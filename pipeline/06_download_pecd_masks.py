"""Download PECD v4.2's PEON (onshore wind), PEOF (offshore wind), and NUTS2
region masks.

Pure data acquisition -- no charts. PEON is needed to assign each MaStR wind
unit to its zone (DE01-DE07) for the onshore replication (pipeline/07-09).
PEOF and NUTS2 are needed for the offshore-wind and solar replication phases
respectively (migrated scope, matching
~/research/delu-headline-forecast's pipeline/08+21_download_pecd_*mask*.py).

Same file / request pattern as ~/research/mastr-power-capacities-germany's
pipeline/06_download_pecd_masks.py -- downloaded again here (rather than
reading that project's copy directly) so this project stays runnable
standalone, per the template's per-project self-containment convention.

No `area` restriction: these masks are needed at full European extent so a
unit near the domain edge still has a matching mask cell to snap to.

Requires a ~/.cdsapirc file with a valid CDS API key.
"""

import cdsapi

from pecdr.cds import retrieve_with_retries
from pecdr.paths import ProjPaths

paths = ProjPaths()
paths.ensure_directories()

MASKS = {
    "peon": paths.peon_mask_zip,
    "peof": paths.peof_mask_zip,
    "nuts_2": paths.nuts2_mask_zip,
}

client = cdsapi.Client()

for variable, output_file in MASKS.items():
    if output_file.exists():
        print(f"'{variable}': already downloaded -> {output_file}")
        continue

    request = {
        "pecd_version": "pecd4_2",
        "file_version": "fv1",
        "variable": f"{variable}_region_mask",
    }
    print(f"Requesting '{variable}_region_mask' -> {output_file}")
    retrieve_with_retries(client, "sis-energy-pecd", request, str(output_file))
    print("Done")
