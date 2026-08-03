"""Download SMARD's monthly redispatch-by-energy-source series.

Pure data acquisition -- no charts. Ground truth for how much feed-in was
curtailed (and increased, for context) under Redispatch 2.0, per energy
carrier, since July 2022 -- see `pipeline/44_analyse_congestion_curtailment.py`
for the analysis this feeds.

Unlike pipeline/13's incremental download, this always re-fetches the whole
series: it's tiny (a few hundred rows), and SMARD does occasionally restate
recent months, which an incremental append would freeze at whatever value
was first observed.
"""

from pecdr.paths import ProjPaths
from pecdr.smard_redispatch import download_redispatch_by_source

paths = ProjPaths()
paths.ensure_directories()

redispatch = download_redispatch_by_source()
redispatch.to_parquet(paths.redispatch_by_source_file)

print(f"Saved {len(redispatch):,} rows ({redispatch['month'].min().date()} .. {redispatch['month'].max().date()}) -> {paths.redispatch_by_source_file}")
print(redispatch.groupby(["direction", "energy_source"])["gwh"].sum().sort_values(ascending=False))
