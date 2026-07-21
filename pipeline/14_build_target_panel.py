"""Combine the raw per-series SMARD downloads into a single hourly target panel.

Pure data processing -- no charts. Reads the four raw parquet files written
by pipeline/13_download_smard.py and joins them on their shared hourly
DatetimeIndex. The individual series have different start dates (pv/
wind_onshore go back to late 2016 under the DE-LU region code; wind_offshore
and load only to 2018-09-30, matching the DE-LU market area's actual start);
the inner join below trims the panel to their common overlap.

Output: data/processed/target_panel.parquet
  Hourly DatetimeIndex, columns: pv, wind_onshore, wind_offshore, load (MW).

Migrated from
~/research/delu-headline-forecast/pipeline/02_build_target_panel.py -- see
the migration plan.
"""

import pandas as pd

from pecdr.paths import ProjPaths

paths = ProjPaths()
paths.ensure_directories()

SERIES_NAMES = ["pv", "wind_onshore", "wind_offshore", "load"]

frames = []
for name in SERIES_NAMES:
    series_df = pd.read_parquet(paths.smard_raw_file(name))
    series_df = series_df.rename(columns={series_df.columns[0]: name})
    frames.append(series_df)

panel = pd.concat(frames, axis=1).sort_index()
panel.index.name = "timestamp"

n_before = len(panel)
panel = panel.dropna(how="any")
print(f"Dropped {n_before - len(panel):,} of {n_before:,} hours with at least one missing series")

panel.to_parquet(paths.target_panel_file)
print(f"Saved {len(panel):,} rows ({panel.index.min()} .. {panel.index.max()}) -> {paths.target_panel_file}")
