"""Download PECD v4.2's own static wind bias-correction reference grids.

Pure data acquisition -- no charts. These are the "Weights and masks" group
variables from the `sis-energy-pecd` CDS dataset (same group the PEON/PEOF
zone masks come from in ~/research/mastr-power-capacities-germany), each
static (no year/month dimension):

- `climatology_of_era5_10m_wind_speed` / `_100m_wind_speed`: ERA5's own
  long-run mean wind speed per grid cell, over PECD's reference period.
- `climatology_of_gwa2_10m_wind_speed` / `_100m_wind_speed`: the same, from
  the Global Wind Atlas v2. Per the PUG, PECD's Delta Adjustment factor is
  the per-cell ratio GWA2/ERA5 of these two -- downloading PECD's own
  climatology grids lets us recompute that exact ratio ourselves rather than
  sourcing raw GWA rasters independently and hoping our own reference-period
  and regridding choices match theirs.
- `power_law_coefficient`: PECD's own precomputed wind-shear (alpha) grid,
  stratified by hour-of-day x month (24x12=288 time steps). Used directly
  rather than re-derived -- the derivation formula is trivial/unambiguous,
  so re-deriving it only risks numerical mismatches for no benefit.

One CDS request per variable, restricted to Germany's PEON bounding box via
`area` (see pecdr/domain.py). Requesting all 5 in a single combined call was
tried first and abandoned: the CDS job sat queued with zero response (not
even a "request accepted" log line) for 20+ minutes, vs. ~3-8 min per
variable when requested individually -- likely because these masks-group
variables aren't pre-bundled server-side the way, e.g., a single year of
timeseries data is.

Requires a ~/.cdsapirc file with a valid CDS API key.
"""

import cdsapi

from pecdr.cds import retrieve_with_retries
from pecdr.domain import GERMANY_PEON_AREA
from pecdr.paths import ProjPaths

paths = ProjPaths()
paths.ensure_directories()

VARIABLES = {
    "climatology_era5_10m": "climatology_of_era5_10m_wind_speed",
    "climatology_era5_100m": "climatology_of_era5_100m_wind_speed",
    "climatology_gwa2_10m": "climatology_of_gwa2_10m_wind_speed",
    "climatology_gwa2_100m": "climatology_of_gwa2_100m_wind_speed",
    "power_law_coefficient": "power_law_coefficient",
}

client = cdsapi.Client()

for name, variable in VARIABLES.items():
    output_file = paths.wind_bias_reference_zip(name)
    if output_file.exists():
        print(f"'{name}': already downloaded -> {output_file}")
        continue

    request = {
        "pecd_version": "pecd4_2",
        "file_version": "fv1",
        "variable": variable,
        "area": GERMANY_PEON_AREA,
    }
    print(f"Requesting '{variable}' -> {output_file}")
    retrieve_with_retries(client, "sis-energy-pecd", request, str(output_file))
    print(f"  Done -> {output_file}")

print("All bias-reference grids downloaded.")
