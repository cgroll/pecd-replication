"""Compute hourly modeled wind-onshore capacity factor (PEON zones +
national) for every hour of every year in `FULL_YEAR_BACKTEST_YEARS`.

Pure data processing script -- no visualizations (see
pipeline/11_analyse_wind_onshore_full_year.py for the comparison charts).
Same physics as pipeline/09 (bias-corrected 100m wind -> hub-height
extrapolation via alpha -> per-plant power curve -> shutdown derate -> flat
loss derate -> zone/national aggregation), run over full years via
pecdr.full_year's vectorized month-batch implementation instead of two
individual snapshot downloads.

Each year uses *that year's own* start-of-year fleet
(`wind_onshore_plant_panel_by_year_file`, built by pipeline/08 from MaStR's
per-unit commissioning/shutdown dates) rather than today's fleet applied
retroactively -- otherwise every year's weather gets run through a fleet
~30% larger (and skewed toward newer, higher-capacity-factor turbines)
than what actually existed.

Uses this project's own hourly ERA5 archive
(pipeline/15_download_era5_full_period.py, data/downloads/era5/era5_YYYY-MM.nc).
"""

import time

import pandas as pd

from pecdr.domain import FULL_YEAR_BACKTEST_YEARS
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
    era5_clim_100 = open_single_zipped_netcdf(paths.wind_bias_reference_zip("climatology_era5_100m"))
    gwa2_clim_100 = open_single_zipped_netcdf(paths.wind_bias_reference_zip("climatology_gwa2_100m"))
    delta_100 = delta_correction(era5_clim_100, gwa2_clim_100)
    alpha_ds = open_single_zipped_netcdf(paths.wind_bias_reference_zip("power_law_coefficient"))

    yearly_results = []
    for year in FULL_YEAR_BACKTEST_YEARS:
        year_panel = pd.read_parquet(paths.wind_onshore_plant_panel_by_year_file(year))
        plants, curve_cache = load_plants_with_curves(paths, plant_panel=year_panel)
        print(f"{year}: {len(plants):,} plants ({plants['capacity_mw'].sum():,.0f} MW)")

        # Delta/alpha lookups are keyed by each plant's grid cell, so they
        # must be rebuilt per year -- the plant set itself changes.
        delta_at_plant, alpha_lookup = precompute_plant_static(plants, delta_100, alpha_ds)

        monthly_results = []
        for month in range(1, 13):
            t0 = time.time()
            cf_df = compute_month(paths.era5_month_file(f"{year}-{month:02d}"), plants, curve_cache, delta_at_plant, alpha_lookup)
            agg = aggregate_to_zone_and_national(cf_df, plants)
            monthly_results.append(agg)
            print(f"  {year}-{month:02d}: {len(agg)} hours in {time.time() - t0:.1f}s")

        yearly_results.append(pd.concat(monthly_results).sort_index())

    full_period = pd.concat(yearly_results).sort_index()
    full_period.to_parquet(output_file)
    print(f"Saved {len(full_period):,} hourly rows -> {output_file}")
