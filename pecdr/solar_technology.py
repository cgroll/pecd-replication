"""Classify MaStR solar units into PECD v4.2's 4 PV technology codes.

PECD publishes solar capacity factor at 4 technology sub-types (see
pipeline/16_download_pecd_capacity_factors.py): 60 = industrial rooftop,
61 = residential rooftop, 62 = utility-scale fixed, 63 = utility-scale
tracking. MaStR doesn't label units with these codes directly, so this
module maps MaStR's own fields to them:

- `installation_type == "Freiflächensolaranlage"` (ground-mounted) is
  PECD's utility-scale segment (62/63) -- split further by whether the
  unit tracks the sun, using `solar_technical_detail.parquet`'s
  `main_orientation`/`main_orientation_tilt_bucket` ("nachgeführt" /
  "Nachgeführt"), since `capacity_events.parquet` itself has no tracking
  flag. Tracking is a small minority of German ground-mounted PV.
- Everything else (rooftop and balcony/"Steckerfertige" installations) is
  PECD's rooftop segment (60/61) -- split by `usage_sector`: "Haushalt"
  (household) is residential (61); any other named sector is industrial
  (60). A missing sector defaults to residential (61) -- this bucket is
  dominated by "Steckerfertige Solaranlage" (balcony) units, which are
  almost always small household installations even when unreported.
"""

import numpy as np
import pandas as pd

GROUND_MOUNTED_INSTALLATION_TYPE = "Freiflächensolaranlage"
HOUSEHOLD_SECTOR = "Haushalt"

TECH_INDUSTRIAL_ROOFTOP = "60"
TECH_RESIDENTIAL_ROOFTOP = "61"
TECH_UTILITY_FIXED = "62"
TECH_UTILITY_TRACKING = "63"


def classify_pecd_technology(installation_type: pd.Series, usage_sector: pd.Series, is_tracked: pd.Series) -> np.ndarray:
    """Vectorized classification into "60"/"61"/"62"/"63" -- see module docstring.

    `installation_type`/`usage_sector` may contain nulls (both columns
    propagate null through `==` rather than comparing unequal, and may be
    categorical dtype), so equality checks use `.eq(...).fillna(False)`
    rather than comparing directly; missing-sector detection happens
    before that fill. `is_tracked` must already be a plain (non-nullable)
    boolean Series.
    """
    is_missing_sector = usage_sector.isna().to_numpy()
    is_ground_mounted = installation_type.eq(GROUND_MOUNTED_INSTALLATION_TYPE).fillna(False).to_numpy()
    is_household = usage_sector.eq(HOUSEHOLD_SECTOR).fillna(False).to_numpy()

    rooftop_tech = np.where(is_household | is_missing_sector, TECH_RESIDENTIAL_ROOFTOP, TECH_INDUSTRIAL_ROOFTOP)
    ground_tech = np.where(is_tracked.to_numpy(), TECH_UTILITY_TRACKING, TECH_UTILITY_FIXED)
    return np.where(is_ground_mounted, ground_tech, rooftop_tech)
