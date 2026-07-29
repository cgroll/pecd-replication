# ---
# jupytext:
#   text_representation:
#     format_name: percent
# kernelspec:
#   display_name: Python 3
#   language: python
#   name: python3
# ---

# %% [markdown]
# # Does the structure matter, or just the features?
#
# `40_forecast_residual_load` compared two points: a naive baseline (no
# self-consumption or curtailment correction) and the full structural model
# (equations 7-11, explicitly estimating the hidden `D_true` and `L_hat`).
# That comparison conflates two separate questions: does having
# weather-derived information at all help, and does *how* it's used (flat
# features vs. explicitly modeling unobserved quantities) matter on top of
# that? This notebook adds three more points to separate them:
#
# - **M0 -- calendar only, no weather at all.** The true "zero weather
#   information" floor: predicts residual load directly from day of week,
#   hour, holiday, and a year trend. Even the naive baseline from `40`
#   already uses weather-derived wind/solar potential on the supply side,
#   so it doesn't answer "does weather help at all" on its own.
# - **M3 -- the same weather + potential-generation features as the full
#   model, but no structure at all.** One flat linear regression predicting
#   *observed* residual load directly from calendar, temperature, and
#   `P_wind_on`/`P_wind_off`/`P_pv` -- no separate demand/supply estimation,
#   no `D_true` vs. `D_grid` distinction, no curtailment curve.
# - **M4 -- the same features as M3, fit with LightGBM instead of a linear
#   model** -- tests whether a flexible, nonlinear model closes the gap to
#   the structural model without any hand-built equations at all.
#
# All five models share the same train/test split (2019-2023 / 2024-2025)
# and the same target: realized residual load, computed directly from
# SMARD, never estimated.

# %%
import lightgbm as lgb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from pecdr.domain import FULL_YEAR_BACKTEST_YEARS
from pecdr.paths import ProjPaths
from pecdr.residual_load import (
    AGGREGATE_DEMAND_FORMULA,
    CALENDAR_ONLY_RHS,
    NAIVE_DEMAND_FORMULA,
    WEATHER_AND_POTENTIAL_RHS,
    curtailment_rate,
    fit_curtailment_curve,
    predict_curtailment_mw,
)

paths = ProjPaths()
paths.ensure_directories()

TRAIN_YEARS = [y for y in FULL_YEAR_BACKTEST_YEARS if y <= "2023"]
TEST_YEARS = [y for y in FULL_YEAR_BACKTEST_YEARS if y > "2023"]

inputs = pd.read_parquet(paths.residual_load_inputs_file)
target_panel = pd.read_parquet(paths.target_panel_file).reindex(inputs.index)
realized_residual_load = target_panel["load"] - (target_panel["wind_onshore"] + target_panel["wind_offshore"] + target_panel["pv"])
inputs = inputs.assign(ResidualLoad_mw=realized_residual_load)

# Capacity-factor features and a capacity-normalized target, for M5 below --
# added here, before the train/test split, so both slices carry them.
total_capacity = inputs["Capacity_wind_on_mw"] + inputs["Capacity_wind_off_mw"] + inputs["Capacity_pv_mw"]
inputs = inputs.assign(
    CF_wind_on=inputs["P_wind_on_mw"] / inputs["Capacity_wind_on_mw"],
    CF_wind_off=inputs["P_wind_off_mw"] / inputs["Capacity_wind_off_mw"],
    CF_pv=inputs["P_pv_mw"] / inputs["Capacity_pv_mw"],
    TotalCapacity_mw=total_capacity,
    ResidualLoad_per_capacity=inputs["ResidualLoad_mw"] / total_capacity,
)

train = inputs.loc[TRAIN_YEARS[0] : TRAIN_YEARS[-1]]
test = inputs.loc[TEST_YEARS[0] : TEST_YEARS[-1]]
target_train, target_test = target_panel.loc[train.index], target_panel.loc[test.index]

predictions = {"realized": test["ResidualLoad_mw"]}

# %% [markdown]
# ## M0: calendar only -- the zero-weather-information floor

# %%
m0 = smf.ols(f"ResidualLoad_mw ~ {CALENDAR_ONLY_RHS}", data=train).fit()
predictions["m0_calendar_only"] = m0.predict(test)

# %% [markdown]
# ## M1: naive baseline (from notebook 40) -- weather used, but no structure or curtailment correction

# %%
naive_demand_model = smf.ols(NAIVE_DEMAND_FORMULA, data=train).fit()
p_total_test = test["P_wind_on_mw"] + test["P_wind_off_mw"] + test["P_pv_mw"]
predictions["m1_naive_baseline"] = naive_demand_model.predict(test) - p_total_test

# %% [markdown]
# ## M2: full structural model (from notebook 40) -- explicit unobserved-quantity estimation

# %%
demand_model = smf.ols(AGGREGATE_DEMAND_FORMULA, data=train).fit()


def d_true_hat_of(df: pd.DataFrame) -> pd.Series:
    return demand_model.predict(df.assign(P_pv_mw=0.0))


p_total_train = train["P_wind_on_mw"] + train["P_wind_off_mw"] + train["P_pv_mw"]
oversupply_train = p_total_train / d_true_hat_of(train)
bins = np.linspace(0, oversupply_train.quantile(0.995), 21)

min_potential_on = 0.05 * train["P_wind_on_mw"].max()
min_potential_off = 0.05 * train["P_wind_off_mw"].max()
p_wind_total_train = train["P_wind_on_mw"].where(train["P_wind_on_mw"] > min_potential_on, 0) + train["P_wind_off_mw"].where(
    train["P_wind_off_mw"] > min_potential_off, 0
)
gap_wind_total_train = (train["P_wind_on_mw"] - target_train["wind_onshore"]).where(train["P_wind_on_mw"] > min_potential_on, 0) + (
    train["P_wind_off_mw"] - target_train["wind_offshore"]
).where(train["P_wind_off_mw"] > min_potential_off, 0)
rate_wind_train = (gap_wind_total_train / p_wind_total_train).where(p_wind_total_train > 0)
curtailment_curve = fit_curtailment_curve(rate_wind_train, oversupply_train, bins)

d_true_hat_test = d_true_hat_of(test)
oversupply_test = p_total_test / d_true_hat_test
l_hat_test = (
    predict_curtailment_mw(curtailment_curve, oversupply_test, test["P_wind_on_mw"])
    + predict_curtailment_mw(curtailment_curve, oversupply_test, test["P_wind_off_mw"])
    + predict_curtailment_mw(curtailment_curve, oversupply_test, test["P_pv_mw"])
)
predictions["m2_full_structural"] = d_true_hat_test - (p_total_test - l_hat_test)

# %% [markdown]
# ## M3: same features as the full model, but one flat linear regression, no structure

# %%
m3 = smf.ols(f"ResidualLoad_mw ~ {WEATHER_AND_POTENTIAL_RHS}", data=train).fit()
predictions["m3_linear_features_only"] = m3.predict(test)

# %% [markdown]
# ## M4: same features as M3, fit with LightGBM instead of a linear model

# %%
dow_dtype = pd.CategoricalDtype(categories=sorted(inputs["dow"].unique()))
hour_dtype = pd.CategoricalDtype(categories=sorted(inputs["hour"].unique()))


def lgbm_features(df: pd.DataFrame, numeric_features: list[str]) -> pd.DataFrame:
    X = df[numeric_features].copy()
    X["is_holiday"] = df["is_holiday"].astype(int)
    X["dow"] = df["dow"].astype(dow_dtype)
    X["hour"] = df["hour"].astype(hour_dtype)
    return X


m4_numeric_features = ["heating_degree", "cooling_degree", "years_since_start", "P_wind_on_mw", "P_wind_off_mw", "P_pv_mw"]
m4 = lgb.LGBMRegressor(n_estimators=500, learning_rate=0.05, num_leaves=31, random_state=42, verbosity=-1)
m4.fit(lgbm_features(train, m4_numeric_features), train["ResidualLoad_mw"], categorical_feature=["dow", "hour"])
predictions["m4_lightgbm_features_only"] = pd.Series(m4.predict(lgbm_features(test, m4_numeric_features)), index=test.index)

# %% [markdown]
# ## M5: LightGBM again, but capacity-factor-rescaled features and target
#
# M4's likely handicap was extrapolation: `years_since_start` and
# `P_wind_off_mw` both had a large share of test-period values beyond
# anything seen in training, and tree-based models can't extrapolate a
# trend. This removes that trend at its source rather than asking the
# tree to cope with it: features become capacity factors
# (`P_i(t)/Capacity_i(t)`, bounded ~0-1 regardless of fleet size) instead
# of absolute MW, and the *target* becomes residual load divided by total
# installed renewable capacity, rather than residual load in MW directly.
# The model never has to learn the capacity scale at all -- it only
# learns the weather-driven pattern in the normalized quantity; the actual
# MW prediction is reconstructed afterward by multiplying back by
# `TotalCapacity_mw`, which is simply looked up at the target time, not
# modeled.

# %%
m5_numeric_features = ["heating_degree", "cooling_degree", "years_since_start", "CF_wind_on", "CF_wind_off", "CF_pv"]
m5 = lgb.LGBMRegressor(n_estimators=500, learning_rate=0.05, num_leaves=31, random_state=42, verbosity=-1)
m5.fit(lgbm_features(train, m5_numeric_features), train["ResidualLoad_per_capacity"], categorical_feature=["dow", "hour"])
predicted_per_capacity = pd.Series(m5.predict(lgbm_features(test, m5_numeric_features)), index=test.index)
predictions["m5_lightgbm_capacity_rescaled"] = predicted_per_capacity * test["TotalCapacity_mw"]

# %% [markdown]
# ## Comparison: all six, out-of-time, same target

# %%
comparison = pd.DataFrame(predictions)
stats_rows = []
for col in [
    "m0_calendar_only",
    "m1_naive_baseline",
    "m2_full_structural",
    "m3_linear_features_only",
    "m4_lightgbm_features_only",
    "m5_lightgbm_capacity_rescaled",
]:
    diff = comparison[col] - comparison["realized"]
    stats_rows.append({
        "model": col,
        "mae_mw": float(diff.abs().mean()),
        "bias_mw": float(diff.mean()),
        "corr": float(comparison[col].corr(comparison["realized"])),
    })
stats_df = pd.DataFrame(stats_rows)
stats_df

# %%
fig, ax = plt.subplots(figsize=(10, 5))
labels = [
    "M0: calendar\nonly",
    "M1: naive\nbaseline",
    "M2: full\nstructural",
    "M3: linear,\nfeatures only",
    "M4: LightGBM,\nfeatures only",
    "M5: LightGBM,\nCF-rescaled",
]
ax.bar(labels, stats_df["mae_mw"])
ax.set_ylabel("MAE (MW)")
ax.set_title("Out-of-time MAE, 2024-2025 test period")
fig.tight_layout()
fig.savefig(paths.images_path / "42_mae_comparison.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/42_mae_comparison.png
# :name: fig-42-mae-comparison
# Out-of-time MAE across all six models, same test period.
# ```

# %% [markdown]
# ## Why does M4 (LightGBM) underperform M3 (plain linear), despite more flexibility?
#
# Checked directly rather than left as a surprise: `years_since_start` has
# **100%** of test-period rows beyond the training range (mechanically
# true, since the test period is entirely after training), and
# `P_wind_off_mw` has **20%** of test hours exceeding the training
# maximum (offshore capacity kept growing). Tree-based models cannot
# extrapolate past the value range seen in training -- a leaf's
# prediction is a constant, so for any trending feature, once the test
# period moves past training's range, the tree just repeats whatever it
# learned at the boundary instead of continuing the trend. With capacity
# (and therefore `P_i`) growing throughout 2019-2025, this is a real,
# structural handicap for LightGBM in this exact setup, not a sign that
# flexible models are worse in general -- a linear model's trend term, by
# contrast, extrapolates by construction.

# %%
for col in ["P_wind_on_mw", "P_wind_off_mw", "P_pv_mw", "years_since_start"]:
    frac_beyond = (test[col] > train[col].max()).mean()
    print(f"{col}: {frac_beyond * 100:.1f}% of test hours exceed the training maximum")

# %% [markdown]
# ## Does capacity-factor rescaling (M5) fix it? Partially, not fully
#
# The natural fix for M4's extrapolation problem: stop feeding the tree a
# trending absolute-MW target and trending absolute-MW features at all.
# M5 uses capacity factors (`CF_i(t) = P_i(t)/Capacity_i(t)`, bounded
# ~0-1 regardless of fleet size) as features and predicts
# `ResidualLoad(t)/TotalCapacity(t)` as the target, reconstructing MW
# afterward by multiplying back by the actual (looked-up, not modeled)
# capacity at the test time.
#
# **This does help** -- M5's MAE (5,294 MW) is meaningfully better than
# M4's (6,714 MW), confirming the extrapolation story above was real and
# that removing the trend from the tree's own inputs matters. **But it
# doesn't fully close the gap to M3**, and checking why turns up a second,
# different mechanism rather than "the fix didn't work": M5's error *in
# the normalized domain* is tiny and nearly unbiased in-sample (bias
# ~0.000 on training data), but picks up a small out-of-sample bias
# (~0.006) on the test period -- and that small normalized-domain bias
# gets **amplified** when multiplied back by `TotalCapacity_mw` to
# reconstruct MW, precisely because capacity is largest in exactly the
# (later) part of the test period. Checked directly: the signed MW error
# correlates with `TotalCapacity_mw` at 0.44. Rescaling fixes the tree's
# *input*-side extrapolation problem; it introduces a smaller, different
# error-amplification effect on the *output*-reconstruction side instead.

# %%
m5_norm_pred_train = pd.Series(m5.predict(lgbm_features(train, m5_numeric_features)), index=train.index)
norm_bias_train = (m5_norm_pred_train - train["ResidualLoad_per_capacity"]).mean()
norm_bias_test = (predicted_per_capacity - test["ResidualLoad_per_capacity"]).mean()
mw_error_test = predictions["m5_lightgbm_capacity_rescaled"] - test["ResidualLoad_mw"]
print(f"M5 normalized-domain bias -- train (in-sample): {norm_bias_train:.5f}, test (out-of-sample): {norm_bias_test:.5f}")
print(f"Correlation between M5's signed MW error and TotalCapacity_mw: {mw_error_test.corr(test['TotalCapacity_mw']):.3f}")

# %% [markdown]
# ## Takeaways
#
# Read the gaps between adjacent bars, not just the bars themselves --
# each comparison isolates one specific question:
#
# - **M0 vs. M1: does weather information help at all?** Surprisingly,
#   M1 (naive baseline, using temperature and raw weather-derived
#   potential) has a *higher* MAE than M0 (calendar only, no weather at
#   all) -- 10,560 MW vs. 10,284 MW -- despite much better correlation
#   (0.905 vs. 0.486). Weather information clearly helps *track the
#   pattern*, but M1's total disregard for curtailment produces such a
#   large systematic bias (-9,750 MW) that it overwhelms that benefit in
#   absolute-error terms. Weather data alone, used carelessly, is not
#   obviously better than no weather data at all.
# - **M1 vs. M2/M3: does correcting for curtailment/self-consumption (in
#   some form) help once weather is already in the model?** Emphatically
#   yes -- both M2 and M3 roughly halve M1's MAE and cut its bias by
#   4-5x, by accounting for the fact that not all potential reaches the
#   grid.
# - **M2 vs. M3: does the *specific structural form* (equations 7-11) beat
#   a plain linear regression given the same inputs?** Here, no --
#   M3 (MAE 4,177, corr 0.941) beats M2 (MAE 4,856, corr 0.915). A flat
#   regression, free to learn its own best-fit relationship between `P_i`
#   and residual load, does better than the hand-built decomposition in
#   this backtest. Plausible reason: M2's curtailment curve is calibrated
#   on wind and *transferred* to PV under a shared-curve assumption (see
#   notebook 39's own robustness check on that assumption); M3's
#   regression instead fits PV's relationship to its own history directly,
#   with no transfer involved.
# - **M3 vs. M4 vs. M5: does a flexible nonlinear model help further,
#   given the same information?** Not in this setup. M4 underperforms M3
#   for the tree-extrapolation reason above; M5's capacity-factor
#   rescaling measurably narrows that gap (MAE 6,714 -> 5,294 MW) without
#   closing it, for the amplification reason just checked. Neither
#   flexible-model variant beats the plain linear regression here.
#
# **Net answer to the original question**: in this backtest, the
# improvement over the naive baseline comes mostly from *having* the
# weather-derived potential-generation features at all, not from the
# specific structural machinery built to extract unobserved quantities --
# a plain linear regression on the same inputs did the best of all six.
# That's a real result, not a foregone conclusion, and it doesn't mean the
# structural approach was wasted effort: it's what made the falsification
# checks, the wind/PV decomposition, and the equations-page account of
# *why* the gap exists possible in the first place -- M3 has no equivalent
# explanation for its own coefficients. But as a pure point-forecast for
# residual load specifically, it's the more complex approach that needed
# to earn its keep here, and on this test it didn't.
