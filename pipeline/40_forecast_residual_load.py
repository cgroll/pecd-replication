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
# # Forecasting residual load: out-of-time backtest
#
# Fits equation 11 from `book/markdown/curtailment_system_equations.md`:
# `ResidualLoad_hat(t) = D_true_hat(t) - (P_total(t) - L_hat(t))` -- built
# entirely from calendar + weather (`D_true_hat`, `P_total`) and the
# wind-calibrated curtailment curve (`L_hat`, notebook 39), so everything
# on the right-hand side is knowable ahead of a day-ahead forecast.
#
# Trained on 2019-2023, evaluated out-of-time on 2024-2025 -- against the
# one target this project can check without any new data: **realized**
# residual load, `D_grid(t) - sum_i G_i(t)`, computable directly from SMARD
# for the whole backtest period. Compared against the naive baseline of
# skipping the whole hidden-variable exercise (raw calendar-fit `D_grid`,
# raw `P_total` with no curtailment correction) -- matching this project's
# established habit of always checking whether added complexity earns its
# keep (done for every other workstream here: wind onshore, wind offshore,
# solar).
#
# One honest limit on what this backtest can prove, from notebook 38's own
# findings: since behind-the-meter self-consumption cancels out of residual
# load by construction, a good fit here validates the *net* effect of the
# whole chain, not that every individual hidden variable (`k`, `L_hat`) was
# separately estimated correctly -- see notebook 38's falsification checks
# for that.

# %%
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from pecdr.domain import FULL_YEAR_BACKTEST_YEARS
from pecdr.paths import ProjPaths
from pecdr.residual_load import (
    AGGREGATE_DEMAND_FORMULA,
    NAIVE_DEMAND_FORMULA,
    curtailment_rate,
    fit_curtailment_curve,
    predict_curtailment_mw,
)

paths = ProjPaths()
paths.ensure_directories()

TRAIN_YEARS = [y for y in FULL_YEAR_BACKTEST_YEARS if y <= "2023"]
TEST_YEARS = [y for y in FULL_YEAR_BACKTEST_YEARS if y > "2023"]
print(f"Train: {TRAIN_YEARS[0]}-{TRAIN_YEARS[-1]}, test: {TEST_YEARS[0]}-{TEST_YEARS[-1]}")

# %% [markdown]
# ## Load data, split train/test

# %%
inputs = pd.read_parquet(paths.residual_load_inputs_file)
target_panel = pd.read_parquet(paths.target_panel_file).reindex(inputs.index)

train = inputs.loc[TRAIN_YEARS[0] : TRAIN_YEARS[-1]]
test = inputs.loc[TEST_YEARS[0] : TEST_YEARS[-1]]
target_train, target_test = target_panel.loc[train.index], target_panel.loc[test.index]

# %% [markdown]
# ## Fit the full chain on train, apply to test
#
# Demand model, oversupply proxy, and the wind-calibrated curtailment curve
# are all fit on training data only, then applied unchanged to the test
# period -- a genuine out-of-time evaluation, not an in-sample fit.

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

# %% [markdown]
# ## Apply to the test period

# %%
d_true_hat_test = d_true_hat_of(test)
p_total_test = test["P_wind_on_mw"] + test["P_wind_off_mw"] + test["P_pv_mw"]
oversupply_test = p_total_test / d_true_hat_test

l_hat_test = (
    predict_curtailment_mw(curtailment_curve, oversupply_test, test["P_wind_on_mw"])
    + predict_curtailment_mw(curtailment_curve, oversupply_test, test["P_wind_off_mw"])
    + predict_curtailment_mw(curtailment_curve, oversupply_test, test["P_pv_mw"])
)
residual_load_hat = d_true_hat_test - (p_total_test - l_hat_test)

# %% [markdown]
# ## Naive baseline: skip the hidden-variable machinery entirely
#
# Demand forecast directly from calendar + temperature (no PV
# self-consumption correction), raw weather-driven potential (no
# curtailment correction).

# %%
naive_demand_model = smf.ols(NAIVE_DEMAND_FORMULA, data=train).fit()
naive_demand_test = naive_demand_model.predict(test)
naive_residual_load_hat = naive_demand_test - p_total_test

# %% [markdown]
# ## Realized residual load (the target, computed directly from SMARD -- no estimation)

# %%
realized_residual_load = target_test["load"] - (target_test["wind_onshore"] + target_test["wind_offshore"] + target_test["pv"])

comparison = pd.DataFrame({
    "realized": realized_residual_load,
    "full_model": residual_load_hat,
    "naive_baseline": naive_residual_load_hat,
}).dropna()

stats = []
for col in ["full_model", "naive_baseline"]:
    diff = comparison[col] - comparison["realized"]
    stats.append({
        "approach": col,
        "mae_mw": float(diff.abs().mean()),
        "bias_mw": float(diff.mean()),
        "corr": float(comparison[col].corr(comparison["realized"])),
    })
stats_df = pd.DataFrame(stats)
stats_df

# %% [markdown]
# ## Full test period, hourly

# %%
fig, ax = plt.subplots(figsize=(14, 5))
comparison["realized"].plot(ax=ax, label="Realized (SMARD)", alpha=0.8, linewidth=0.4)
comparison["full_model"].plot(ax=ax, label="Full model forecast", alpha=0.8, linewidth=0.4)
comparison["naive_baseline"].plot(ax=ax, label="Naive baseline", alpha=0.8, linewidth=0.4)
ax.set_ylabel("Residual load (MW)")
ax.set_title(f"Out-of-time test period {TEST_YEARS[0]}-{TEST_YEARS[-1]}")
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "40_test_period_timeseries.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/40_test_period_timeseries.png
# :name: fig-40-test-period-timeseries
# Full model and naive baseline vs. realized residual load, out-of-time test period.
# ```

# %% [markdown]
# ## Scatter vs. realized

# %%
fig, axes = plt.subplots(1, 2, figsize=(12, 5.5), sharex=True, sharey=True)
for ax, col, label in zip(axes, ["full_model", "naive_baseline"], ["Full model", "Naive baseline"]):
    ax.scatter(comparison["realized"], comparison[col], s=2, alpha=0.05)
    lims = [comparison[["realized", col]].min().min(), comparison[["realized", col]].max().max()]
    ax.plot(lims, lims, "k--", alpha=0.5, label="1:1")
    ax.set_xlabel("Realized residual load (MW)")
    ax.set_ylabel(f"{label} (MW)")
    row = stats_df[stats_df["approach"] == ("full_model" if col == "full_model" else "naive_baseline")].iloc[0]
    ax.set_title(f"{label}\nMAE={row['mae_mw']:.0f} MW, corr={row['corr']:.3f}")
fig.tight_layout()
fig.savefig(paths.images_path / "40_scatter_vs_realized.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/40_scatter_vs_realized.png
# :name: fig-40-scatter-vs-realized
# Full model and naive baseline vs. realized residual load, out-of-time test period.
# ```
