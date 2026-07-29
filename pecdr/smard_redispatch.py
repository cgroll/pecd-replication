"""Download SMARD's monthly redispatch-by-energy-source series.

Since July 2022, SMARD publishes how much feed-in was reduced/increased
under Redispatch 2.0, broken down by energy carrier (wind onshore/offshore,
solar, and the conventional sources) -- monthly, national totals, no
per-TSO/per-plant detail. This is the ground-truth data behind
`book/markdown/congestion_curtailment_data.md`.

Unlike the rest of this project's SMARD data (`pecdr/smard.py`'s
`chart_data` JSON API), this series has no documented API endpoint -- the
frontend instead multiplexes ~130 different chart series into one shared
CSV, selected client-side by a `chart_id` column. That CSV's URL is a
CoreMedia resource ID (e.g. `/resource/blob/217306/-/data-csv-data.csv`)
which rotates on site republish, so it's resolved from the live topic-article
page each run rather than hardcoded: the page loads a shared `mod_urls.js`
that defines `URLS.data` to the current path -- the same two-hop lookup the
browser itself performs.
"""

import re

import pandas as pd
import requests

TOPIC_ARTICLE_URL = "https://www.smard.de/page/en/topic-article/212250/214114/redispatching-by-energy-source"

# Column order confirmed against the topic-article page's embedded
# `set_locale` chart legend (`series: [...]`), not just the CSV itself --
# the CSV has no header row.
ENERGY_SOURCE_COLUMNS = [
    "Wind_Offshore",
    "Wind_Onshore",
    "Braunkohle",
    "Photovoltaik",
    "Steinkohle",
    "Erdgas",
    "Kernenergie",
    "Biomasse",
    "Pumpspeicher",
    "Wasserkraft",
    "Sonstige_Erneuerbare",
    "Sonstige_Konventionelle",
    "Unbekannt",
]

# "Redispatch Reduzierungen/Erhöhungen pro Energieträger" -- reductions are
# curtailment-down (our primary interest); increases are counter-trading
# up-regulation, kept for context (expected to be dominated by conventional
# sources, not renewables).
CHART_IDS = {"s-nepm_re_et-1-1": "reduction", "s-nepm_re_et-1-2": "increase"}


def _resolve_csv_url(page_url: str = TOPIC_ARTICLE_URL) -> str:
    """Re-derive the current CSV blob URL from the live page rather than
    hardcoding it -- see module docstring.
    """
    page_html = requests.get(page_url, timeout=30).text
    mod_urls_match = re.search(r'src="(//www\.smard\.de[^"]*mod_urls[^"]*\.js)"', page_html)
    if mod_urls_match is None:
        raise RuntimeError(f"Could not find mod_urls.js reference on {page_url}")
    mod_urls_js = requests.get("https:" + mod_urls_match.group(1), timeout=30).text
    data_path_match = re.search(r'data:\s*"([^"]+)"', mod_urls_js)
    if data_path_match is None:
        raise RuntimeError("Could not find URLS.data in mod_urls.js")
    return f"https://www.smard.de{data_path_match.group(1)}"


def download_redispatch_by_source(page_url: str = TOPIC_ARTICLE_URL) -> pd.DataFrame:
    """Monthly redispatch volume by energy source, tidy long format:
    columns `month`, `direction` ("reduction"/"increase"), `energy_source`,
    `gwh`.
    """
    csv_url = _resolve_csv_url(page_url)
    csv_text = requests.get(csv_url, timeout=30).text

    # The master CSV multiplexes ~130 unrelated chart series with different
    # row widths (some carry a per-Bundesland breakdown instead of
    # per-energy-source) -- parsing the whole file with a fixed column
    # count fails, so only lines for the two chart_ids of interest are
    # parsed here, each of which is known to have exactly len(ENERGY_SOURCE_COLUMNS) + 2 fields.
    expected_fields = len(ENERGY_SOURCE_COLUMNS) + 2
    rows = []
    for line in csv_text.splitlines():
        fields = line.split(";")
        chart_id = fields[0]
        if chart_id not in CHART_IDS or len(fields) != expected_fields:
            continue
        direction = CHART_IDS[chart_id]
        month = pd.to_datetime(fields[1])
        for energy_source, raw_value in zip(ENERGY_SOURCE_COLUMNS, fields[2:]):
            if raw_value == "":
                continue
            rows.append({"month": month, "direction": direction, "energy_source": energy_source, "gwh": float(raw_value)})

    return pd.DataFrame(rows).sort_values(["direction", "energy_source", "month"]).reset_index(drop=True)
