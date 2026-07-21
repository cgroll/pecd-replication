"""Process all downloaded ERA5 months into own physics-derived capacity factors.

Pure data processing -- no charts. Applies `pecdr.physics`'s wind power
curve + pvlib solar chain, per grid cell, aggregated to PEON/PEOF/NUTS2
zones only afterwards -- across every `era5_YYYY-MM.nc` file in
data/downloads/era5/ (pipeline/15_download_era5_full_period.py), producing
full-backtest-period capacity factor panels shaped exactly like PECD's own
processed files (pipeline/17_process_pecd_capacity_factors.py) -- same
zones, same wide hourly format -- so every downstream consumer works
identically regardless of which source produced the panel.

Processes one month at a time and only keeps the small aggregated
(zone, time) result in memory afterwards -- the large per-grid-cell arrays
are discarded before moving to the next month.

Migrated from
~/research/delu-headline-forecast/pipeline/24_process_era5_capacity_factors.py.
"""

import pandas as pd
import xarray as xr

from pecdr.era5 import mask_weighted_regional_mean
from pecdr.paths import ProjPaths
from pecdr.pecd_io import open_single_zipped_netcdf
from pecdr.physics import solar_capacity_factor, wind_capacity_factor
from pecdr.wind_bias import raw_wind_speed

paths = ProjPaths()
paths.ensure_directories()

era5_files = sorted(paths.era5_downloads_path.glob("era5_????-??.nc"))
months = [f.stem.removeprefix("era5_") for f in era5_files]
print(f"Processing {len(months)} months: {months[0]} .. {months[-1]}")

peon_mask = open_single_zipped_netcdf(paths.peon_mask_zip)["mask"]
peof_mask = open_single_zipped_netcdf(paths.peof_mask_zip)["mask"]
nuts2_mask = open_single_zipped_netcdf(paths.nuts2_mask_zip)["mask"]

peon_de = sorted(r for r in peon_mask.region.values.tolist() if str(r).startswith("DE"))
peof_de = sorted(r for r in peof_mask.region.values.tolist() if str(r).startswith("DE"))

# Solar's NUTS2 columns are only meaningful where PECD itself has data --
# restrict to that same set for a directly comparable panel.
pecd_solar_regions = sorted({region for _, region in pd.read_parquet(paths.pecd_solar_capacity_factors_file).columns})
nuts2_de = sorted(r for r in nuts2_mask.region.values.tolist() if str(r).startswith("DE") and r in pecd_solar_regions)

wind_onshore_parts, wind_offshore_parts, solar_parts = [], [], []

for i, (month, era5_file) in enumerate(zip(months, era5_files), 1):
    print(f"[{i}/{len(months)}] {month}", flush=True)
    era5 = xr.open_dataset(era5_file)

    wind_speed_100m = raw_wind_speed(era5["100m_u_component_of_wind"], era5["100m_v_component_of_wind"])
    wind_speed_10m = raw_wind_speed(era5["10m_u_component_of_wind"], era5["10m_v_component_of_wind"])
    temperature_c = era5["2m_temperature"] - 273.15
    ghi_wm2 = era5["surface_solar_radiation_downwards"] / 3600

    wind_cf_grid = wind_capacity_factor(wind_speed_100m)
    solar_cf_grid = solar_capacity_factor(ghi_wm2, temperature_c, wind_speed_10m)

    wind_onshore_parts.append(mask_weighted_regional_mean(wind_cf_grid, peon_mask.sel(region=peon_de)))
    wind_offshore_parts.append(mask_weighted_regional_mean(wind_cf_grid, peof_mask.sel(region=peof_de)))
    solar_parts.append(mask_weighted_regional_mean(solar_cf_grid, nuts2_mask.sel(region=nuts2_de)))

    era5.close()

wind_onshore = pd.concat(wind_onshore_parts).sort_index()
wind_offshore = pd.concat(wind_offshore_parts).sort_index()
solar = pd.concat(solar_parts).sort_index()

for name, df in [("onshore", wind_onshore), ("offshore", wind_offshore), ("solar", solar)]:
    n_dups = int(df.index.duplicated().sum())
    if n_dups:
        print(f"  Dropping {n_dups} duplicate timestamps in {name}")

wind_onshore = wind_onshore[~wind_onshore.index.duplicated(keep="first")]
wind_offshore = wind_offshore[~wind_offshore.index.duplicated(keep="first")]
solar = solar[~solar.index.duplicated(keep="first")]

wind_onshore.to_parquet(paths.own_wind_onshore_capacity_factors_file)
wind_offshore.to_parquet(paths.own_wind_offshore_capacity_factors_file)
solar.to_parquet(paths.own_solar_capacity_factors_file)

print(f"Saved onshore wind: {wind_onshore.shape} -> {paths.own_wind_onshore_capacity_factors_file}")
print(f"Saved offshore wind: {wind_offshore.shape} -> {paths.own_wind_offshore_capacity_factors_file}")
print(f"Saved solar: {solar.shape} -> {paths.own_solar_capacity_factors_file}")
