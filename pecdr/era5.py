"""Download raw ERA5 grid data via CDS.

Migrated from ~/research/delu-headline-forecast/dhf/era5.py (CDS-download
portion only -- see the migration plan). delu's `mask_weighted_regional_mean`/
`grid_cell_capacity_weighted_features`/physics-feature helpers stay there for
now, migrated alongside `dhf/physics.py` in a later phase.
"""

import shutil
import tempfile
import zipfile
from pathlib import Path

import cdsapi
import pandas as pd
import xarray as xr

# Public GCS Zarr store -- read here only for its `valid_time_stop` metadata
# (the latest finalized month), not for actual data download (CDS is
# 5-8x faster for this project's small region + 6 variables, see
# `download_era5_months_via_cds`).
ERA5_STORE = "gs://gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3"

# Rounded outward (1 degree margin) from the exact bounding box of Germany's
# PEON/PEOF zone masks.
ERA5_LAT_MIN, ERA5_LAT_MAX = 47.0, 56.0
ERA5_LON_MIN, ERA5_LON_MAX = 3.0, 15.0

ERA5_VARIABLES = [
    "100m_u_component_of_wind",
    "100m_v_component_of_wind",
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    "surface_solar_radiation_downwards",
    "2m_temperature",
]

CDS_DATASET = "reanalysis-era5-single-levels"

# CDS's netCDF output splits into two files by ERA5 "step type" (instantaneous
# fields like wind/temperature vs. hourly-accumulated fields like solar
# radiation) inside one zip, uses short GRIB-derived variable names, and
# calls the time coordinate "valid_time" -- rename everything to the
# long-form ERA5_VARIABLES names so every downstream consumer works
# identically regardless of which source a given month came from.
CDS_RENAME = {
    "u100": "100m_u_component_of_wind",
    "v100": "100m_v_component_of_wind",
    "u10": "10m_u_component_of_wind",
    "v10": "10m_v_component_of_wind",
    "t2m": "2m_temperature",
    "ssrd": "surface_solar_radiation_downwards",
    "valid_time": "time",
}


def latest_finalized_month() -> str:
    """Latest calendar month ARCO-ERA5 marks as finalized ("YYYY-MM"), read from
    its own metadata rather than hardcoded -- only the metadata is read, no data.
    """
    ds = xr.open_zarr(ERA5_STORE, storage_options={"token": "anon"}, chunks=None, decode_timedelta=True)
    finalized_stop = pd.Timestamp(ds.attrs["valid_time_stop"])
    ds.close()
    last_full_month = finalized_stop - pd.offsets.MonthBegin(1) if finalized_stop.day < 28 else finalized_stop
    return f"{last_full_month.year}-{last_full_month.month:02d}"


def quarter_batches(months: list[str]) -> list[list[str]]:
    """Group a list of "YYYY-MM" months into consecutive same-calendar-quarter batches."""
    batches: list[list[str]] = []
    current: list[str] = []
    current_quarter = None
    for month in months:
        year, mon = int(month[:4]), int(month[5:7])
        quarter = (year, (mon - 1) // 3)
        if quarter != current_quarter:
            if current:
                batches.append(current)
            current = []
            current_quarter = quarter
        current.append(month)
    if current:
        batches.append(current)
    return batches


def download_era5_months_via_cds(months: list[str], output_files: dict[str, Path], client: cdsapi.Client) -> None:
    """Download `months` (must all share one calendar quarter -- see `quarter_batches`)
    in a single CDS request, then split into one file per month.

    No-op (skips the CDS request) if every month's output file already exists.
    """
    if all(f.exists() for f in output_files.values()):
        print(f"{months}: already downloaded", flush=True)
        return

    years = sorted({m[:4] for m in months})
    assert len(years) == 1, f"a CDS batch must stay within one year, got {months}"

    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        zip_path = tmp_dir / "era5.zip"
        print(f"{months}: requesting from CDS ...", flush=True)
        client.retrieve(
            CDS_DATASET,
            {
                "product_type": "reanalysis",
                "format": "netcdf",
                "variable": ERA5_VARIABLES,
                "year": years[0],
                "month": [m[5:7] for m in months],
                "day": [f"{d:02d}" for d in range(1, 32)],
                "time": [f"{h:02d}:00" for h in range(24)],
                "area": [ERA5_LAT_MAX, ERA5_LON_MIN, ERA5_LAT_MIN, ERA5_LON_MAX],
            },
            str(zip_path),
        )

        with zipfile.ZipFile(zip_path) as z:
            z.extractall(tmp_dir)

        instant = xr.open_dataset(tmp_dir / "data_stream-oper_stepType-instant.nc")
        accum = xr.open_dataset(tmp_dir / "data_stream-oper_stepType-accum.nc")
        combined = (
            xr.merge([instant, accum], compat="override", join="inner")
            .drop_vars("expver", errors="ignore")
            .rename(CDS_RENAME)
        )

        for month in months:
            output_file = output_files[month]
            if output_file.exists():
                print(f"{month}: already downloaded -> {output_file}", flush=True)
                continue
            tmp_file = output_file.with_suffix(".nc.tmp")
            combined.sel(time=month).to_netcdf(tmp_file)
            shutil.move(tmp_file, output_file)
            size_mb = output_file.stat().st_size / 1e6
            print(f"{month}: saved -> {output_file} ({size_mb:.1f} MB)", flush=True)
