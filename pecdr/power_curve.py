"""Per-plant wind power curve: a matched public (OEDB, via `windpowerlib`)
curve where possible, a generic specific-power-parametrized curve otherwise.

PECD's own approach builds a per-plant power curve from a proprietary
database (WindPowerNet) with ML-imputed hub heights/turbine types where
missing -- not available to us. The substitute here mirrors PECD's own
fallback for its "future technology" categories (which have no real
installed-turbine database to draw on either): a generic curve
parametrized by specific power (rated power / rotor swept area), which
determines roughly where the curve's cut-in-to-rated ramp sits. Empirically
(see project discussion), only ~44% of MaStR's onshore wind capacity has an
exact match in the public OEDB library (67 turbine types) -- most of the
fleet uses the generic fallback.

No explicit wake modeling and no per-turbine storm-shutdown database
(WindPowerNet-specific) -- see pecdr/shutdown.py for the simplified
probabilistic cutoff used instead, and pipeline/09 for the flat "other
losses" derate.
"""

import numpy as np
import pandas as pd
from windpowerlib import WindTurbine, get_turbine_types

AIR_DENSITY_KG_M3 = 1.225  # matches PECD's own fixed assumption (per the PUG)
GENERIC_CUT_IN_MS = 3.0
GENERIC_CUT_OUT_MS = 25.0
GENERIC_MAX_CP = 0.45  # typical modern turbine peak power coefficient, used only to place the rated wind speed

# Flat non-wake "other losses" derate (electrical, availability, blade
# soiling, etc.) -- PECD applies a country-varying value (~5-15%, see PUG);
# simplified here to one representative flat value rather than a
# per-country table, per the project's "skip explicit wake/loss detail"
# simplification.
OTHER_LOSSES_FRACTION = 0.10


def library_turbines() -> pd.DataFrame:
    """OEDB turbine types with a usable power curve (via `windpowerlib.get_turbine_types`)."""
    lib = get_turbine_types(print_out=False)
    return lib[lib["has_power_curve"]].reset_index(drop=True)


def match_turbine_type(turbine_model, library: pd.DataFrame) -> str | None:
    """Try to match a MaStR `turbine_model` string to one OEDB `turbine_type`.

    MaStR model strings (e.g. "E-101", "V90", "SWT-3.6-120") and OEDB type
    strings (e.g. "E-101/3050", manufacturer/model/rated_power_kw) use
    different conventions -- matched by whether one is a prefix of the
    other after stripping spaces/hyphens, checked against the OEDB type's
    model segment (before the "/rated_power" suffix).
    """
    if pd.isna(turbine_model):
        return None
    model_clean = str(turbine_model).upper().replace(" ", "").replace("-", "")
    for lt in library["turbine_type"]:
        lt_clean = str(lt).upper().replace("-", "")
        lt_prefix = lt_clean.split("/")[0]
        if not lt_prefix:
            continue
        if lt_clean.replace("/", "") == model_clean or model_clean.startswith(lt_prefix) or lt_prefix.startswith(model_clean):
            return lt
    return None


def library_cf_curve(turbine_type: str, hub_height_m: float = 100) -> tuple[np.ndarray, np.ndarray]:
    """(wind_speed, capacity_factor) arrays for one OEDB turbine type.

    `hub_height_m` only affects windpowerlib's optional density/roughness
    corrections (unused here -- we apply our own hub-height wind speed
    upstream via pecdr.hub_height), so any placeholder value works; passed
    through because `WindTurbine` requires it.
    """
    wt = WindTurbine(turbine_type=turbine_type, hub_height=hub_height_m)
    curve = wt.power_curve.sort_values("wind_speed")
    return curve["wind_speed"].to_numpy(), (curve["value"].to_numpy() / wt.nominal_power)


def specific_power_w_m2(rated_power_kw: float, rotor_diameter_m: float) -> float:
    """Rated power per unit rotor swept area, in W/m^2."""
    swept_area_m2 = np.pi * (rotor_diameter_m / 2) ** 2
    return rated_power_kw * 1000 / swept_area_m2


def rated_wind_speed_from_specific_power(specific_power: float, max_cp: float = GENERIC_MAX_CP, air_density: float = AIR_DENSITY_KG_M3) -> float:
    """Actuator-disk estimate of the wind speed at which a generic turbine reaches rated power.

    specific_power = 0.5 * air_density * max_cp * v_rated**3
    => v_rated = (specific_power / (0.5 * air_density * max_cp)) ** (1/3)

    Same trick PECD itself uses for its "future technology" categories
    (parametrized by specific power rather than a named real turbine).
    """
    return (specific_power / (0.5 * air_density * max_cp)) ** (1 / 3)


def generic_capacity_factor(wind_speed_ms: np.ndarray, rated_wind_speed_ms: np.ndarray, cut_in: float = GENERIC_CUT_IN_MS, cut_out: float = GENERIC_CUT_OUT_MS) -> np.ndarray:
    """Cubic-ramp generic power curve, parametrized per-plant by its own rated wind speed.

    Same shape as ~/research/delu-headline-forecast's
    `dhf.physics.wind_capacity_factor` (one fixed 12 m/s rated speed for
    the whole fleet); here `rated_wind_speed_ms` varies per plant based on
    its own specific power, which is the "improved/dynamic" refinement this
    project's methodology calls for.
    """
    ramp = np.clip((wind_speed_ms - cut_in) / (rated_wind_speed_ms - cut_in), 0, None) ** 3
    cf = np.clip(ramp, 0.0, 1.0)
    return np.where((wind_speed_ms >= cut_in) & (wind_speed_ms < cut_out), cf, 0.0)


def capacity_factor_from_library_curve(wind_speed_ms: np.ndarray, curve_wind_speed: np.ndarray, curve_cf: np.ndarray, cut_out: float = GENERIC_CUT_OUT_MS) -> np.ndarray:
    """Interpolate a matched OEDB capacity-factor curve at arbitrary wind speeds.

    `np.interp` clips below the curve's first point and above its last
    (typically 0 and ~1) rather than extrapolating -- appropriate for a
    power curve, but storm cutoff (usually >= the curve's own max) is
    applied explicitly since not every OEDB curve extends to `cut_out`.
    """
    cf = np.interp(wind_speed_ms, curve_wind_speed, curve_cf, left=0.0, right=curve_cf[-1])
    return np.where(wind_speed_ms < cut_out, cf, 0.0)
