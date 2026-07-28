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
# # What drives the gap against SMARD?
#
# `12_compare_all_approaches` found that **all three** modeled series --
# including PECD's own official product (approach 1) -- systematically
# overshoot SMARD's actual wind-onshore generation at high capacity factors.
# Since approach 1 isn't derived from this project's replication at all,
# that shared pattern is evidence the gap is a genuine physical-vs-grid
# effect (curtailment, high-wind shutdown, behind-the-meter
# self-consumption -- see `../markdown/index.md`), not a defect specific to
# this project's methodology.
#
# This notebook digs into *when* the bias shows up, pooled across every
# year in `pecdr.domain.FULL_YEAR_BACKTEST_YEARS`, to see which candidate
# explanation it's most consistent with:
#
# - **Bias vs. CF level** -- grows with output level, as expected if it's
#   driven by high-wind curtailment/shutdown rather than a flat offset.
# - **Bias vs. month** -- larger in winter (higher wind *and* more grid
#   congestion) would point toward curtailment; a flat seasonal pattern
#   would point toward something structural instead (e.g. a fleet-vintage
#   or power-curve mismatch).
# - **Bias vs. hour of day** -- larger overnight, when demand is low and
#   negative prices make curtailment more likely, would support the
#   curtailment/oversupply story specifically (as opposed to shutdown,
#   which has no time-of-day preference of its own).
# - **Bias vs. renewable oversupply** -- (wind + solar) / load as a rough
#   proxy for how close the grid is to zero/negative residual load, the
#   condition curtailment is most likely under.
# - **Bias vs. year** -- checks whether any of the above is stable across
#   the backtest period, or whether one year is doing all the work.

# %%
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from pecdr.capacity_weighting import capacity_weighted_cf, total_hourly_capacity
from pecdr.domain import FULL_YEAR_BACKTEST_YEARS
from pecdr.paths import ProjPaths

paths = ProjPaths()
paths.ensure_directories()

PERIOD_LABEL = f"{FULL_YEAR_BACKTEST_YEARS[0]}-{FULL_YEAR_BACKTEST_YEARS[-1]}"

# %% [markdown]
# ## Rebuild the same three series as `12_compare_all_approaches`

# %%
mastr_peon_month = pd.read_parquet(paths.mastr_capacity_by_peon_month_file)

pecd_peon_cf = pd.read_parquet(paths.pecd_wind_onshore_capacity_factors_file)
approach1 = capacity_weighted_cf(pecd_peon_cf, mastr_peon_month)

approach3 = pd.read_parquet(paths.wind_onshore_full_year_cf_file)["national"]

target_panel = pd.read_parquet(paths.target_panel_file)
total_capacity_hourly = total_hourly_capacity(mastr_peon_month, target_panel.index)
smard_implied_cf = target_panel["wind_onshore"] / total_capacity_hourly

comparison = pd.DataFrame({
    "1_pecd_official_x_mastr": approach1,
    "3_pecd_replication": approach3,
    "4_smard_implied": smard_implied_cf,
}).loc[FULL_YEAR_BACKTEST_YEARS[0]:FULL_YEAR_BACKTEST_YEARS[-1]].dropna()

comparison["diff1"] = comparison["1_pecd_official_x_mastr"] - comparison["4_smard_implied"]
comparison["diff3"] = comparison["3_pecd_replication"] - comparison["4_smard_implied"]

# Renewable-oversupply proxy: (wind + solar generation) / load, from SMARD.
# High values approximate the low/negative-residual-load conditions under
# which curtailment is most likely to bind.
renewables = target_panel.loc[comparison.index, ["pv", "wind_onshore", "wind_offshore"]].sum(axis=1)
comparison["renewable_share_of_load"] = renewables / target_panel.loc[comparison.index, "load"]

print(f"Hours compared: {len(comparison):,}")
print(f"Approach 1 vs SMARD -- bias: {comparison['diff1'].mean():.4f}, MAE: {comparison['diff1'].abs().mean():.4f}")
print(f"Approach 3 vs SMARD -- bias: {comparison['diff3'].mean():.4f}, MAE: {comparison['diff3'].abs().mean():.4f}")

# %% [markdown]
# ## 1. Does the bias grow with capacity-factor level?
#
# Both approaches shown side by side against the same SMARD-implied CF
# bins -- if the shared shape survives even though approach 1 and approach
# 3 arrive at their numbers completely differently, that's further evidence
# the effect lives in the SMARD side of the comparison (curtailment/
# shutdown), not in either model.

# %%
bins = np.linspace(0, comparison["4_smard_implied"].max(), 21)
comparison["cf_bin"] = pd.cut(comparison["4_smard_implied"], bins)
bin_mid = [interval.mid for interval in comparison["cf_bin"].cat.categories]

bin_stats1 = comparison.groupby("cf_bin", observed=True)["diff1"].mean().reindex(comparison["cf_bin"].cat.categories)
bin_stats3 = comparison.groupby("cf_bin", observed=True)["diff3"].mean().reindex(comparison["cf_bin"].cat.categories)

fig, ax = plt.subplots(figsize=(9, 5))
width = (bin_mid[1] - bin_mid[0]) * 0.4
ax.bar(np.array(bin_mid) - width / 2, bin_stats1, width=width, label="1. PECD official x MaStR", color="#4C72B0")
ax.bar(np.array(bin_mid) + width / 2, bin_stats3, width=width, label="3. PECD replication", color="#DD8452")
ax.axhline(0, color="k", linewidth=0.8)
ax.set_xlabel("SMARD-implied CF (binned)")
ax.set_ylabel("Mean bias (model - SMARD)")
ax.set_title(f"Bias vs. capacity-factor level, {PERIOD_LABEL}")
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "22_bias_vs_cf_level.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/22_bias_vs_cf_level.png
# :name: fig-22-bias-vs-cf-level
# Mean bias (model minus SMARD-implied CF) by SMARD CF bin, both approaches, 2019-2025.
# ```

# %% [markdown]
# ## 2. Seasonal pattern: bias by month

# %%
monthly = comparison.groupby(comparison.index.month)[["diff1", "diff3"]].mean()
monthly.index.name = "month"

fig, ax = plt.subplots(figsize=(9, 5))
width = 0.35
x = monthly.index.to_numpy()
ax.bar(x - width / 2, monthly["diff1"], width=width, label="1. PECD official x MaStR", color="#4C72B0")
ax.bar(x + width / 2, monthly["diff3"], width=width, label="3. PECD replication", color="#DD8452")
ax.axhline(0, color="k", linewidth=0.8)
ax.set_xticks(x)
ax.set_xlabel("Month")
ax.set_ylabel("Mean bias (model - SMARD)")
ax.set_title(f"Bias by month, {PERIOD_LABEL}")
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "22_bias_by_month.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/22_bias_by_month.png
# :name: fig-22-bias-by-month
# Mean bias by calendar month, both approaches, pooled across 2019-2025.
# ```

# %% [markdown]
# ## 3. Diurnal pattern: bias by hour of day
#
# If the bias is largest overnight -- low demand, wind often still
# blowing, negative prices more likely -- that's consistent with
# oversupply-driven curtailment specifically, rather than high-wind
# shutdown (which cares about wind speed, not time of day).

# %%
hourly = comparison.groupby(comparison.index.hour)[["diff1", "diff3"]].mean()
hourly.index.name = "hour"

fig, ax = plt.subplots(figsize=(9, 5))
ax.plot(hourly.index, hourly["diff1"], marker="o", markersize=4, label="1. PECD official x MaStR", color="#4C72B0")
ax.plot(hourly.index, hourly["diff3"], marker="o", markersize=4, label="3. PECD replication", color="#DD8452")
ax.axhline(0, color="k", linewidth=0.8)
ax.set_xlabel("Hour of day (UTC)")
ax.set_ylabel("Mean bias (model - SMARD)")
ax.set_title(f"Bias by hour of day, {PERIOD_LABEL}")
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "22_bias_by_hour.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/22_bias_by_hour.png
# :name: fig-22-bias-by-hour
# Mean bias by hour of day, both approaches, pooled across 2019-2025.
# ```

# %% [markdown]
# ## 4. Bias vs. renewable oversupply proxy
#
# `(pv + wind_onshore + wind_offshore) / load` approximates how close the
# system is to zero (or negative) residual load -- the condition under
# which curtailment is most likely to bind. A bias that climbs with this
# ratio, even controlling for CF level, would point specifically at
# oversupply-driven curtailment rather than a pure per-turbine wind-speed
# effect.

# %%
share_bins = np.linspace(0, comparison["renewable_share_of_load"].quantile(0.99), 16)
comparison["share_bin"] = pd.cut(comparison["renewable_share_of_load"], share_bins)
share_mid = [interval.mid for interval in comparison["share_bin"].cat.categories]

share_stats1 = comparison.groupby("share_bin", observed=True)["diff1"].mean().reindex(comparison["share_bin"].cat.categories)
share_stats3 = comparison.groupby("share_bin", observed=True)["diff3"].mean().reindex(comparison["share_bin"].cat.categories)

fig, ax = plt.subplots(figsize=(9, 5))
width = (share_mid[1] - share_mid[0]) * 0.4
ax.bar(np.array(share_mid) - width / 2, share_stats1, width=width, label="1. PECD official x MaStR", color="#4C72B0")
ax.bar(np.array(share_mid) + width / 2, share_stats3, width=width, label="3. PECD replication", color="#DD8452")
ax.axhline(0, color="k", linewidth=0.8)
ax.set_xlabel("(PV + wind onshore + wind offshore) / load, binned")
ax.set_ylabel("Mean bias (model - SMARD)")
ax.set_title(f"Bias vs. renewable oversupply proxy, {PERIOD_LABEL}")
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "22_bias_vs_oversupply.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/22_bias_vs_oversupply.png
# :name: fig-22-bias-vs-oversupply
# Mean bias vs. renewable share of load (oversupply proxy), both approaches, pooled across 2019-2025.
# ```

# %% [markdown]
# ## 5. Does the bias hold up year to year?
#
# The pooled panels above could hide a single unusual year -- this checks
# directly whether bias/MAE is stable across the backtest period.

# %%
yearly = comparison.groupby(comparison.index.year)[["diff1", "diff3"]].agg(["mean", lambda s: s.abs().mean()])
yearly.columns = ["bias1", "mae1", "bias3", "mae3"]

fig, ax = plt.subplots(figsize=(9, 5))
width = 0.35
x = yearly.index.to_numpy()
ax.bar(x - width / 2, yearly["bias1"], width=width, label="1. PECD official x MaStR", color="#4C72B0")
ax.bar(x + width / 2, yearly["bias3"], width=width, label="3. PECD replication", color="#DD8452")
ax.axhline(0, color="k", linewidth=0.8)
ax.set_xticks(x)
ax.set_xlabel("Year")
ax.set_ylabel("Mean bias (model - SMARD)")
ax.set_title("Bias by year")
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "22_bias_by_year.png", dpi=150, bbox_inches="tight")
plt.show()

yearly

# %% [markdown]
# ```{figure} ../../output/images/22_bias_by_year.png
# :name: fig-22-bias-by-year
# Mean bias by year, both approaches, 2019-2025.
# ```

# %% [markdown]
# ## Summary table

# %%
summary = pd.DataFrame({
    "approach 1 (PECD official)": [comparison["diff1"].mean(), comparison["diff1"].abs().mean()],
    "approach 3 (replication)": [comparison["diff3"].mean(), comparison["diff3"].abs().mean()],
}, index=["mean bias", "MAE"])
summary

# %% [markdown]
# ## Takeaways
#
# - **CF level and month**: both patterns from the single-year (2020) pass
#   hold up over the full 2019-2025 backtest, and come out cleaner with 7x
#   the sample -- bias grows roughly monotonically with SMARD CF, and is
#   largest in the high-wind months (Jan/Feb, Oct-Dec), near zero in
#   summer. Both approaches (built from PECD's official product and from
#   this project's from-scratch replication respectively) show the same
#   shape, which is strong evidence the effect lives on the SMARD side of
#   the comparison -- wind-speed-driven curtailment and/or high-wind
#   shutdown -- not in either model.
# - **Bias by year**: stable at ~0.048-0.056 (approach 3) / ~0.014-0.017
#   (approach 1) for 2019-2022, then steps up to ~0.065-0.072 /
#   ~0.015-0.023 for 2023-2025 -- both approaches step up together, at
#   the same point in time. That's consistent with a real-world change
#   rather than a modeling artifact specific to either approach: Germany's
#   reported wind curtailment volumes have risen substantially since
#   2022-2023 as grid congestion has worsened, which is exactly the
#   growing-curtailment trend this project's own `../markdown/index.md`
#   already flags as expected "to become more common, not less, as
#   renewable penetration grows."
# - **Hour of day**: the sharp, localized dip around 10-11 UTC is *not* a
#   curtailment/oversupply signature after all -- it lines up exactly with
#   a documented ERA5 artifact already called out in this project's own
#   `pecdr/domain.py`: "ERA5 has a documented spurious wind-speed dip at
#   [10:00 UTC], which PECD corrects via interpolation as a separate
#   preprocessing step not yet replicated here." Approach 1 (PECD's own
#   product, which does apply that correction) shows a much shallower dip
#   at the same hour than approach 3 (this project's replication, which
#   doesn't), consistent with this being substantially an uncorrected
#   input-data artifact in our pipeline rather than a distinct physical
#   effect. Concrete, fixable follow-up: interpolate across 10:00 UTC in
#   the raw ERA5 wind speed before running it through the rest of the
#   pipeline, the way PECD itself does.
# - **Oversupply proxy**: bias climbs with renewable share of load, but
#   this ratio is highly collinear with CF level itself (wind dominates the
#   numerator here), so this panel is largely a restatement of the first
#   result rather than independent evidence for oversupply-driven
#   curtailment specifically.
#
# Net: the CF-level, seasonal, and year-over-year patterns all support
# treating most of the remaining bias as wind-speed-driven curtailment/
# shutdown that neither PECD's own product nor this replication attempts
# to model -- which is what makes a **CF-conditional statistical
# correction** (e.g. quantile mapping, binned by CF level) a reasonable
# next step for anyone consuming this as a forecasting feature. The
# diurnal dip, on the other hand, looks like a specific, fixable
# ERA5-interpolation gap rather than a modeling limitation to correct for
# statistically.
