"""Build the onshore wind plant panel, optionally as of a given date.

Shared by `pipeline/08_build_wind_onshore_plant_panel.py`, which uses this
both for today's "active now" snapshot (`as_of=None`, used by the
two-snapshot check in `pipeline/09`) and for a series of year-start
snapshots (`as_of=<year>-01-01`, used by the full-year backtest in
`pipeline/10` to avoid applying today's larger, newer fleet retroactively
to earlier years' weather).
"""

import pandas as pd

from pecdr.grid import nearest_grid_index
from pecdr.peon_zones import assign_dominant_zone
from pecdr.pecd_io import open_single_zipped_netcdf
from pecdr.paths import ProjPaths


def build_plant_panel(paths: ProjPaths, as_of: pd.Timestamp | None = None) -> pd.DataFrame:
    """Active onshore wind units, one row per unit, as of `as_of` (or "today" if None).

    "Today" (`as_of=None`) matches units with no `final_shutdown_date` yet,
    same as this project's original snapshot. Given an explicit `as_of`,
    a unit counts as active if it was already commissioned by then and
    either never shut down or shut down after `as_of`.
    """
    events = pd.read_parquet(
        paths.mastr_capacity_events_file,
        columns=["unit_id", "technology", "region_code", "capacity_mw", "commissioning_date", "final_shutdown_date", "longitude", "latitude"],
    )
    wind = events[events["technology"] == "wind"].copy()
    is_offshore = wind["region_code"].astype(str).str.startswith("DEZZ")
    has_coords = wind["longitude"].notna() & wind["latitude"].notna()

    if as_of is None:
        is_active = wind["final_shutdown_date"].isna()
    else:
        is_active = (wind["commissioning_date"] <= as_of) & (wind["final_shutdown_date"].isna() | (wind["final_shutdown_date"] > as_of))

    onshore = wind[~is_offshore & is_active & has_coords].copy()

    detail = pd.read_parquet(paths.mastr_wind_technical_detail_file)
    plants = onshore.merge(detail, on="unit_id", how="left")

    mask_ds = open_single_zipped_netcdf(paths.peon_mask_zip)
    lats, lons = mask_ds["latitude"].values, mask_ds["longitude"].values

    lat_idx = nearest_grid_index(plants["latitude"].to_numpy(), lats)
    lon_idx = nearest_grid_index(plants["longitude"].to_numpy(), lons)
    plants["grid_lat"] = lats[lat_idx]
    plants["grid_lon"] = lons[lon_idx]

    plants["peon_zone"] = assign_dominant_zone(plants, mask_ds["mask"], zone_prefix="DE")

    return plants[
        ["unit_id", "capacity_mw", "hub_height_m", "rotor_diameter_m", "manufacturer", "turbine_model", "longitude", "latitude", "grid_lat", "grid_lon", "peon_zone"]
    ]
