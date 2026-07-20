"""Download PECD v4.2's own bias-corrected gridded 10m/100m wind speed --
the ground truth for pipeline/04_replicate_wind_bias_correction.py.

Pure data acquisition -- no charts. `sis-energy-pecd`'s gridded historical
variables (`spatial_resolution=0_25_degree`) have no month-level subsetting
for a past year (confirmed via the CDS constraints API: the `month` key only
applies to the current, in-progress year) -- so this downloads the full
SNAPSHOT_YEAR at hourly resolution, restricted to Germany's PEON bounding
box (~1.7% of the full PECD domain, see pecdr/domain.py), and the analysis
script selects out just the two snapshot timestamps.

One request per height (10m, 100m) -- requesting both together was tried
first and abandoned for the same reason as
pipeline/01_download_pecd_wind_bias_reference.py: the combined job sat
queued with zero response for 20+ minutes.

The downloaded file's own `history` NetCDF attribute confirms this is
genuinely post-bias-correction (confirmed by inspection of the 10m file):
it records "Bias adjustment with mean delta method" and "Removed drop at 10
UTC" as processing steps already applied, matching the PUG's description
exactly.

Requires a ~/.cdsapirc file with a valid CDS API key.
"""

import cdsapi

from pecdr.cds import retrieve_with_retries
from pecdr.domain import GERMANY_PEON_AREA, SNAPSHOT_YEAR
from pecdr.paths import ProjPaths

paths = ProjPaths()
paths.ensure_directories()

HEIGHTS_M = [10, 100]

client = cdsapi.Client()

for height_m in HEIGHTS_M:
    output_file = paths.pecd_wind_speed_zip(height_m, SNAPSHOT_YEAR)
    if output_file.exists():
        print(f"{height_m}m: already downloaded -> {output_file}")
        continue

    request = {
        "pecd_version": "pecd4_2",
        "temporal_period": "historical",
        "origin": "era5_reanalysis",
        "variable": f"{height_m}m_wind_speed",
        "spatial_resolution": "0_25_degree",
        "year": SNAPSHOT_YEAR,
        "file_version": "fv1",
        "area": GERMANY_PEON_AREA,
    }
    print(f"Requesting {height_m}m wind speed for {SNAPSHOT_YEAR} -> {output_file}")
    retrieve_with_retries(client, "sis-energy-pecd", request, str(output_file))
    print(f"  Done -> {output_file}")

print("All PECD wind-speed ground-truth grids downloaded.")
