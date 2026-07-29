"""Vectorized full-period solar PV capacity-factor computation -- the
technology- and orientation-aware, PECD-documented physics chain
validated in pipeline/27 (`pecdr.solar_config_physics`), restructured to
run over every hour of every year in `pecdr.domain.FULL_YEAR_BACKTEST_YEARS`
instead of pipeline/27's 3 spot-check days.

Each (region, technology, orientation) config's physics call is cheap
(~7ms for a month of hourly data, dominated by per-call pvlib overhead
rather than array length -- benchmarked directly), so the only structural
change needed from pipeline/27 is calling each config once per *month*
over that month's full hourly series, rather than once per *day*: looping
day-by-day over the full 2019-2025 period would be ~850x more Python-level
calls for no benefit, since the chain itself vectorizes over an
arbitrarily long time index already.
"""

import pandas as pd

from pecdr.solar_config_physics import solar_capacity_factor_for_config
from pecdr.solar_orientation import expand_orientation


def active_configs_for_month(unit_panel: pd.DataFrame, month_end: pd.Timestamp) -> pd.DataFrame:
    """(region, technology, azimuth, tilt, tracked) configs and capacity
    active as of `month_end` -- same vintage rule
    `pipeline/24_build_solar_capacity_by_nuts2_month.py` uses for its own
    monthly capacity panel.
    """
    is_active = (unit_panel["commissioning_date"] <= month_end) & (unit_panel["final_shutdown_date"].isna() | (unit_panel["final_shutdown_date"] > month_end))
    configs = expand_orientation(unit_panel.loc[is_active])
    return configs[configs["capacity_mw"] > 0]


def compute_month_by_tech_region(ghi_region: pd.DataFrame, temp_region: pd.DataFrame, configs: pd.DataFrame, centroids: pd.DataFrame) -> pd.DataFrame:
    """Capacity-weighted (region, technology) capacity factor for one
    month, one column per (technology, region) with any active configs.

    Returns a DataFrame indexed by timestamp, MultiIndex columns
    (pecd_technology, nuts2_region) -- same shape as
    `paths.pecd_solar_capacity_factors_file`.
    """
    columns = {}
    for (region, tech), group in configs.groupby(["nuts2_region", "pecd_technology"], observed=True):
        if region not in ghi_region.columns:
            continue
        total_capacity = group["capacity_mw"].sum()
        weighted_cf = pd.Series(0.0, index=ghi_region.index)
        lat, lon = centroids.loc[region, "lat"], centroids.loc[region, "lon"]
        for row in group.itertuples():
            cf = solar_capacity_factor_for_config(
                ghi_region[region], temp_region[region],
                lat=lat, lon=lon,
                tilt_deg=row.tilt_deg, azimuth_deg=row.azimuth_deg, is_tracked=row.is_tracked,
            )
            weighted_cf = weighted_cf + cf * row.capacity_mw
        columns[(tech, region)] = weighted_cf / total_capacity

    result = pd.DataFrame(columns)
    result.columns = pd.MultiIndex.from_tuples(result.columns, names=["pecd_technology", "nuts2_region"])
    return result
