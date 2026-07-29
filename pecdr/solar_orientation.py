"""Expand MaStR solar units into (azimuth, tilt, tracked) configurations.

`solar_technical_detail.parquet`'s `main_orientation`/
`main_orientation_tilt_bucket` are real per-unit values -- finer than
PECD's own approach, which only assumes a per-technology Gaussian
tilt/azimuth distribution (Saint-Drenan et al. 2018). This module turns
those categorical fields into the handful of (region, technology,
azimuth_deg, tilt_deg, is_tracked) configurations `pipeline/27` actually
needs to run physics on -- one config per group of units that would
produce identical modeled output, not one row per unit.

Three cases per unit:
- Tracked (`main_orientation == "nachgeführt"` or
  `main_orientation_tilt_bucket == "Nachgeführt"`): azimuth/tilt are
  determined dynamically by the tracking algorithm, not fixed values.
- "Ost-West" (east-west sawtooth rooftop arrays, common on large
  commercial roofs): doesn't map to one azimuth -- split into two
  half-capacity virtual entries at 90 deg and 270 deg.
- Missing orientation and/or tilt (~20% of units): that capacity is
  redistributed across the *known* (azimuth, tilt) distribution observed
  within the same (nuts2_region, pecd_technology) group, falling back to
  the national per-technology distribution if a region has no known
  values at all for that technology.
"""

import numpy as np
import pandas as pd

AZIMUTH_DEGREES = {
    "Süd": 180.0,
    "Süd-West": 225.0,
    "Süd-Ost": 135.0,
    "West": 270.0,
    "Ost": 90.0,
    "Nord-West": 315.0,
    "Nord-Ost": 45.0,
    "Nord": 0.0,
}
TRACKED_ORIENTATION = "nachgeführt"
EAST_WEST_ORIENTATION = "Ost-West"
EAST_WEST_AZIMUTHS = (90.0, 270.0)

TILT_DEGREES = {
    "unter 5 Grad (horizontal)": 2.5,
    "5 - 20 Grad": 12.5,
    "21 - 40 Grad": 30.0,
    "41 - 60 Grad": 50.0,
    "61 - 89 Grad": 75.0,
    "90 Grad (vertikal)": 90.0,
}
TRACKED_TILT_BUCKET = "Nachgeführt"

GROUP_COLS = ["nuts2_region", "pecd_technology"]
CONFIG_COLS = ["azimuth_deg", "tilt_deg", "is_tracked"]


def expand_orientation(unit_panel: pd.DataFrame) -> pd.DataFrame:
    """Return one row per (unit-or-half-unit, azimuth_deg, tilt_deg, is_tracked).

    `unit_panel` must have `capacity_mw`, `nuts2_region`, `pecd_technology`,
    `main_orientation`, `main_orientation_tilt_bucket`. Total capacity per
    (nuts2_region, pecd_technology) is conserved exactly.
    """
    df = unit_panel.reset_index(drop=True)
    is_tracked = df["main_orientation"].eq(TRACKED_ORIENTATION).fillna(False) | df["main_orientation_tilt_bucket"].eq(TRACKED_TILT_BUCKET).fillna(False)
    tilt_deg = df["main_orientation_tilt_bucket"].map(TILT_DEGREES)
    # Requires a resolved tilt too, not just the east-west azimuth split --
    # an east-west unit with no tilt bucket would otherwise carry a NaN
    # tilt_deg straight into the expanded output (azimuth_deg is already
    # NaN for every "Ost-West" row regardless, since it isn't a key in
    # AZIMUTH_DEGREES). A NaN physics input poisons the *entire*
    # capacity-weighted sum for that (region, technology) group once
    # multiplied in below (NaN + anything = NaN), not just this unit's own
    # share -- routing it through `is_unresolved` instead redistributes
    # its capacity across the group's known (azimuth, tilt) shares, same
    # as any other unit with missing orientation data.
    is_east_west = df["main_orientation"].eq(EAST_WEST_ORIENTATION).fillna(False) & ~is_tracked & tilt_deg.notna()

    azimuth_deg = df["main_orientation"].map(AZIMUTH_DEGREES)
    is_known = ~is_tracked & ~is_east_west & azimuth_deg.notna() & tilt_deg.notna()
    is_unresolved = ~is_tracked & ~is_east_west & ~is_known

    parts = []

    tracked = df.loc[is_tracked, ["capacity_mw", *GROUP_COLS]].copy()
    tracked["azimuth_deg"] = np.nan
    tracked["tilt_deg"] = np.nan
    tracked["is_tracked"] = True
    parts.append(tracked)

    for az in EAST_WEST_AZIMUTHS:
        half = df.loc[is_east_west, ["nuts2_region", "pecd_technology"]].copy()
        half["capacity_mw"] = df.loc[is_east_west, "capacity_mw"].to_numpy() / len(EAST_WEST_AZIMUTHS)
        half["azimuth_deg"] = az
        half["tilt_deg"] = tilt_deg.loc[is_east_west].to_numpy()
        half["is_tracked"] = False
        parts.append(half)

    known = df.loc[is_known, ["capacity_mw", *GROUP_COLS]].copy()
    known["azimuth_deg"] = azimuth_deg.loc[is_known].to_numpy()
    known["tilt_deg"] = tilt_deg.loc[is_known].to_numpy()
    known["is_tracked"] = False
    parts.append(known)

    unresolved_capacity = df.loc[is_unresolved].groupby(GROUP_COLS)["capacity_mw"].sum()
    if len(unresolved_capacity):
        parts.append(_impute_unresolved(unresolved_capacity, known))

    expanded = pd.concat(parts, ignore_index=True)
    expanded = expanded.groupby([*GROUP_COLS, *CONFIG_COLS], as_index=False, dropna=False)["capacity_mw"].sum()
    return expanded


def _impute_unresolved(unresolved_capacity: pd.Series, known: pd.DataFrame) -> pd.DataFrame:
    """Redistribute `unresolved_capacity` (indexed by nuts2_region, pecd_technology)
    across the empirical (azimuth_deg, tilt_deg) shares seen in `known`, per
    (region, technology), falling back to the national per-technology shares.
    """
    by_region_tech = known.groupby([*GROUP_COLS, "azimuth_deg", "tilt_deg"])["capacity_mw"].sum()
    region_tech_totals = by_region_tech.groupby(level=GROUP_COLS).sum()

    by_tech = known.groupby(["pecd_technology", "azimuth_deg", "tilt_deg"])["capacity_mw"].sum()
    tech_totals = by_tech.groupby(level="pecd_technology").sum()

    rows = []
    for (region, tech), missing_mw in unresolved_capacity.items():
        if (region, tech) in region_tech_totals.index:
            shares = by_region_tech.loc[region, tech] / region_tech_totals.loc[(region, tech)]
        else:
            shares = by_tech.loc[tech] / tech_totals.loc[tech]
        for (az, tilt), share in shares.items():
            rows.append({"nuts2_region": region, "pecd_technology": tech, "azimuth_deg": az, "tilt_deg": tilt, "is_tracked": False, "capacity_mw": missing_mw * share})
    return pd.DataFrame(rows)
