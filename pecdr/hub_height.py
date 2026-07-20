"""Extrapolate wind speed to hub height using PECD v4.2's precomputed power-law (alpha) grid.

Per the PUG, alpha is stratified by hour-of-day x month (24x12=288
climatological bins, downloaded as `power_law_coefficient.zip` in
pipeline/01) -- used directly rather than re-derived, since the underlying
formula is a straightforward, unambiguous log-ratio (see project decision:
re-deriving it ourselves only risks numerical mismatches for no benefit).
This module applies the power law:

    v(h) = v_ref * (h / h_ref) ** alpha(hour, month, cell)

No PECD ground truth exists for wind speed at arbitrary hub heights (PECD
only ever publishes 10m and 100m as standalone gridded variables), so this
step can't be checked against a third independent ground truth the way the
bias correction was. Instead, pipeline/05 checks internal consistency:
alpha was itself derived from the 10m/100m ratio (per the PUG), so
extrapolating our already-validated 100m field back down to 10m via alpha
should closely reproduce our already-validated 10m field.
"""

import xarray as xr

from pecdr.wind_bias import single_data_var


def alpha_for_timestamp(alpha_ds: xr.Dataset, timestamp) -> xr.DataArray:
    """Select the (latitude, longitude) alpha grid for one real timestamp's hour-of-day x month bin.

    `alpha_ds`'s `time` coordinate spans a single placeholder year
    (2011-01-01 .. 2011-12-01T23:00, 288 steps = 24 hours x 12 months) --
    a climatological lookup table, not a real time series -- so
    `timestamp` is matched by (month, hour), not by date.
    """
    alpha = single_data_var(alpha_ds)
    match = (alpha["time"].dt.month == timestamp.month) & (alpha["time"].dt.hour == timestamp.hour)
    matches = alpha.sel(time=match)
    if matches.sizes["time"] != 1:
        raise ValueError(f"Expected exactly one alpha bin for {timestamp}, found {matches.sizes['time']}")
    return matches.isel(time=0).drop_vars("time")


def extrapolate_to_hub_height(wind_speed_ref: xr.DataArray, alpha: xr.DataArray, ref_height_m: float, hub_height_m) -> xr.DataArray:
    """Power-law vertical extrapolation: v(h) = v_ref * (h / h_ref) ** alpha.

    `hub_height_m` may be a scalar (uniform target height) or a DataArray
    aligned with `wind_speed_ref` (e.g. a per-plant hub height after
    snapping each plant to its nearest grid cell) -- both broadcast the
    same way.
    """
    alpha_aligned = alpha.reindex_like(wind_speed_ref, method="nearest", tolerance=0.01)
    return wind_speed_ref * (hub_height_m / ref_height_m) ** alpha_aligned
