"""Download PECD v4.2 capacity factor time series: solar PV (NUTS2) and wind
onshore/offshore (PEON/PEOF), 2015-2025.

Pure data acquisition -- no charts. One CDS request per (variable,
technology) combination, each covering all requested years in a single
call. Downloads, at hourly resolution:

  - Solar PV capacity factor at NUTS2, all 4 technology sub-types (60/61/62/63:
    industrial rooftop, residential rooftop, utility fixed, utility tracker) --
    no energy_scenario; roughly mirrors MaStR's behind-the-meter split.
  - Wind onshore capacity factor at PEON zones, technology 30 ("Existing
    technologies"), energy_scenario=resource_grade_b.
  - Wind offshore capacity factor at PEOF zones, technology 20 ("Existing
    technologies"), energy_scenario=resource_grade_b.

Migrated from
~/research/delu-headline-forecast/pipeline/10_download_pecd_capacity_factors.py
as part of centralizing data acquisition -- see the migration plan. Broader
in scope (multi-year, solar + offshore) than
pipeline/07_download_pecd_peon_capacity_factor.py, which stays as-is since
the already-validated onshore replication pipeline depends on it.

Requires a ~/.cdsapirc file with a valid CDS API key.
"""

import cdsapi

from pecdr.cds import retrieve_with_retries
from pecdr.paths import ProjPaths

paths = ProjPaths()
paths.ensure_directories()

YEARS = [str(y) for y in range(2015, 2026)]
MONTHS = [f"{m:02d}" for m in range(1, 13)]

REQUESTS = {
    "solar_tech60": ("solar", "60"),
    "solar_tech61": ("solar", "61"),
    "solar_tech62": ("solar", "62"),
    "solar_tech63": ("solar", "63"),
    "wind_onshore_tech30": ("wind_onshore", "30"),
    "wind_offshore_tech20": ("wind_offshore", "20"),
}

VARIABLE_NAMES = {
    "solar": "solar_photovoltaic_generation_capacity_factor",
    "wind_onshore": "wind_power_onshore_capacity_factor",
    "wind_offshore": "wind_power_offshore_capacity_factor",
}

SPATIAL_RESOLUTION = {
    "solar": "nuts_2",
    "wind_onshore": "peon",
    "wind_offshore": "peof",
}

client = cdsapi.Client()

for label, (kind, technology) in REQUESTS.items():
    output_file = paths.pecd_capacity_factor_zip(kind, technology)
    if output_file.exists():
        print(f"{label}: already downloaded -> {output_file}")
        continue

    request = {
        "pecd_version": "pecd4_2",
        "temporal_period": "historical",
        "origin": "era5_reanalysis",
        "variable": VARIABLE_NAMES[kind],
        "technology": technology,
        "spatial_resolution": SPATIAL_RESOLUTION[kind],
        "year": YEARS,
        "month": MONTHS,
        "file_version": "fv1",
    }
    if kind != "solar":
        request["energy_scenario"] = "resource_grade_b"

    print(f"{label}: requesting {YEARS[0]}-{YEARS[-1]} ...")
    retrieve_with_retries(client, "sis-energy-pecd", request, str(output_file))
    print(f"  saved -> {output_file}")
