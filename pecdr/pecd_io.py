"""Shared helpers for reading PECD v4.2 CDS downloads (zipped NetCDF).

PECD's gridded/masks-group downloads are ZIPs containing one or more NetCDF
files with long, machine-generated names (e.g.
`H_ERA5_ECMW_T639_WS-_0010m_Pecd_025d_S...PECD4.2_fv1...nc`) -- callers
shouldn't need to know these exact names, just the dataset's own variable
name inside (e.g. `ws10`, `alpha`).
"""

import io
import zipfile
from pathlib import Path

import pandas as pd
import xarray as xr


def extract_zip(zip_path: Path) -> list[Path]:
    """Extract a CDS zip to a sibling `<zip_stem>_extracted/` directory, return its .nc paths.

    Idempotent (skips extraction if the directory already exists). Kept as a
    list of paths rather than pre-opened/merged Datasets: a multi-variable
    combined request's member files often reuse the *same* internal data-var
    name (e.g. every wind-speed climatology grid calls its variable `ws10`
    regardless of ERA5 vs. GWA2 source), so blindly merging would silently
    drop all but one. Callers should pick the file they want by a substring
    in its (CDS-generated, but stable and descriptive) filename.
    """
    extract_dir = zip_path.parent / f"{zip_path.stem}_extracted"
    if not extract_dir.exists():
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(extract_dir)
    nc_files = sorted(extract_dir.glob("*.nc"))
    if not nc_files:
        raise FileNotFoundError(f"No .nc files found inside {zip_path}")
    return nc_files


def open_by_filename_substring(zip_path: Path, substring: str) -> xr.Dataset:
    """Extract `zip_path` and open the one `.nc` member whose filename contains `substring`."""
    matches = [f for f in extract_zip(zip_path) if substring in f.name]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one file containing {substring!r} in {zip_path}, found {len(matches)}")
    return xr.open_dataset(matches[0])


def open_single_zipped_netcdf(zip_path: Path) -> xr.Dataset:
    """Extract `zip_path` and open its one `.nc` member.

    For the common case here (every pipeline/01+02 download is a single
    CDS variable per zip, after abandoning the combined multi-variable
    request -- see those scripts' module docstrings), so there's exactly
    one file and no filename-substring matching is needed.
    """
    nc_files = extract_zip(zip_path)
    if len(nc_files) != 1:
        raise ValueError(f"Expected exactly one .nc file in {zip_path}, found {len(nc_files)}")
    return xr.open_dataset(nc_files[0])


def load_region_timeseries_zip(zip_path: Path, region_prefix: str = "DE") -> pd.DataFrame:
    """Read a PECD region-aggregated-timeseries ZIP (one CSV per year inside) into a wide, hourly-indexed DataFrame.

    Same ZIP/CSV structure ~/research/delu-headline-forecast's `dhf.pecd.load_capacity_factor_zip`
    already established for this exact product family (metadata header rows
    before the real `Date,...` header; region columns like `DE01`..`DE07`
    for PEON). `region_prefix` filters columns down to one country's zones
    instead of loading all of Europe's.
    """
    parts = []
    with zipfile.ZipFile(zip_path) as z:
        for csv_name in z.namelist():
            with z.open(csv_name) as f:
                text = io.TextIOWrapper(f, encoding="utf-8")
                header_idx = next(i for i, line in enumerate(text) if line.startswith("Date,"))
            with z.open(csv_name) as f:
                df = pd.read_csv(
                    f,
                    skiprows=header_idx,
                    parse_dates=["Date"],
                    index_col="Date",
                    usecols=lambda c: c == "Date" or c.startswith(region_prefix),
                )
            parts.append(df)
    combined = pd.concat(parts).sort_index()
    combined.index.name = "timestamp"
    if combined.index.duplicated().any():
        combined = combined[~combined.index.duplicated(keep="first")]
    return combined
