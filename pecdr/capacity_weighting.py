"""Broadcast a monthly capacity panel to hourly and use it to weight a
zone-level capacity-factor series.

Same pattern already established in ~/research/delu-headline-forecast's
`dhf.pecd` module, duplicated here (not imported cross-repo, per this
project's self-containment convention) -- generic enough to weight PECD's
own zone capacity factor, delu's own-physics zone capacity factor, or a
SMARD-implied one, all by MaStR's *actual time-varying* installed capacity
rather than a fixed "active today" snapshot. That distinction matters for
any comparison against a historical actuals series (e.g. SMARD): applying
today's larger fleet retroactively to, say, 2020 would inflate a
denominator that was smaller back then.
"""

import pandas as pd


def hourly_capacity_by_zone(capacity_by_zone_month: pd.DataFrame, target_index: pd.DatetimeIndex, zone_col: str = "region_code") -> pd.DataFrame:
    """Broadcast a monthly (zone, month, capacity_mw) panel to `target_index`'s hourly resolution.

    Capacity is held constant within each calendar month, matching MaStR's
    own resolution.
    """
    wide = (
        capacity_by_zone_month.assign(year_month=lambda d: d["month"].dt.to_period("M"))
        .groupby(["year_month", zone_col])["capacity_mw"]
        .sum()
        .unstack(zone_col)
    )
    hourly = wide.reindex(target_index.to_period("M"))
    hourly.index = target_index
    return hourly


def capacity_weighted_cf(capacity_factor: pd.DataFrame, capacity_by_zone_month: pd.DataFrame, zone_col: str = "region_code") -> pd.Series:
    """Capacity-weighted mean capacity factor, hourly, using time-varying zone capacity.

    Zones present in one input but not the other are dropped (treated as
    zero-weight), same as `dhf.pecd.national_capacity_weighted_cf`.
    """
    capacity_hourly = hourly_capacity_by_zone(capacity_by_zone_month, capacity_factor.index, zone_col)
    common = capacity_factor.columns.intersection(capacity_hourly.columns)
    cf, cap = capacity_factor[common], capacity_hourly[common]
    return (cf * cap).sum(axis=1) / cap.sum(axis=1)


def total_hourly_capacity(capacity_by_zone_month: pd.DataFrame, target_index: pd.DatetimeIndex, zone_col: str = "region_code") -> pd.Series:
    """Total installed capacity (MW), hourly, summed across all zones in the panel."""
    return hourly_capacity_by_zone(capacity_by_zone_month, target_index, zone_col).sum(axis=1)


def average_across_technologies(capacity_factor: pd.DataFrame) -> pd.DataFrame:
    """Collapse a (technology, region) MultiIndex-column solar CF frame to one CF per region.

    Simple unweighted mean across PECD's 4 solar technology sub-types --
    there's no MaStR capacity split by technology (only by behind-the-meter
    category) to weight them by, so this is the "approach 1" simplification
    (see pipeline/12_compare_all_approaches.py). Migrated from
    ~/research/delu-headline-forecast's `dhf.pecd.average_across_technologies`.
    """
    return capacity_factor.T.groupby(level="region").mean().T
