"""Download PECD v4.2 2m temperature, country level (NUTS0), 2015-2025.

Pure data acquisition -- no charts. For a `load` target: PECD's
population-weighted temperature product isn't usable here (v4.2 only offers
it at the pan-European "synchronous zone" resolution -- Germany's zone,
Continental Europe, spans ~20 countries), so this uses plain area-average
2m temperature at NUTS0 instead.

Two requests, not one: this variable/resolution combo splits across
`file_version` by year range (fv2 -> 1950-2021, fv1 -> 2022-2025) -- a
single fv1 request spanning both silently drops the pre-2022 years instead
of erroring, so each file_version is requested separately and combined at
processing time (pipeline/19_process_pecd_temperature.py).

Migrated from
~/research/delu-headline-forecast/pipeline/14_download_pecd_temperature.py.

Requires a ~/.cdsapirc file with a valid CDS API key.
"""

import cdsapi

from pecdr.cds import retrieve_with_retries
from pecdr.paths import ProjPaths

paths = ProjPaths()
paths.ensure_directories()

MONTHS = [f"{m:02d}" for m in range(1, 13)]

REQUESTS = {
    "fv2": [str(y) for y in range(2015, 2022)],
    "fv1": [str(y) for y in range(2022, 2026)],
}

client = cdsapi.Client()

for file_version, years in REQUESTS.items():
    output_file = paths.pecd_temperature_zip(file_version)
    if output_file.exists():
        print(f"{file_version}: already downloaded -> {output_file}")
        continue

    request = {
        "pecd_version": "pecd4_2",
        "temporal_period": "historical",
        "origin": "era5_reanalysis",
        "variable": "2m_temperature",
        "spatial_resolution": "nuts_0",
        "year": years,
        "month": MONTHS,
        "file_version": file_version,
    }
    print(f"{file_version}: requesting 2m_temperature {years[0]}-{years[-1]} ...")
    retrieve_with_retries(client, "sis-energy-pecd", request, str(output_file))
    print(f"  saved -> {output_file}")
