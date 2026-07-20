"""Wind-speed bias correction: replicate PECD v4.2's GWA2 Delta Adjustment.

Per the PUG (confirmed empirically -- see pipeline/02's module docstring,
which found the "Bias adjustment with mean delta method" step recorded in
PECD's own file history), PECD bias-corrects ERA5 wind speed by multiplying
each grid cell by the ratio of the Global Wind Atlas v2 climatology to
ERA5's own climatology, both over PECD's 2006-2018 reference period:

    delta(cell) = climatology_gwa2(cell) / climatology_era5(cell)
    corrected(t, cell) = raw_era5(t, cell) * delta(cell)

This module does not yet replicate PECD's other two documented preprocessing
steps (capping outliers above 70 m/s, and interpolating the ERA5 10:00 UTC
dip) -- deliberately out of scope for milestone 1's two snapshot hours,
neither of which is 10:00 UTC nor expected to see >70 m/s gusts. Revisit
once a validation window includes 10:00 UTC or extreme-wind hours.
"""

import numpy as np
import xarray as xr


def single_data_var(ds: xr.Dataset) -> xr.DataArray:
    """Return a Dataset's one data variable, regardless of its (CDS-assigned) name."""
    names = list(ds.data_vars)
    if len(names) != 1:
        raise ValueError(f"Expected exactly one data variable, found {names}")
    return ds[names[0]]


def climatology_grid(ds: xr.Dataset) -> xr.DataArray:
    """Squeeze a climatology Dataset down to a plain (latitude, longitude) grid.

    PECD's Delta Adjustment factor is a single ratio per cell (not
    stratified by hour/month, unlike alpha) -- if the downloaded grid still
    carries a `time` dimension (e.g. a length-1 reference-period stamp),
    average over it defensively rather than assuming a particular length.
    """
    da = single_data_var(ds)
    if "time" in da.dims:
        da = da.mean(dim="time")
    return da


def delta_correction(era5_clim: xr.Dataset, gwa2_clim: xr.Dataset) -> xr.DataArray:
    """Per-cell GWA2/ERA5 climatology ratio -- PECD's Delta Adjustment factor."""
    return climatology_grid(gwa2_clim) / climatology_grid(era5_clim)


def raw_wind_speed(u: xr.DataArray, v: xr.DataArray) -> xr.DataArray:
    """Wind speed magnitude from u/v components."""
    return np.sqrt(u**2 + v**2)


def restrict_to_onshore(*arrays: xr.DataArray, reference: xr.DataArray) -> list[xr.DataArray]:
    """Mask every array to `reference`'s non-NaN cells (its land/onshore footprint).

    PECD's ERA5/GWA2 climatology grids are NaN over sea cells -- they're
    part of the onshore-wind-specific "Weights and masks" bundle, so GWA2
    coverage (and therefore our Delta Adjustment factor) is only defined
    over land. PECD's own general-purpose bias-corrected wind-speed product
    has no such gap (it's a general climate variable, valid over sea too),
    so comparing the two without masking would silently average over
    different domains on each side -- not a like-for-like comparison, and
    not indicative of any actual mismatch in the replication.
    """
    land_mask = reference.notnull()
    return [a.where(land_mask) for a in arrays]


def apply_delta_correction(raw_speed: xr.DataArray, delta: xr.DataArray) -> xr.DataArray:
    """Apply the per-cell Delta Adjustment, aligning grids by nearest lat/lon.

    `delta` comes from a separate CDS download (the climatology grids) that
    may not share float-identical coordinate values with `raw_speed`'s grid
    (e.g. float32 vs. float64 rounding) even though both are nominally the
    same 0.25-degree ERA5 grid -- nearest-neighbor reindexing handles this
    robustly instead of requiring exact float equality.
    """
    delta_aligned = delta.reindex_like(raw_speed, method="nearest", tolerance=0.01)
    return raw_speed * delta_aligned
