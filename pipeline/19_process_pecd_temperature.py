"""Process the downloaded PECD 2m temperature ZIPs into an hourly, Germany-only parquet.

Pure data processing -- no charts. Same ZIP structure (one CSV per year
inside) and DE-column filtering as
pipeline/17_process_pecd_capacity_factors.py, reused directly. Combines the
two file_version downloads (see pipeline/18_download_pecd_temperature.py)
into one continuous series.

Output: data/processed/pecd_temperature_de.parquet
  Hourly DatetimeIndex, single column "DE" (degrees Celsius).

Migrated from
~/research/delu-headline-forecast/pipeline/15_process_pecd_temperature.py.
"""

import pandas as pd

from pecdr.paths import ProjPaths
from pecdr.pecd_io import load_region_timeseries_zip

paths = ProjPaths()
paths.ensure_directories()

parts = [load_region_timeseries_zip(paths.pecd_temperature_zip(fv)) for fv in ("fv2", "fv1")]
temperature = pd.concat(parts).sort_index()
temperature = temperature[~temperature.index.duplicated(keep="last")]
print(f"{len(temperature):,} rows x {len(temperature.columns)} countries - {temperature.index.min()} .. {temperature.index.max()}")

de_temperature = temperature[["DE"]]
print(f"DE temperature range: {de_temperature['DE'].min():.1f}C .. {de_temperature['DE'].max():.1f}C")

de_temperature.to_parquet(paths.pecd_temperature_file)
print(f"Saved -> {paths.pecd_temperature_file}")
