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
# # Estimating curtailment: calibrated on wind, applied to PV
#
# Fits equations 9-10a from `book/markdown/curtailment_system_equations.md`.
# Wind's own gap (`P_i(t) - G_i(t)`) has no behind-the-meter term to
# separate out -- it's `L_repair + L_price + L_congestion + ε` directly, a
# clean signal for how curtailment responds to system-wide oversupply.
# That relationship, fit on wind, is then applied to PV's own oversupply
# hours; what's left over in PV's gap after subtracting the predicted
# curtailment is an estimate of PV's self-consumption plus its own repair
# losses and model error.
#
# Curtailment is expressed as a **rate relative to each technology's own
# potential** (`Gap_i(t) / P_i(t)`), not an absolute MW level, before
# transferring the wind-fitted relationship to PV -- wind and PV have very
# different capacity scales, so only a *fraction of potential lost* is
# meaningfully comparable across technologies experiencing the same
# system-wide oversupply conditions.
#
# The oversupply proxy used here is the **potential-based** one (equation
# 9: `P_total(t) / D_true_hat(t)`), not the observed one from notebooks
# 22/36 -- the observed version is built from already-curtailed values, so
# it understates true oversupply exactly when curtailment is largest.

# %%
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from pecdr.domain import FULL_YEAR_BACKTEST_YEARS
from pecdr.paths import ProjPaths
from pecdr.residual_load import AGGREGATE_DEMAND_FORMULA, curtailment_rate, fit_curtailment_curve, predict_curtailment_mw

paths = ProjPaths()
paths.ensure_directories()

PERIOD_LABEL = f"{FULL_YEAR_BACKTEST_YEARS[0]}-{FULL_YEAR_BACKTEST_YEARS[-1]}"

# %% [markdown]
# ## Rebuild gross demand and the potential-based oversupply proxy

# %%
inputs = pd.read_parquet(paths.residual_load_inputs_file)
target_panel = pd.read_parquet(paths.target_panel_file).reindex(inputs.index)

# Aggregate specification (equation 7, not the uninstrumentable 7a split -- see notebook 38)
demand_model = smf.ols(AGGREGATE_DEMAND_FORMULA, data=inputs).fit()
d_true_hat = demand_model.predict(inputs.assign(P_pv_mw=0.0))

p_total = inputs["P_wind_on_mw"] + inputs["P_wind_off_mw"] + inputs["P_pv_mw"]
oversupply_proxy = p_total / d_true_hat
print(f"Oversupply proxy: mean {oversupply_proxy.mean():.3f}, 99th pct {oversupply_proxy.quantile(0.99):.3f}")

bins = np.linspace(0, oversupply_proxy.quantile(0.995), 21)
bin_mid = [interval.mid for interval in pd.IntervalIndex(pd.cut(oversupply_proxy, bins).cat.categories)]

# %% [markdown]
# ## Wind's own gap: clean, BTM-free curtailment signal
#
# Expressed as a rate (`Gap / P`), restricted to hours with at least 5% of
# each technology's own peak potential -- below that, the ratio is noisy
# and not physically meaningful (curtailing 2 MW out of a possible 3 MW
# means something very different from curtailing 2000 out of 3000).

# %%
min_potential_on = 0.05 * inputs["P_wind_on_mw"].max()
min_potential_off = 0.05 * inputs["P_wind_off_mw"].max()

rate_wind_on = curtailment_rate(inputs["P_wind_on_mw"], target_panel["wind_onshore"], min_potential_on)
rate_wind_off = curtailment_rate(inputs["P_wind_off_mw"], target_panel["wind_offshore"], min_potential_off)

# %% [markdown]
# ## Robustness check: do onshore and offshore show the same curtailment-vs-oversupply shape?
#
# Both are structurally BTM-free, so if their curtailment response to the
# same system-wide oversupply proxy diverges sharply, the "one shared
# curve" assumption used below is too coarse (e.g. differing grid-connection
# constraints per technology).

# %%
rate_on_by_bin = fit_curtailment_curve(rate_wind_on, oversupply_proxy, bins)
rate_off_by_bin = fit_curtailment_curve(rate_wind_off, oversupply_proxy, bins)

fig, ax = plt.subplots(figsize=(9, 5))
ax.plot(bin_mid, rate_on_by_bin, marker="o", markersize=4, label="Wind onshore")
ax.plot(bin_mid, rate_off_by_bin, marker="o", markersize=4, label="Wind offshore")
ax.axhline(0, color="k", linewidth=0.8)
ax.set_xlabel("Potential-based oversupply proxy (binned)")
ax.set_ylabel("Mean curtailment rate (Gap / P)")
ax.set_title(f"Onshore vs. offshore curtailment-rate shape, {PERIOD_LABEL}")
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "39_onshore_vs_offshore_curtailment_shape.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/39_onshore_vs_offshore_curtailment_shape.png
# :name: fig-39-onshore-vs-offshore-shape
# Curtailment rate vs. the potential-based oversupply proxy, onshore vs. offshore wind separately.
# ```

# %% [markdown]
# ## The pooled wind curtailment curve, and its transfer to PV

# %%
gap_pv = inputs["P_pv_mw"] - target_panel["pv"]

p_wind_total = inputs["P_wind_on_mw"].where(inputs["P_wind_on_mw"] > min_potential_on, 0) + inputs["P_wind_off_mw"].where(
    inputs["P_wind_off_mw"] > min_potential_off, 0
)
gap_wind_total = (inputs["P_wind_on_mw"] - target_panel["wind_onshore"]).where(inputs["P_wind_on_mw"] > min_potential_on, 0) + (
    inputs["P_wind_off_mw"] - target_panel["wind_offshore"]
).where(inputs["P_wind_off_mw"] > min_potential_off, 0)
rate_wind_pooled = (gap_wind_total / p_wind_total).where(p_wind_total > 0)

rate_pooled_by_bin = fit_curtailment_curve(rate_wind_pooled, oversupply_proxy, bins)
predicted_curtailment_pv = predict_curtailment_mw(rate_pooled_by_bin, oversupply_proxy, inputs["P_pv_mw"])
residual_pv = gap_pv - predicted_curtailment_pv

print(f"PV raw gap: mean {gap_pv.mean():.0f} MW")
print(f"PV predicted curtailment (wind-calibrated): mean {predicted_curtailment_pv.mean():.0f} MW")
print(f"PV residual (BTM + repair + model error): mean {residual_pv.mean():.0f} MW")

# %% [markdown]
# ## Cross-check: does the PV residual track the self-consumption-registered capacity share?
#
# If the residual above is really behind-the-meter self-consumption, months
# with a larger self-consumption-registered capacity share
# (`solar_capacity_by_pv_category_month`) should show a bigger residual.

# %%
pv_category_month = pd.read_parquet(paths.solar_capacity_by_pv_category_month_file)
category_wide = pv_category_month.assign(year_month=lambda d: d["month"].dt.to_period("M")).pivot_table(
    index="year_month", columns="pv_category", values="capacity_mw"
)
self_consumption_share = 1 - category_wide["full_feed_in"] / category_wide.sum(axis=1)

monthly_residual = residual_pv.groupby(residual_pv.index.to_period("M")).mean()
monthly_comparison = pd.DataFrame({"residual_pv_mw": monthly_residual, "self_consumption_share": self_consumption_share.reindex(monthly_residual.index)}).dropna()

fig, ax1 = plt.subplots(figsize=(12, 5))
ax1.plot(monthly_comparison.index.to_timestamp(), monthly_comparison["residual_pv_mw"], color="#4C72B0", label="PV residual (MW)")
ax1.set_ylabel("PV residual, MW (BTM + repair + model error)", color="#4C72B0")
ax2 = ax1.twinx()
ax2.plot(monthly_comparison.index.to_timestamp(), monthly_comparison["self_consumption_share"], color="#DD8452", label="Self-consumption-registered capacity share")
ax2.set_ylabel("Self-consumption-registered capacity share", color="#DD8452")
corr = monthly_comparison["residual_pv_mw"].corr(monthly_comparison["self_consumption_share"])
ax1.set_title(f"PV residual vs. self-consumption-registered capacity share, {PERIOD_LABEL} (corr={corr:.3f})")
fig.tight_layout()
fig.savefig(paths.images_path / "39_pv_residual_vs_self_consumption_share.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/39_pv_residual_vs_self_consumption_share.png
# :name: fig-39-pv-residual-vs-self-consumption
# Monthly PV residual (curtailment already subtracted out) vs. the self-consumption-registered capacity share.
# ```

# %% [markdown]
# ## Takeaways
#
# - **Onshore and offshore agree reasonably well from oversupply~0.6
#   upward** -- the region that matters most for transferring the curve to
#   PV, since PV's own oversupply hours (daylight, when PV itself
#   contributes to the numerator) skew toward this range. Below that,
#   offshore's rate goes sharply negative (as low as -0.7) while onshore
#   stays mildly positive -- a real divergence, not smoothed over here, most
#   plausibly a residual imperfection in the offshore replication at low
#   wind speeds (this project's own offshore chain is the newer, less
#   independently cross-checked of the two) rather than evidence the
#   shared-curve assumption is wrong where it's actually used.
# - **The wind-calibrated curve explains most of PV's raw gap**: of the
#   ~2177 MW average gap, ~1605 MW (74%) is predicted curtailment, leaving
#   a ~519 MW residual for self-consumption + repair + model error --
#   curtailment, not self-consumption, is the larger piece of PV's own
#   gap, which wasn't obvious going in.
# - **The residual correlates with the self-consumption-registered capacity
#   share at 0.643** -- supportive, but both series simply trend upward
#   over 2019-2025, so part of this is two trending series moving together
#   rather than tight month-to-month co-movement. Worth a follow-up
#   detrended check (year-over-year differences instead of levels) before
#   leaning on this number heavily.
