"""Simple physics models converting raw ERA5 weather into wind/solar capacity factors.

Deliberately simple -- one representative turbine curve / panel config, not
PECD's actual technology mix or bias-corrected wind speed (contrast
`pecdr.wind_bias`/`pecdr.power_curve`, this project's own PECD-methodology
replication). This is "approach 2" of the three physically-motivated
feature approaches (see pipeline/12_compare_all_approaches.py): computed
from scratch, but with the simplest possible physics.

Migrated from ~/research/delu-headline-forecast/dhf/physics.py -- see the
migration plan. `compare_by_zone` stayed there for now (only used by the
EDA/comparison notebooks, migrated in a later phase).
"""

import numpy as np
import pandas as pd
import pvlib
import xarray as xr

# --- Wind: generic three-region turbine power curve ---
# A widely-used generic onshore-turbine shape, not tied to a specific model
# or to PECD's own (undisclosed) reference turbine. Applied at 100m (roughly
# hub height) for both onshore and offshore in this first draft.
WIND_CUT_IN_MS = 3.0
WIND_RATED_MS = 12.0
WIND_CUT_OUT_MS = 25.0


def wind_capacity_factor(wind_speed_ms: xr.DataArray) -> xr.DataArray:
    """Cubic-ramp turbine power curve: 0 below cut-in, cubic ramp cut-in to
    rated, flat at 1 up to cut-out, 0 above (safety shutdown)."""
    ramp = ((wind_speed_ms - WIND_CUT_IN_MS) / (WIND_RATED_MS - WIND_CUT_IN_MS)) ** 3
    cf = ramp.clip(0.0, 1.0)
    return cf.where((wind_speed_ms >= WIND_CUT_IN_MS) & (wind_speed_ms < WIND_CUT_OUT_MS), 0.0)


# --- Solar: Erbs GHI decomposition -> fixed-tilt POA transposition -> Faiman
# cell temperature -> PVWatts DC output ---
PANEL_TILT_DEG = 35.0  # roughly optimal fixed tilt at German latitudes
PANEL_AZIMUTH_DEG = 180.0  # south-facing
# Solar position (zenith/azimuth) is computed once for this single
# domain-centroid site and broadcast across the whole grid -- geometry varies
# only modestly across Germany's ~9 degree latitude span at a given hour,
# and per-grid-cell solar position isn't worth the complexity for a first
# draft. One shared panel tilt/azimuth/technology is used everywhere too --
# real per-plant orientation (MaStR's solar_technical_detail, see
# mastr-power-capacities-germany) is this project's later, bias-adjusted
# solar replication phase, not this simple baseline.
DOMAIN_CENTROID_LAT, DOMAIN_CENTROID_LON = 51.0, 10.0
PVWATTS_GAMMA_PDC = -0.004  # per degree C, typical crystalline-silicon temperature coefficient


def solar_capacity_factor(ghi_wm2: xr.DataArray, temp_air_c: xr.DataArray, wind_speed_ms: xr.DataArray) -> xr.DataArray:
    """PV capacity factor (pdc0=1, so the result is already a 0..~1 fraction).

    Grid arrays are transposed to (cell, time) -- time as the *trailing*
    axis -- before calling pvlib: pvlib's irradiance functions derive some
    quantities (e.g. extraterrestrial radiation) purely from the timestamp,
    shaped (n_time,). Numpy broadcasts trailing axes, so a (cell, time)
    array lines up automatically against a (time,) one; a (time, cell)
    array would not, and pvlib has no cell/spatial axis of its own to
    broadcast against.
    """
    time_index = pd.DatetimeIndex(ghi_wm2["time"].values)
    lat_dim, lon_dim = "latitude", "longitude"
    n_time, n_lat, n_lon = len(time_index), ghi_wm2.sizes[lat_dim], ghi_wm2.sizes[lon_dim]
    n_cells = n_lat * n_lon

    def to_cell_time(da: xr.DataArray) -> np.ndarray:
        return da.transpose("time", lat_dim, lon_dim).values.reshape(n_time, n_cells).T

    ghi = np.clip(to_cell_time(ghi_wm2), 0, None)
    temp_air = to_cell_time(temp_air_c)
    wind_speed = to_cell_time(wind_speed_ms)

    location = pvlib.location.Location(DOMAIN_CENTROID_LAT, DOMAIN_CENTROID_LON, tz="UTC")
    solpos = location.get_solarposition(time_index)
    zenith = np.broadcast_to(solpos["apparent_zenith"].to_numpy(), (n_cells, n_time))
    azimuth = np.broadcast_to(solpos["azimuth"].to_numpy(), (n_cells, n_time))

    # Plain numpy day-of-year, not a DatetimeIndex: pvlib returns a
    # pandas.Series for extraterrestrial-radiation-derived quantities when
    # given a DatetimeIndex, which doesn't broadcast against our (cell,
    # time) 2D arrays (Series ops assume a 1D result matching their own
    # index). A bare numpy doy array keeps everything as plain ndarrays.
    doy = time_index.dayofyear.to_numpy()
    decomposed = pvlib.irradiance.erbs(ghi, zenith, doy)

    poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=PANEL_TILT_DEG,
        surface_azimuth=PANEL_AZIMUTH_DEG,
        dni=decomposed["dni"],
        ghi=ghi,
        dhi=decomposed["dhi"],
        solar_zenith=zenith,
        solar_azimuth=azimuth,
    )
    poa_global = poa["poa_global"]

    cell_temp = pvlib.temperature.faiman(poa_global, temp_air, wind_speed)
    dc = pvlib.pvsystem.pvwatts_dc(poa_global, cell_temp, pdc0=1.0, gamma_pdc=PVWATTS_GAMMA_PDC)
    # PVWatts can transiently exceed pdc0 at low zenith / high POA (reflected
    # + diffuse components stacking above the 1000 W/m^2 STC reference) --
    # clip to match PECD's 0..1 capacity-factor definition.
    cf = np.clip(dc, 0, 1.0).reshape(n_lat, n_lon, n_time).transpose(2, 0, 1)

    return xr.DataArray(
        cf,
        dims=("time", lat_dim, lon_dim),
        coords={"time": ghi_wm2["time"], lat_dim: ghi_wm2[lat_dim], lon_dim: ghi_wm2[lon_dim]},
    )
