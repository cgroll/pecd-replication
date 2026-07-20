"""Download PECD v4.2's PEON (pan-European onshore wind zone) region mask.

Pure data acquisition -- no charts. Needed to assign each MaStR wind unit to
its PEON zone (DE01-DE07 for Germany) by nearest grid cell + dominant zone
fraction, so per-plant power output can be aggregated to zone level and
compared against pipeline/07's PEON capacity-factor ground truth.

Same file / request as ~/research/mastr-power-capacities-germany's
pipeline/06_download_pecd_masks.py -- downloaded again here (rather than
reading that project's copy directly) so this project stays runnable
standalone, per the template's per-project self-containment convention.

No `area` restriction: unlike the gridded wind-speed downloads, this mask is
needed at full European extent so a MaStR unit near the domain edge still
has a matching mask cell to snap to.

Requires a ~/.cdsapirc file with a valid CDS API key.
"""

import cdsapi

from pecdr.cds import retrieve_with_retries
from pecdr.paths import ProjPaths

paths = ProjPaths()
paths.ensure_directories()

output_file = paths.peon_mask_zip
if output_file.exists():
    print(f"Already downloaded -> {output_file}")
else:
    request = {
        "pecd_version": "pecd4_2",
        "file_version": "fv1",
        "variable": "peon_region_mask",
    }
    print(f"Requesting 'peon_region_mask' -> {output_file}")
    client = cdsapi.Client()
    retrieve_with_retries(client, "sis-energy-pecd", request, str(output_file))
    print("Done")
