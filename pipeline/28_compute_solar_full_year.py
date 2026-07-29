"""Compute hourly modeled solar PV capacity factor (NUTS2 x technology),
using the technology- and orientation-aware, PECD-documented physics
chain validated in pipeline/27 (`pecdr.solar_config_physics`), for every
hour of every year in `pecdr.domain.FULL_YEAR_BACKTEST_YEARS`.

Pure data processing script -- no visualizations (see
pipeline/29_analyse_solar_full_year.py for the comparison against PECD's
own product and SMARD). Fleet vintage is *monthly*, not annual (unlike
wind's `pipeline/10`): pipeline/24's own monthly (nuts2_region,
pecd_technology, month) capacity panel already exists at this
resolution, and Germany's solar fleet grew too fast over 2019-2025 for a
single annual snapshot to be a good approximation.

Temporal downscaling (pipeline/27's tested-but-not-adopted 15-minute
step, see `pecdr/temporal_downscaling.py`) is intentionally not applied
here -- it made no measurable difference there and would roughly double
runtime for no benefit.

Uses this project's own hourly ERA5 archive
(pipeline/15_download_era5_full_period.py, data/downloads/era5/era5_YYYY-MM.nc).
"""

import pandas as pd
import xarray as xr

from pecdr.domain import FULL_YEAR_BACKTEST_YEARS
from pecdr.era5 import mask_weighted_regional_mean, region_centroids
from pecdr.paths import ProjPaths
from pecdr.pecd_io import open_single_zipped_netcdf
from pecdr.solar_full_year import active_configs_for_month, compute_month_by_tech_region

paths = ProjPaths()
paths.ensure_directories()

output_file = paths.own_solar_full_year_cf_file
if output_file.exists():
    print(f"Already computed -> {output_file}")
else:
    mask = open_single_zipped_netcdf(paths.nuts2_mask_zip)["mask"]
    de_regions = sorted(r for r in mask.region.values.tolist() if str(r).startswith("DE"))
    mask_de = mask.sel(region=de_regions)
    centroids = region_centroids(mask_de)

    unit_panel = pd.read_parquet(paths.solar_unit_technology_file)

    monthly_results = []
    for year in FULL_YEAR_BACKTEST_YEARS:
        for month in range(1, 13):
            month_str = f"{year}-{month:02d}"
            era5_file = paths.era5_month_file(month_str)
            if not era5_file.exists():
                print(f"  {month_str}: no ERA5 file, skipping")
                continue

            era5 = xr.open_dataset(era5_file)
            ghi_grid = era5["surface_solar_radiation_downwards"] / 3600
            temp_grid = era5["2m_temperature"] - 273.15
            ghi_region = mask_weighted_regional_mean(ghi_grid, mask_de)
            temp_region = mask_weighted_regional_mean(temp_grid, mask_de)
            era5.close()

            month_end = ghi_region.index.max()
            configs = active_configs_for_month(unit_panel, month_end)

            result = compute_month_by_tech_region(ghi_region, temp_region, configs, centroids)
            monthly_results.append(result)
            print(f"  {month_str}: {len(configs):,} configs, {result.shape[1]} (technology, region) columns, {len(result)} hours")

    full_period = pd.concat(monthly_results).sort_index()
    full_period.to_parquet(output_file)
    print(f"Saved {len(full_period):,} hourly rows x {full_period.shape[1]} (technology, region) columns -> {output_file}")
