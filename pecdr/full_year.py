"""Vectorized full-year wind-onshore capacity-factor computation.

Same physics as pipeline/09 (bias-corrected 100m wind -> hub-height
extrapolation via alpha -> per-plant power curve -> shutdown derate -> flat
loss derate -> zone/national aggregation), restructured to run over every
hour of a year instead of two snapshots: per-plant static quantities (grid
index, Delta Adjustment factor, alpha per month/hour-of-day bin) are
precomputed once, then each month's ERA5 file is processed as one batch of
array operations rather than one CDS download + one Python call per hour.
"""

import numpy as np
import pandas as pd
import xarray as xr

from pecdr.grid import nearest_grid_index
from pecdr.plant_model import plant_capacity_factor
from pecdr.power_curve import OTHER_LOSSES_FRACTION
from pecdr.shutdown import apply_shutdown_derate
from pecdr.wind_bias import single_data_var


def precompute_plant_static(plants: pd.DataFrame, delta_100: xr.DataArray, alpha_ds: xr.Dataset) -> tuple[np.ndarray, np.ndarray]:
    """Per-plant, time-invariant quantities needed by the monthly loop.

    Returns `(delta_at_plant, alpha_lookup)`:
    - `delta_at_plant`: (n_plants,) Delta Adjustment factor at each plant's grid cell.
    - `alpha_lookup`: (12, 24, n_plants) alpha value per (month, hour-of-day, plant),
      built once from the 288-step climatological grid rather than re-selected per hour.
    """
    plant_lat = xr.DataArray(plants["grid_lat"].to_numpy(), dims="plant")
    plant_lon = xr.DataArray(plants["grid_lon"].to_numpy(), dims="plant")

    delta_at_plant = delta_100.sel(latitude=plant_lat, longitude=plant_lon, method="nearest").to_numpy()

    alpha_da = single_data_var(alpha_ds)
    alpha_at_plant = alpha_da.sel(latitude=plant_lat, longitude=plant_lon, method="nearest")  # (time=288, plant)
    months = alpha_da["time"].dt.month.values
    hours = alpha_da["time"].dt.hour.values
    alpha_values = alpha_at_plant.to_numpy()  # (288, n_plants)

    alpha_lookup = np.empty((12, 24, len(plants)))
    alpha_lookup[months - 1, hours] = alpha_values
    return delta_at_plant, alpha_lookup


def compute_month(era5_file, plants: pd.DataFrame, curve_cache: dict, delta_at_plant: np.ndarray, alpha_lookup: np.ndarray) -> pd.DataFrame:
    """Per-plant capacity factor for every hour in one ERA5 month file.

    Returns a (time x plant) DataFrame -- one row per hour, one column per
    plant (`unit_id`), values are the final (post-shutdown, post-loss)
    capacity factor.
    """
    ds = xr.open_dataset(era5_file)
    lat_idx = nearest_grid_index(plants["grid_lat"].to_numpy(), ds["latitude"].values)
    lon_idx = nearest_grid_index(plants["grid_lon"].to_numpy(), ds["longitude"].values)

    u = ds["100m_u_component_of_wind"].to_numpy()
    v = ds["100m_v_component_of_wind"].to_numpy()
    raw_speed = np.sqrt(u**2 + v**2)  # (time, lat, lon)
    v100_at_plant = raw_speed[:, lat_idx, lon_idx]  # (time, n_plants)
    corrected = v100_at_plant * delta_at_plant[None, :]

    month = int(pd.Timestamp(ds["time"].values[0]).month)
    hours_of_day = ds["time"].dt.hour.values
    alpha_at_hours = alpha_lookup[month - 1][hours_of_day]  # (time, n_plants)

    hub_height = plants["hub_height_m"].to_numpy()
    v_hub = corrected * (hub_height[None, :] / 100) ** alpha_at_hours  # (time, n_plants)

    n_hours = v_hub.shape[0]
    cf = np.empty((n_hours, len(plants)))
    matched_type, rated_ws = plants["matched_type"], plants["rated_wind_speed_ms"]
    for h in range(n_hours):
        cf[h] = plant_capacity_factor(v_hub[h], matched_type, rated_ws, curve_cache)

    cf = apply_shutdown_derate(cf, v_hub)
    cf = cf * (1 - OTHER_LOSSES_FRACTION)

    return pd.DataFrame(cf, index=pd.DatetimeIndex(ds["time"].values, name="timestamp"), columns=plants["unit_id"])


def aggregate_to_zone_and_national(cf_df: pd.DataFrame, plants: pd.DataFrame) -> pd.DataFrame:
    """Capacity-weighted zone (PEON) and national capacity factor, per hour.

    `cf_df` is (time x plant) as returned by `compute_month`. Returns one
    row per hour with columns `national` and one per PEON zone.
    """
    capacity = plants.set_index("unit_id")["capacity_mw"].reindex(cf_df.columns)
    power = cf_df * capacity.to_numpy()[None, :]

    zone_indicator = pd.get_dummies(plants.set_index("unit_id")["peon_zone"]).reindex(cf_df.columns).fillna(0)
    zone_capacity = (zone_indicator.to_numpy() * capacity.to_numpy()[:, None]).sum(axis=0)
    zone_power = power.to_numpy() @ zone_indicator.to_numpy()
    zone_cf = pd.DataFrame(zone_power / zone_capacity[None, :], index=cf_df.index, columns=zone_indicator.columns)

    zone_cf["national"] = power.sum(axis=1) / capacity.sum()
    return zone_cf
