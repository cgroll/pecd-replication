"""Grid-cell-capacity-weighted national wind features (onshore + offshore).

Pure data processing -- no charts. A genuinely better nationwide wind
feature than pipeline/20's zone-level (PEON/PEOF) aggregation: instead of
(a) area-weighting per-cell capacity factor up to a PEON/PEOF zone, then
(b) capacity-weighting zones up to a national number -- both steps
implicitly treat installed capacity as spread uniformly within a zone --
this goes straight from per-grid-cell capacity factor to a national number,
weighted by each individual grid cell's own MaStR installed capacity (each
unit snapped to its single nearest ERA5/PECD grid cell -- no zone involved
anywhere in this path). See `pecdr.era5.grid_cell_capacity_weighted_features`
for the aggregation logic.

Solar stays on the zone-level path (pipeline/20) for now -- MaStR's
coordinate coverage for solar is too poor (~4% of unit rows, concentrated in
utility-scale/ground-mount) to do this without a geocoding fallback.

All months' 100m wind components are loaded and the capacity factor computed
in one pass (not month-by-month like pipeline/20) -- unlike solar's pvlib
chain, `pecdr.physics.wind_capacity_factor` is a cheap elementwise
computation.

Migrated from
~/research/delu-headline-forecast/pipeline/27_process_wind_grid_capacity_weighted.py.
"""

import pandas as pd
import xarray as xr

from pecdr.era5 import grid_cell_capacity_weighted_features
from pecdr.paths import ProjPaths
from pecdr.physics import wind_capacity_factor
from pecdr.wind_bias import raw_wind_speed

paths = ProjPaths()
paths.ensure_directories()

era5_files = sorted(paths.era5_downloads_path.glob("era5_????-??.nc"))
print(f"Loading {len(era5_files)} months of 100m wind components ...")


def load_wind_components(f):
    return xr.open_dataset(f)[["100m_u_component_of_wind", "100m_v_component_of_wind"]].drop_vars(
        "number", errors="ignore"
    )


wind_components = xr.concat([load_wind_components(f) for f in era5_files], dim="time").sortby("time")

wind_speed_100m = raw_wind_speed(wind_components["100m_u_component_of_wind"], wind_components["100m_v_component_of_wind"])
cf_grid = wind_capacity_factor(wind_speed_100m)
print(f"CF grid: {dict(cf_grid.sizes)}")

onshore_capacity = pd.read_parquet(paths.mastr_capacity_by_wind_onshore_grid_month_file)
offshore_capacity = pd.read_parquet(paths.mastr_capacity_by_wind_offshore_grid_month_file)

onshore_features = grid_cell_capacity_weighted_features(cf_grid, onshore_capacity, prefix="wind_onshore")
offshore_features = grid_cell_capacity_weighted_features(cf_grid, offshore_capacity, prefix="wind_offshore")

onshore_features.to_parquet(paths.own_wind_onshore_gridweighted_features_file)
offshore_features.to_parquet(paths.own_wind_offshore_gridweighted_features_file)

print(
    f"Saved onshore: {len(onshore_features):,} hours, "
    f"mean_cf={onshore_features['wind_onshore_effective_cf'].mean():.3f} -> "
    f"{paths.own_wind_onshore_gridweighted_features_file}"
)
print(
    f"Saved offshore: {len(offshore_features):,} hours, "
    f"mean_cf={offshore_features['wind_offshore_effective_cf'].mean():.3f} -> "
    f"{paths.own_wind_offshore_gridweighted_features_file}"
)
