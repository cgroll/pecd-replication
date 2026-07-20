"""Assign each point (e.g. a MaStR wind unit) to its dominant PEON zone.

Per ~/research/mastr-power-capacities-germany's docs/data_sources.md
crosswalk methodology ("For point data..."): snap to the nearest
0.25-degree grid cell, then take the zone with the highest mask fraction at
that cell, restricted to the target country's own zones (ignore a
neighboring country's zone even if it nominally wins that boundary cell --
the point's country is already known from MaStR, no need to guess it from
geometry).
"""

import numpy as np
import pandas as pd
import xarray as xr

from pecdr.grid import nearest_grid_index


def assign_dominant_zone(df: pd.DataFrame, mask: xr.DataArray, zone_prefix: str = "DE", lat_col: str = "latitude", lon_col: str = "longitude") -> pd.Series:
    """Return the dominant PEON zone (argmax mask fraction, restricted to `zone_prefix`) per row.

    `mask` is the full `mask` DataArray from the PEON region-mask Dataset
    (dims: region, latitude, longitude). Rows with no domestic-zone coverage
    at their nearest cell (all `zone_prefix` zones are 0 there -- only
    occurs right at a border) fall back to the nearest zone by centroid
    distance.
    """
    country_zones = [z for z in mask["region"].values if str(z).startswith(zone_prefix)]
    country_mask = mask.sel(region=country_zones)

    lats = mask["latitude"].values
    lons = mask["longitude"].values
    lat_idx = nearest_grid_index(df[lat_col].to_numpy(), lats)
    lon_idx = nearest_grid_index(df[lon_col].to_numpy(), lons)

    # fractions[zone, row] = country_mask[zone, lat_idx[row], lon_idx[row]]
    fractions = country_mask.values[:, lat_idx, lon_idx]
    best_zone_idx = np.argmax(fractions, axis=0)
    best_fraction = fractions[best_zone_idx, np.arange(len(df))]
    zone = np.array(country_zones)[best_zone_idx].astype(object)

    no_coverage = best_fraction <= 0
    if no_coverage.any():
        zone[no_coverage] = _nearest_zone_by_centroid(df.loc[no_coverage, [lat_col, lon_col]], country_mask, lats, lons)

    return pd.Series(zone, index=df.index, name="peon_zone")


def _nearest_zone_by_centroid(points: pd.DataFrame, country_mask: xr.DataArray, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    """Fallback for points with zero domestic-zone mask coverage at their nearest cell.

    Assigns each such point to whichever zone's own non-zero cells have the
    nearest area-weighted centroid -- only expected right at a border,
    where the nearest cell is entirely claimed by a neighboring country's
    zone.
    """
    lat_grid, lon_grid = np.meshgrid(lats, lons, indexing="ij")
    zones, centroid_lats, centroid_lons = [], [], []
    for zone in country_mask["region"].values:
        weight = country_mask.sel(region=zone).values
        if weight.sum() == 0:
            continue
        zones.append(zone)
        centroid_lats.append(float((lat_grid * weight).sum() / weight.sum()))
        centroid_lons.append(float((lon_grid * weight).sum() / weight.sum()))
    centroid_lats, centroid_lons = np.array(centroid_lats), np.array(centroid_lons)

    result = []
    for _, row in points.iterrows():
        dist = (centroid_lats - row.iloc[0]) ** 2 + (centroid_lons - row.iloc[1]) ** 2
        result.append(zones[int(np.argmin(dist))])
    return np.array(result)
