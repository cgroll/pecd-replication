"""Compute hourly modeled wind-onshore capacity factor (PEON zones +
national) for every hour of 2020.

Pure data processing script -- no visualizations (see
pipeline/11_analyse_wind_onshore_full_year.py for the comparison charts).
Same physics as pipeline/09 (bias-corrected 100m wind -> hub-height
extrapolation via alpha -> per-plant power curve -> shutdown derate -> flat
loss derate -> zone/national aggregation), run over the full year via
pecdr.full_year's vectorized month-batch implementation instead of two
individual snapshot downloads.

Uses this project's own hourly ERA5 archive
(pipeline/15_download_era5_full_period.py, data/downloads/era5/era5_YYYY-MM.nc).
PECD's own 2020 ground truth (gridded wind speed, PEON capacity factor) was
already fetched in full-year form by pipeline/01-02/07, just never
previously read past its first two rows.
"""

import time

import pandas as pd

from pecdr.full_year import aggregate_to_zone_and_national, compute_month, precompute_plant_static
from pecdr.paths import ProjPaths
from pecdr.pecd_io import open_single_zipped_netcdf
from pecdr.plant_model import load_plants_with_curves
from pecdr.wind_bias import delta_correction

paths = ProjPaths()
paths.ensure_directories()

output_file = paths.wind_onshore_full_year_cf_file
if output_file.exists():
    print(f"Already computed -> {output_file}")
else:
    plants, curve_cache = load_plants_with_curves(paths)
    print(f"Plants: {len(plants):,} ({plants['capacity_mw'].sum():,.0f} MW)")

    era5_clim_100 = open_single_zipped_netcdf(paths.wind_bias_reference_zip("climatology_era5_100m"))
    gwa2_clim_100 = open_single_zipped_netcdf(paths.wind_bias_reference_zip("climatology_gwa2_100m"))
    delta_100 = delta_correction(era5_clim_100, gwa2_clim_100)
    alpha_ds = open_single_zipped_netcdf(paths.wind_bias_reference_zip("power_law_coefficient"))
    delta_at_plant, alpha_lookup = precompute_plant_static(plants, delta_100, alpha_ds)

    monthly_results = []
    for month in range(1, 13):
        t0 = time.time()
        cf_df = compute_month(paths.era5_month_file(f"2020-{month:02d}"), plants, curve_cache, delta_at_plant, alpha_lookup)
        agg = aggregate_to_zone_and_national(cf_df, plants)
        monthly_results.append(agg)
        print(f"  2020-{month:02d}: {len(agg)} hours in {time.time() - t0:.1f}s")

    full_year = pd.concat(monthly_results).sort_index()
    full_year.to_parquet(output_file)
    print(f"Saved {len(full_year):,} hourly rows -> {output_file}")
