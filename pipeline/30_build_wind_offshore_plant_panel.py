"""Build the offshore wind plant panel: one row per unit, with capacity, hub
height, rotor diameter, turbine model, coordinates, nearest 0.25-degree grid
cell, and dominant PEOF zone.

Pure data processing script -- no visualizations. Same structure as
pipeline/08_build_wind_onshore_plant_panel.py, via
`pecdr.plant_panel.build_plant_panel(offshore=True)`:

1. Today's active fleet (`wind_offshore_plant_panel_file`) -- used by
   pipeline/31's two-snapshot check.
2. One snapshot per year in `pecdr.domain.FULL_YEAR_BACKTEST_YEARS`, as of
   Jan 1 of that year (`wind_offshore_plant_panel_by_year_file`) -- used by
   pipeline/32's full-year backtest, so each year's weather runs through
   that year's own fleet instead of today's larger, newer one.
"""

import pandas as pd

from pecdr.domain import FULL_YEAR_BACKTEST_YEARS
from pecdr.paths import ProjPaths
from pecdr.plant_panel import build_plant_panel

paths = ProjPaths()
paths.ensure_directories()

today_panel = build_plant_panel(paths, as_of=None, offshore=True)
today_panel.to_parquet(paths.wind_offshore_plant_panel_file, index=False)
print(f"Today: {len(today_panel):,} units, {today_panel['capacity_mw'].sum():,.0f} MW -> {paths.wind_offshore_plant_panel_file}")

for year in FULL_YEAR_BACKTEST_YEARS:
    year_start = pd.Timestamp(f"{year}-01-01")
    panel = build_plant_panel(paths, as_of=year_start, offshore=True)
    out_file = paths.wind_offshore_plant_panel_by_year_file(year)
    panel.to_parquet(out_file, index=False)
    print(f"{year}: {len(panel):,} units, {panel['capacity_mw'].sum():,.0f} MW -> {out_file}")
