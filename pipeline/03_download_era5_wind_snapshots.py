"""Download raw (not bias-corrected) ERA5 10m/100m wind components for the
two milestone-1 snapshot hours (see pecdr/domain.py).

Pure data acquisition -- no charts. This is the "before" side of the
bias-correction replication: pipeline/04_replicate_wind_bias_correction.py
applies our own GWA delta-adjustment to this raw ERA5 pull and compares the
result against PECD's own published bias-corrected grid
(pipeline/02_download_pecd_wind_speed_snapshots.py).

Uses the standard `reanalysis-era5-single-levels` CDS dataset (distinct from
`sis-energy-pecd`, which only re-publishes ERA5 post-bias-correction) -- the
only place raw, uncorrected ERA5 wind speed is available. Unlike
`sis-energy-pecd`'s gridded product, this dataset supports single-hour
requests, so no whole-year download is needed here.

Requires a ~/.cdsapirc file with a valid CDS API key.
"""

import cdsapi

from pecdr.cds import retrieve_with_retries
from pecdr.domain import GERMANY_PEON_AREA, SNAPSHOT_TIMESTAMPS
from pecdr.paths import ProjPaths

paths = ProjPaths()
paths.ensure_directories()

output_file = paths.era5_wind_snapshots_file
if output_file.exists():
    print(f"Already downloaded -> {output_file}")
else:
    months = sorted({ts[5:7] for ts in SNAPSHOT_TIMESTAMPS})
    days = sorted({ts[8:10] for ts in SNAPSHOT_TIMESTAMPS})
    times = sorted({ts[11:16] for ts in SNAPSHOT_TIMESTAMPS})
    years = sorted({ts[:4] for ts in SNAPSHOT_TIMESTAMPS})

    # NOTE: the CDS request is a cartesian product of year x month x day x
    # time, so this will return every combination (e.g. both Jan-15 and
    # Jun-15 at both 00:00 and 12:00), not just the exact two timestamps in
    # SNAPSHOT_TIMESTAMPS -- harmless (the file is tiny either way) and
    # cheaper than one request per timestamp. The analysis script selects
    # the exact two via `.sel(valid_time=...)`.
    request = {
        "product_type": ["reanalysis"],
        "variable": [
            "10m_u_component_of_wind",
            "10m_v_component_of_wind",
            "100m_u_component_of_wind",
            "100m_v_component_of_wind",
        ],
        "year": years,
        "month": months,
        "day": days,
        "time": times,
        "area": GERMANY_PEON_AREA,
        "data_format": "netcdf",
        "download_format": "unarchived",
    }
    print(f"Requesting raw ERA5 wind components for {SNAPSHOT_TIMESTAMPS} -> {output_file}")
    client = cdsapi.Client()
    retrieve_with_retries(client, "reanalysis-era5-single-levels", request, str(output_file))
    print("Done")
