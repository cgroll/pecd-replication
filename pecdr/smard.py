"""Download hourly SMARD (Bundesnetzagentur) series for the DE-LU market area.

Uses the smard.de web app's JSON endpoints (undocumented, but proven to work
in ~/research/world-of-energy and ~/research/delu-headline-forecast -- see
docs/data_sources.md): a first call lists available block-start timestamps,
a second call fetches each block's actual observations.

Migrated from ~/research/delu-headline-forecast/dhf/smard.py unchanged --
see the data-pipeline migration plan (pecd-replication now owns raw data
acquisition; delu-headline-forecast imports the resulting target panel
directly rather than downloading it itself).
"""

from datetime import datetime
from enum import IntEnum

import pandas as pd
import requests

BASE_URL = "https://www.smard.de/app"
DEFAULT_START_DATE = datetime(2015, 1, 1)


class Variable(IntEnum):
    """SMARD variable IDs for the four headline series."""

    SOLAR = 4068
    WIND_ONSHORE = 4067
    WIND_OFFSHORE = 1225
    TOTAL_LOAD = 410


def download_series(
    variable: Variable,
    region: str = "DE-LU",
    resolution: str = "hour",
    start_time: datetime | None = None,
) -> pd.DataFrame:
    """Download one SMARD series as a UTC-timestamp-indexed single-column DataFrame."""
    index_url = f"{BASE_URL}/chart_data/{variable.value}/{region}/index_{resolution}.json"
    response = requests.get(index_url, timeout=30)
    response.raise_for_status()
    block_timestamps = response.json()["timestamps"]

    if start_time is not None:
        start_ms = int(start_time.timestamp() * 1000)
        block_timestamps = [ts for ts in block_timestamps if ts >= start_ms]

    col = variable.name.lower()
    if not block_timestamps:
        return pd.DataFrame({col: []}, index=pd.DatetimeIndex([], name="timestamp"))

    all_ts_ms: list[int] = []
    all_values: list[float] = []
    for block_ts in block_timestamps:
        data_url = (
            f"{BASE_URL}/chart_data/{variable.value}/{region}/"
            f"{variable.value}_{region}_{resolution}_{block_ts}.json"
        )
        block_response = requests.get(data_url, timeout=30)
        if block_response.status_code != 200:
            continue
        for point_ts_ms, value in block_response.json()["series"]:
            if value is not None:
                all_ts_ms.append(point_ts_ms)
                all_values.append(value)

    # Epoch milliseconds are UTC by definition -- parsed directly rather than
    # via datetime.fromtimestamp(), which depends on the local machine's
    # timezone and isn't reproducible across environments.
    index = pd.to_datetime(all_ts_ms, unit="ms", utc=True).tz_localize(None)
    df = pd.DataFrame({col: all_values}, index=index)
    df.index.name = "timestamp"
    df = df.sort_index()
    return df[~df.index.duplicated(keep="last")]
