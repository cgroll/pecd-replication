"""Download SMARD's monthly redispatch-by-energy-source series.

Since July 2022, SMARD publishes how much feed-in was reduced/increased
under Redispatch 2.0, broken down by energy carrier (wind onshore/offshore,
solar, and the conventional sources) -- monthly, national totals, no
per-TSO/per-plant detail. This is the ground-truth data behind
`pipeline/44_analyse_congestion_curtailment.py`.

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


def download_smard_chart_series(chart_id: str, column_names: list[str], page_url: str = TOPIC_ARTICLE_URL) -> pd.DataFrame:
    """Fetch one arbitrary chart_id's raw rows from SMARD's shared master
    CSV -- wide format, one row per date, one column per name in
    `column_names` (in the order the CSV actually carries them; get this
    order from the topic-article page's `set_locale` legend, not by
    guessing).

    Generalizes `download_redispatch_by_source`'s parsing (used for
    `s-nepm_re_et-1-1/1-2`) to any of the ~130 other chart_ids in the same
    CSV -- e.g. `s-nepm_entw-1-1` (yearly, by measure type),
    `s-nepm_re_eb-1-1x` (TSO vs. DSO), `s-nepm_ct-1-1` (countertrading),
    `s-nepm_nepm-1-1` (aggregate by measure type) -- used by
    `pipeline/44_analyse_congestion_curtailment.py`'s verification section
    and `pipeline/46_attribute_ambiguous_redispatch_entities.py`'s TSO/DSO
    and measure-type analysis.

    Dates are either a bare year ("2015", for the yearly series) or a full
    "YYYY-MM-DD" (for the monthly ones) -- both parse correctly with plain
    `pd.to_datetime`. Empty fields become `NaN`, not `0.0` -- SMARD leaves a
    cell blank when a series didn't exist yet for that period (e.g. a
    technology added to the chart partway through), which is a different
    thing from a genuine zero; callers decide whether to `.dropna()` or
    `.fillna(0)` depending on which meaning applies.
    """
    csv_url = _resolve_csv_url(page_url)
    csv_text = requests.get(csv_url, timeout=30).text

    # The master CSV multiplexes ~130 unrelated chart series with different
    # row widths (some carry a per-Bundesland breakdown instead of
    # per-energy-source) -- parsing the whole file with a fixed column
    # count fails, so only lines matching this specific chart_id's expected
    # width are parsed.
    expected_fields = len(column_names) + 2
    rows = []
    for line in csv_text.splitlines():
        fields = line.split(";")
        if fields[0] != chart_id or len(fields) != expected_fields:
            continue
        row = {"date": pd.to_datetime(fields[1])}
        for name, raw_value in zip(column_names, fields[2:]):
            row[name] = float(raw_value) if raw_value else float("nan")
        rows.append(row)

    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def download_redispatch_by_source(page_url: str = TOPIC_ARTICLE_URL) -> pd.DataFrame:
    """Monthly redispatch volume by energy source, tidy long format:
    columns `month`, `direction` ("reduction"/"increase"), `energy_source`,
    `gwh`.
    """
    tidy_frames = []
    for chart_id, direction in CHART_IDS.items():
        wide = download_smard_chart_series(chart_id, ENERGY_SOURCE_COLUMNS, page_url=page_url)
        tidy = wide.melt(id_vars="date", value_vars=ENERGY_SOURCE_COLUMNS, var_name="energy_source", value_name="gwh")
        tidy = tidy.rename(columns={"date": "month"})
        tidy["direction"] = direction
        tidy_frames.append(tidy.dropna(subset=["gwh"]))

    return pd.concat(tidy_frames)[["month", "direction", "energy_source", "gwh"]].sort_values(
        ["direction", "energy_source", "month"]
    ).reset_index(drop=True)
