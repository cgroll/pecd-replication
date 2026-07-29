"""Shared helpers for the residual-load workstream: converting modeled
capacity factors to absolute MW potential, building the gross-demand
regression's calendar/temperature features, and fitting that regression.

See `book/markdown/curtailment_system_equations.md` for the full system of
equations this module implements pieces of -- in particular equation 7
(the gross-demand regression) and 7a (the feed-in-category split).
"""

import holidays as holidays_lib
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from pecdr.capacity_weighting import capacity_weighted_cf, total_hourly_capacity


def potential_mw(cf: pd.DataFrame, capacity_by_zone_month: pd.DataFrame, zone_col: str = "region_code") -> pd.Series:
    """Absolute MW potential: capacity-weighted mean CF x total capacity, both hourly.

    `capacity_weighted_cf` and `total_hourly_capacity` are both already
    generic over `zone_col` (see `pecdr/capacity_weighting.py`) -- this
    just multiplies them back together to undo the normalization and
    recover an absolute MW series instead of a capacity factor.
    """
    weighted_cf = capacity_weighted_cf(cf, capacity_by_zone_month, zone_col=zone_col)
    total_capacity = total_hourly_capacity(capacity_by_zone_month, cf.index, zone_col=zone_col)
    return weighted_cf * total_capacity


def wind_potential_mw(national_cf: pd.Series, capacity_by_year: dict[str, float]) -> pd.Series:
    """Absolute MW wind potential, using each year's own plant-panel capacity
    (a step function that jumps once per year) rather than a separately
    built monthly capacity panel -- keeps the MW conversion consistent with
    the exact fleet already used to compute `national_cf`
    (pipeline/10 and pipeline/32's year-vintage-correct plant panels),
    rather than introducing a second, independently-built capacity source
    that could disagree with it.
    """
    capacity_hourly = national_cf.index.year.astype(str).map(capacity_by_year)
    return national_cf * pd.Series(capacity_hourly, index=national_cf.index, dtype=float)


def degree_days(temperature_c: pd.Series, heat_ref: float = 15.0, cool_ref: float = 20.0) -> tuple[pd.Series, pd.Series]:
    """Heating and cooling degree terms: how far below/above a reference
    temperature, floored at 0 -- the standard degree-day parametrization of
    temperature-driven electricity demand. Both terms are expected to carry
    a *positive* coefficient in the demand regression (colder -> more
    heating demand; hotter -> more cooling demand) -- a directly
    falsifiable prediction, not just a curve-fitting convenience.
    """
    heating = (heat_ref - temperature_c).clip(lower=0)
    cooling = (temperature_c - cool_ref).clip(lower=0)
    return heating, cooling


def calendar_features(index: pd.DatetimeIndex) -> pd.DataFrame:
    """Day-of-week, hour-of-day, German public holiday, and a linear year
    trend (structural change over 2019-2025, e.g. 2022's energy-price-crisis
    demand destruction) -- everything forecastable ahead of time from the
    calendar alone, no weather needed.
    """
    de_holidays = holidays_lib.Germany(years=range(index.year.min(), index.year.max() + 1))
    years_since_start = (index - index[0]) / pd.Timedelta(days=365.25)
    return pd.DataFrame(
        {
            "dow": index.day_name(),
            "hour": index.hour,
            "is_holiday": index.normalize().isin(pd.DatetimeIndex(list(de_holidays.keys()))),
            "years_since_start": years_since_start,
        },
        index=index,
    )


DEMAND_FORMULA = (
    "D_grid_mw ~ C(dow) + C(hour) + is_holiday "
    "+ heating_degree + cooling_degree + years_since_start "
    "+ P_pv_full_feed_in_mw + P_pv_self_consumption_mw"
)

# Equation 7, single aggregate P_pv term -- the trustworthy specification
# once notebook 38 found the 7a category split unidentifiable (0.95
# correlation between the two regressors). Used by notebooks 39, 40, 42.
AGGREGATE_DEMAND_FORMULA = (
    "D_grid_mw ~ C(dow) + C(hour) + is_holiday "
    "+ heating_degree + cooling_degree + years_since_start + P_pv_mw"
)

# The naive baseline (pipeline/40, 42): no PV term at all, so no
# self-consumption correction -- fits observed D_grid directly.
NAIVE_DEMAND_FORMULA = "D_grid_mw ~ C(dow) + C(hour) + is_holiday + heating_degree + cooling_degree + years_since_start"

# Right-hand sides only (no target variable prefixed) for notebook 42's
# model-flexibility comparison, which fits several models against
# *residual load* directly rather than against D_grid -- so the same
# feature sets get reused with different left-hand sides depending on the
# model, rather than baked into a single fixed formula string.
CALENDAR_ONLY_RHS = "C(dow) + C(hour) + is_holiday + years_since_start"
WEATHER_AND_POTENTIAL_RHS = (
    "C(dow) + C(hour) + is_holiday + heating_degree + cooling_degree + years_since_start"
    " + P_wind_on_mw + P_wind_off_mw + P_pv_mw"
)


def fit_gross_demand_model(df: pd.DataFrame, extra_regressors: list[str] | None = None):
    """Fit the gross-demand regression (equation 7/7a): grid-metered load as
    a calendar+temperature demand model minus PV self-consumption.

    `extra_regressors`, if given, are appended to the formula -- used for
    the falsification check of adding wind potential terms, which should
    come out statistically indistinguishable from zero (wind has no
    behind-the-meter self-consumption to detect).
    """
    formula = DEMAND_FORMULA
    if extra_regressors:
        formula += " + " + " + ".join(extra_regressors)
    return smf.ols(formula, data=df).fit()


def predict_gross_demand(model, df: pd.DataFrame) -> pd.Series:
    """D_true_hat(t): the fitted model's prediction with both PV
    self-consumption terms zeroed out -- i.e. gross demand before any
    self-consumption deduction, the quantity equation 7 calls
    `D_true_hat(t;theta)` (the underbrace term, not the full right-hand side).
    """
    df_zeroed = df.copy()
    df_zeroed["P_pv_full_feed_in_mw"] = 0.0
    df_zeroed["P_pv_self_consumption_mw"] = 0.0
    return model.predict(df_zeroed)


def curtailment_rate(potential: pd.Series, observed: pd.Series, min_potential: float) -> pd.Series:
    """`Gap(t) / P(t)` (equation 10's building block), masked to hours with
    at least `min_potential` MW of potential -- below that, the ratio is
    noisy and not physically meaningful (curtailing 2 MW out of a possible
    3 MW means something very different from curtailing 2000 out of 3000).
    """
    return ((potential - observed) / potential).where(potential > min_potential)


def fit_curtailment_curve(rate: pd.Series, oversupply_proxy: pd.Series, bins: np.ndarray) -> pd.Series:
    """Bin-mean curtailment rate vs. the oversupply proxy (equation 10) --
    an empirical, nonparametric lookup rather than an assumed functional
    form, matching this project's established convention (notebooks 22/36)
    of binning bias against a driver rather than fitting a parametric curve.
    """
    oversupply_bin = pd.cut(oversupply_proxy, bins)
    return rate.groupby(oversupply_bin, observed=True).mean().reindex(oversupply_bin.cat.categories)


def predict_curtailment_mw(curve: pd.Series, oversupply_proxy: pd.Series, potential: pd.Series) -> np.ndarray:
    """Apply a curtailment-rate curve (from `fit_curtailment_curve`) to a new
    technology's own potential, via the same oversupply-proxy bins --
    equation 10a's `L_hat(t)`. Clipped at 0 (a fitted rate can go slightly
    negative in a low-oversupply bin from model noise; curtailment itself
    cannot be negative).

    `oversupply_proxy` is clipped into the curve's own fitted range before
    binning -- an out-of-time test period can have hours whose oversupply
    proxy falls outside whatever range training data covered (found via a
    genuine bug: this silently produced `NaN` for 4.1% of a real test
    period before the clip was added, since `pd.cut` has no bin to assign
    an out-of-range value to). Clipping extrapolates by repeating the
    nearest edge bin's fitted rate -- the same graceful-degradation
    behavior a tree-based model gives for free, done explicitly here
    instead of failing outright. Interior bins with zero training
    observations are filled by nearest-neighbor interpolation for the same
    reason.
    """
    curve_filled = curve.interpolate(limit_direction="both")
    intervals = pd.IntervalIndex(curve_filled.index)
    lower_bound, upper_bound = intervals.min().left, intervals.max().right
    span = upper_bound - lower_bound
    clipped_proxy = oversupply_proxy.clip(lower=lower_bound + span * 1e-9, upper=upper_bound - span * 1e-9)
    oversupply_bin = pd.cut(clipped_proxy, intervals)
    predicted_rate = oversupply_bin.map(curve_filled)
    return (predicted_rate.to_numpy() * potential).clip(lower=0)
