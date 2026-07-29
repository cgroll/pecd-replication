"""Classify every MaStR solar unit into PECD's 4 PV technology codes, and
build a monthly (NUTS2 zone x technology) installed-capacity panel.

Pure data processing script -- no visualizations. MaStR doesn't label
units with PECD's technology codes directly (see
pecdr/solar_technology.py for the classification logic), and the sibling
project's own NUTS2 monthly panel (`capacity_by_nuts2_month.parquet`)
splits by feed-in category instead, so both steps are done here rather
than reused. NUTS2 zone comes from truncating each unit's 5-character
NUTS3 `region_code` to 4 characters -- NUTS3 codes are a strict prefix of
their parent NUTS2 code in Eurostat's NUTS scheme, confirmed against
`pecd_solar_capacity_factors_file`'s own NUTS2 column codes (e.g. "DE11").
Unlike wind, solar units mostly lack coordinates (~95% missing), so this
avoids needing a grid/mask-based zone assignment at all.
"""

import pandas as pd

from pecdr.paths import ProjPaths
from pecdr.solar_technology import classify_pecd_technology

paths = ProjPaths()
paths.ensure_directories()

events = pd.read_parquet(
    paths.mastr_capacity_events_file,
    columns=["unit_id", "technology", "region_code", "capacity_mw", "commissioning_date", "final_shutdown_date", "installation_type", "usage_sector", "pv_category"],
)
solar = events[events["technology"] == "solar"].copy()
print(f"Solar units: {len(solar):,}, total capacity {solar['capacity_mw'].sum():,.0f} MW")

detail = pd.read_parquet(paths.mastr_solar_technical_detail_file, columns=["unit_id", "main_orientation", "main_orientation_tilt_bucket"])
solar = solar.merge(detail, on="unit_id", how="left")

is_tracked = solar["main_orientation"].eq("nachgeführt").fillna(False) | solar["main_orientation_tilt_bucket"].eq("Nachgeführt").fillna(False)
solar["nuts2_region"] = solar["region_code"].str[:4]
solar["pecd_technology"] = classify_pecd_technology(solar["installation_type"], solar["usage_sector"], is_tracked)

print("Capacity (MW) by PECD technology (60=industrial roof, 61=residential roof, 62=utility fixed, 63=utility tracking):")
print(solar.groupby("pecd_technology")["capacity_mw"].sum())

unit_panel = solar[
    ["unit_id", "capacity_mw", "nuts2_region", "pecd_technology", "pv_category", "main_orientation", "main_orientation_tilt_bucket", "commissioning_date", "final_shutdown_date"]
]
unit_panel.to_parquet(paths.solar_unit_technology_file, index=False)
print(f"Saved unit-level panel -> {paths.solar_unit_technology_file}")

# --- Monthly (nuts2_region, pecd_technology, month) capacity panel, plus a
# national (pv_category, month) panel for the self-consumption-share bias
# check in pipeline/26 -- both need the same per-month "active" mask, so
# built in the same loop rather than scanning the unit panel twice. ---
month_ends = pd.date_range("2015-01-31", pd.Timestamp.today().normalize(), freq="ME")

monthly_rows, pv_category_rows = [], []
for month_end in month_ends:
    is_active = (solar["commissioning_date"] <= month_end) & (solar["final_shutdown_date"].isna() | (solar["final_shutdown_date"] > month_end))
    active = solar.loc[is_active]

    snapshot = active.groupby(["nuts2_region", "pecd_technology"])["capacity_mw"].sum().reset_index()
    snapshot["month"] = month_end
    monthly_rows.append(snapshot)

    pv_category_snapshot = active.groupby("pv_category", observed=True)["capacity_mw"].sum().reset_index()
    pv_category_snapshot["month"] = month_end
    pv_category_rows.append(pv_category_snapshot)

monthly = pd.concat(monthly_rows, ignore_index=True)
monthly.to_parquet(paths.solar_capacity_by_nuts2_month_file, index=False)
print(f"Saved monthly panel: {len(monthly):,} rows ({month_ends[0]:%Y-%m} .. {month_ends[-1]:%Y-%m}) -> {paths.solar_capacity_by_nuts2_month_file}")

pv_category_monthly = pd.concat(pv_category_rows, ignore_index=True)
pv_category_monthly.to_parquet(paths.solar_capacity_by_pv_category_month_file, index=False)
print(f"Saved national pv_category panel: {len(pv_category_monthly):,} rows -> {paths.solar_capacity_by_pv_category_month_file}")
