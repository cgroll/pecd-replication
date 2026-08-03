"""Download netztransparenz.de's per-measure Redispatch export (Format 5).

Pure data acquisition -- no charts. The per-measure counterpart to
pipeline/43's SMARD download: real start/end timestamps, per-plant/cluster
names, TSO attribution -- see `pipeline/45_explore_redispatch_measures.py`
for the analysis this feeds.

Always re-fetches the whole 2021-01-01..today range, same reasoning as
pipeline/43: netztransparenz gives no incremental/delta endpoint, and the
file is a few MB, cheap to re-pull in full each run.
"""

from pecdr.paths import ProjPaths
from pecdr.redispatch_measures import download_redispatch_measures

paths = ProjPaths()
paths.ensure_directories()

csv_bytes = download_redispatch_measures()
paths.redispatch_measures_file.write_bytes(csv_bytes)

print(f"Saved {len(csv_bytes):,} bytes -> {paths.redispatch_measures_file}")
