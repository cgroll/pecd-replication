"""Shared plant-panel + power-curve setup, used by both the two-snapshot
comparison (pipeline/09) and the full-year comparison (pipeline/10).
"""

import numpy as np
import pandas as pd

from pecdr.paths import ProjPaths
from pecdr.power_curve import (
    capacity_factor_from_library_curve,
    generic_capacity_factor,
    library_cf_curve,
    library_turbines,
    match_turbine_type,
    rated_wind_speed_from_specific_power,
    specific_power_w_m2,
)


def load_plants_with_curves(paths: ProjPaths) -> tuple[pd.DataFrame, dict]:
    """Load the plant panel, match each plant to a public power curve (or fall
    back to the generic specific-power curve), and return it alongside a
    `{matched_type: (wind_speed, capacity_factor)}` curve cache.
    """
    plants = pd.read_parquet(paths.wind_onshore_plant_panel_file)
    plants = plants.dropna(subset=["hub_height_m", "rotor_diameter_m"]).reset_index(drop=True)

    library = library_turbines()
    plants["matched_type"] = plants["turbine_model"].apply(lambda m: match_turbine_type(m, library))

    plants["specific_power_w_m2"] = specific_power_w_m2(plants["capacity_mw"] * 1000, plants["rotor_diameter_m"])
    plants["rated_wind_speed_ms"] = rated_wind_speed_from_specific_power(plants["specific_power_w_m2"])

    curve_cache = {t: library_cf_curve(t) for t in plants["matched_type"].dropna().unique()}
    return plants, curve_cache


def plant_capacity_factor(wind_speed_at_hub: np.ndarray, matched_type: pd.Series, rated_wind_speed_ms: pd.Series, curve_cache: dict) -> np.ndarray:
    """Per-plant capacity factor at `wind_speed_at_hub` (1-D, one value per plant), matched curve where available."""
    cf = np.empty(len(wind_speed_at_hub))
    is_matched = matched_type.notna().to_numpy()
    for t in matched_type[is_matched].unique():
        idx = (matched_type == t).to_numpy()
        ws, curve_cf = curve_cache[t]
        cf[idx] = capacity_factor_from_library_curve(wind_speed_at_hub[idx], ws, curve_cf)
    if (~is_matched).any():
        cf[~is_matched] = generic_capacity_factor(wind_speed_at_hub[~is_matched], rated_wind_speed_ms[~is_matched].to_numpy())
    return cf
