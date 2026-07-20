"""Download PECD v4.2's own wind-onshore capacity factor at PEON zones --
the ground truth for the full wind-onshore replication (grid -> plant
power -> PEON zone aggregate).

Pure data acquisition -- no charts. `technology=30` ("Existing
technologies") is the only option representing the currently-installed
fleet rather than a hypothetical future build, and is only offered under
`energy_scenario=resource_grade_b` (confirmed via the CDS constraints, same
as ~/research/delu-headline-forecast's pipeline/10_download_pecd_capacity_factors.py).

Region-aggregated timeseries products (PEON here, unlike the gridded 0.25
degree products in pipeline/01-02) are not restricted by `area` -- the CDS
form explicitly states area sub-setting only applies to gridded products
-- so this downloads all of Europe's PEON zones for SNAPSHOT_YEAR; the
zip/CSV is filtered down to Germany's DE01-DE07 columns at load time
(`pecdr.pecd_io.load_region_timeseries_zip`).

Requires a ~/.cdsapirc file with a valid CDS API key.
"""

import cdsapi

from pecdr.cds import retrieve_with_retries
from pecdr.domain import SNAPSHOT_YEAR
from pecdr.paths import ProjPaths

paths = ProjPaths()
paths.ensure_directories()

output_file = paths.pecd_peon_capacity_factor_zip(SNAPSHOT_YEAR)
if output_file.exists():
    print(f"Already downloaded -> {output_file}")
else:
    request = {
        "pecd_version": "pecd4_2",
        "temporal_period": "historical",
        "origin": "era5_reanalysis",
        "variable": "wind_power_onshore_capacity_factor",
        "technology": "30",
        "energy_scenario": "resource_grade_b",
        "spatial_resolution": "peon",
        "year": SNAPSHOT_YEAR,
        "month": [f"{m:02d}" for m in range(1, 13)],
        "file_version": "fv1",
    }
    print(f"Requesting PEON wind-onshore capacity factor for {SNAPSHOT_YEAR} -> {output_file}")
    client = cdsapi.Client()
    retrieve_with_retries(client, "sis-energy-pecd", request, str(output_file))
    print("Done")
