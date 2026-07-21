"""Download the full backtest-period raw ERA5 archive via CDS.

Pure data acquisition -- no charts. Runs `pecdr.era5.download_era5_months_via_cds`
once per calendar quarter from `START_MONTH` to the latest fully-finalized
month ARCO-ERA5 has (used only to read the cutoff date, not for the actual
download), writing one `era5_YYYY-MM.nc` file per month to
data/downloads/era5/.

Migrated from
~/research/delu-headline-forecast/pipeline/23_download_era5_full_period.py
as part of centralizing data acquisition in this project -- see the
migration plan. `pecdr.paths.era5_month_file` is now this project's own
data; delu-headline-forecast reads it directly instead of downloading its
own copy.

**Date range**: starts 2018-10 (SMARD's DE-LU series start), ends at the
last full calendar month ARCO-ERA5 marks as finalized. The last few months
before "now" are excluded as preliminary/revisable.

**Deliberately not wired into `dvc.yaml`**: a multi-hour job (~4.5-5 min per
month, ~90+ months) shouldn't silently run inside every `dvc repro`. Run
directly, once, deliberately, with unbuffered output:

    uv run python -u pipeline/15_download_era5_full_period.py

Safe to Ctrl-C and resume: `download_era5_months_via_cds` skips a whole
quarter if every month in it already has an output file.

Requires a ~/.cdsapirc file with a valid CDS API key.
"""

import cdsapi

from pecdr.era5 import download_era5_months_via_cds, latest_finalized_month, quarter_batches
from pecdr.paths import ProjPaths

paths = ProjPaths()
paths.ensure_directories()

START_MONTH = "2018-10"


def month_range(start_month: str, end_month: str) -> list[str]:
    start_year, start_mon = int(start_month[:4]), int(start_month[5:7])
    end_year, end_mon = int(end_month[:4]), int(end_month[5:7])
    months = []
    year, mon = start_year, start_mon
    while (year, mon) <= (end_year, end_mon):
        months.append(f"{year}-{mon:02d}")
        mon += 1
        if mon > 12:
            mon = 1
            year += 1
    return months


END_MONTH = latest_finalized_month()
months = month_range(START_MONTH, END_MONTH)
batches = quarter_batches(months)
print(f"Downloading {len(months)} months ({months[0]} .. {months[-1]}) in {len(batches)} quarterly CDS requests", flush=True)

client = cdsapi.Client()
failed = []
for i, batch in enumerate(batches, 1):
    print(f"[{i}/{len(batches)}] {batch}", flush=True)
    output_files = {m: paths.era5_month_file(m) for m in batch}
    try:
        download_era5_months_via_cds(batch, output_files, client)
    except Exception as exc:  # noqa: BLE001 - keep going across a many-hour run
        print(f"  FAILED: {batch}: {exc}", flush=True)
        failed.append(batch)

print(f"\nDone. {len(batches) - len(failed)}/{len(batches)} quarterly batches downloaded.", flush=True)
if failed:
    print(f"Failed batches (re-run this script to retry, it will skip the rest): {failed}", flush=True)
