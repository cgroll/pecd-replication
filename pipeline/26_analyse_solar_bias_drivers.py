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
# # What drives the solar gap against SMARD?
#
# `25_compare_solar_approaches` found approach 1 (PECD official x
# MaStR-by-technology capacity) tracks SMARD reasonably well overall
# (corr=0.940, MAE=0.033) but with a small positive bias that grows over
# the backtest period (2018: 0.006, 2025: 0.026). This notebook checks two
# distinct candidate explanations, mirroring `22_analyse_bias_drivers`'s
# wind investigation but adapted for what's actually different about
# solar:
#
# - **Curtailment, growing over time** -- the same pattern found for wind,
#   where the bias stepped up after 2022-2023 alongside real, reported
#   increases in German curtailment. If solar shows the same CF-level and
#   year-over-year shape, that's evidence for the same explanation.
# - **Behind-the-meter self-consumption** -- specific to solar: MaStR's
#   `pv_category` shows ~44% of German solar capacity is
#   self-consumption (with or without storage), which SMARD's *net*
#   grid-injected generation figure never sees (see `../markdown/index.md`'s
#   "behind-the-meter blind spot"). Since our modeled series is a *gross*
#   capacity factor, periods/eras with a higher self-consumption capacity
#   share should show a larger gap if this is a real contributor -- a
#   check wind never needed, since wind has negligible self-consumption.

# %%
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from pecdr.capacity_weighting import capacity_weighted_cf, hourly_capacity_by_zone, total_hourly_capacity
from pecdr.paths import ProjPaths

paths = ProjPaths()
paths.ensure_directories()

# %% [markdown]
# ## Rebuild approach 1 vs. SMARD, same as `25_compare_solar_approaches`

# %%
solar_capacity_month = pd.read_parquet(paths.solar_capacity_by_nuts2_month_file)

pecd_solar_cf = pd.read_parquet(paths.pecd_solar_capacity_factors_file)
pecd_solar_cf.columns = [f"{tech}_{region}" for tech, region in pecd_solar_cf.columns]

tech_region_capacity = solar_capacity_month.copy()
tech_region_capacity["region_code"] = tech_region_capacity["pecd_technology"] + "_" + tech_region_capacity["nuts2_region"]
model_cf = capacity_weighted_cf(pecd_solar_cf, tech_region_capacity)

target_panel = pd.read_parquet(paths.target_panel_file)
total_region_capacity = solar_capacity_month.groupby(["nuts2_region", "month"])["capacity_mw"].sum().reset_index()
total_region_capacity = total_region_capacity.rename(columns={"nuts2_region": "region_code"})
total_capacity_hourly = total_hourly_capacity(total_region_capacity, target_panel.index)
smard_cf = target_panel["pv"] / total_capacity_hourly

comparison = pd.DataFrame({"model_cf": model_cf, "smard_cf": smard_cf}).dropna()
comparison["diff"] = comparison["model_cf"] - comparison["smard_cf"]

# Self-consumption capacity share, national, broadcast to hourly -- reuses
# `hourly_capacity_by_zone` with `pv_category` as the "zone" key, exactly
# as it's normally used for a spatial zone.
pv_category_month = pd.read_parquet(paths.solar_capacity_by_pv_category_month_file)
pv_category_hourly = hourly_capacity_by_zone(pv_category_month, comparison.index, zone_col="pv_category")
self_consumption_cols = [c for c in ["self_consumption_no_storage", "self_consumption_with_storage"] if c in pv_category_hourly.columns]
comparison["self_consumption_share"] = pv_category_hourly[self_consumption_cols].sum(axis=1) / pv_category_hourly.sum(axis=1)

print(f"Hours compared: {len(comparison):,}")
print(f"Bias: {comparison['diff'].mean():.4f}, MAE: {comparison['diff'].abs().mean():.4f}, corr: {comparison['model_cf'].corr(comparison['smard_cf']):.4f}")

# %% [markdown]
# ## 1. Does the bias grow with capacity-factor level?

# %%
bins = np.linspace(0, comparison["smard_cf"].max(), 21)
comparison["cf_bin"] = pd.cut(comparison["smard_cf"], bins)
bin_mid = [interval.mid for interval in comparison["cf_bin"].cat.categories]
bin_stats = comparison.groupby("cf_bin", observed=True)["diff"].mean().reindex(comparison["cf_bin"].cat.categories)

fig, ax = plt.subplots(figsize=(9, 5))
ax.bar(bin_mid, bin_stats, width=(bin_mid[1] - bin_mid[0]) * 0.8, color="#4C72B0")
ax.axhline(0, color="k", linewidth=0.8)
ax.set_xlabel("SMARD-implied CF (binned)")
ax.set_ylabel("Mean bias (model - SMARD)")
ax.set_title("Bias vs. capacity-factor level")
fig.tight_layout()
fig.savefig(paths.images_path / "26_bias_vs_cf_level.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/26_bias_vs_cf_level.png
# :name: fig-26-bias-vs-cf-level
# Mean bias (model minus SMARD-implied CF) by SMARD CF bin.
# ```

# %% [markdown]
# ## 2. Seasonal pattern: bias by month

# %%
monthly = comparison.groupby(comparison.index.month)["diff"].mean()

fig, ax = plt.subplots(figsize=(9, 5))
ax.bar(monthly.index, monthly, color="#4C72B0")
ax.axhline(0, color="k", linewidth=0.8)
ax.set_xticks(monthly.index)
ax.set_xlabel("Month")
ax.set_ylabel("Mean bias (model - SMARD)")
ax.set_title("Bias by month")
fig.tight_layout()
fig.savefig(paths.images_path / "26_bias_by_month.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/26_bias_by_month.png
# :name: fig-26-bias-by-month
# Mean bias by calendar month.
# ```

# %% [markdown]
# ## 3. Diurnal pattern: bias by hour of day

# %%
hourly = comparison.groupby(comparison.index.hour)["diff"].mean()

fig, ax = plt.subplots(figsize=(9, 5))
ax.plot(hourly.index, hourly, marker="o", markersize=4, color="#4C72B0")
ax.axhline(0, color="k", linewidth=0.8)
ax.set_xlabel("Hour of day (UTC)")
ax.set_ylabel("Mean bias (model - SMARD)")
ax.set_title("Bias by hour of day")
fig.tight_layout()
fig.savefig(paths.images_path / "26_bias_by_hour.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/26_bias_by_hour.png
# :name: fig-26-bias-by-hour
# Mean bias by hour of day.
# ```

# %% [markdown]
# ## 4. Does the bias hold up year to year?

# %%
yearly = comparison.groupby(comparison.index.year).agg(bias=("diff", "mean"), mae=("diff", lambda s: s.abs().mean()))

fig, ax = plt.subplots(figsize=(9, 5))
ax.bar(yearly.index.astype(str), yearly["bias"], color="#4C72B0")
ax.axhline(0, color="k", linewidth=0.8)
ax.set_xlabel("Year")
ax.set_ylabel("Mean bias (model - SMARD)")
ax.set_title("Bias by year")
fig.tight_layout()
fig.savefig(paths.images_path / "26_bias_by_year.png", dpi=150, bbox_inches="tight")
plt.show()

yearly

# %% [markdown]
# ```{figure} ../../output/images/26_bias_by_year.png
# :name: fig-26-bias-by-year
# Mean bias by year.
# ```

# %% [markdown]
# ## 5. Bias vs. self-consumption capacity share
#
# If behind-the-meter self-consumption is a real contributor, bias should
# climb as the self-consumed share of the fleet grows -- independent of
# (though potentially confounded with, since self-consumption capacity has
# also grown over time) the year-over-year pattern above.

# %%
share_bins = np.linspace(comparison["self_consumption_share"].min(), comparison["self_consumption_share"].max(), 16)
comparison["share_bin"] = pd.cut(comparison["self_consumption_share"], share_bins)
share_mid = [interval.mid for interval in comparison["share_bin"].cat.categories]
share_stats = comparison.groupby("share_bin", observed=True)["diff"].mean().reindex(comparison["share_bin"].cat.categories)

fig, ax = plt.subplots(figsize=(9, 5))
ax.bar(share_mid, share_stats, width=(share_mid[1] - share_mid[0]) * 0.8, color="#4C72B0")
ax.axhline(0, color="k", linewidth=0.8)
ax.set_xlabel("Self-consumption capacity share (binned)")
ax.set_ylabel("Mean bias (model - SMARD)")
ax.set_title("Bias vs. self-consumption capacity share")
fig.tight_layout()
fig.savefig(paths.images_path / "26_bias_vs_self_consumption.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/26_bias_vs_self_consumption.png
# :name: fig-26-bias-vs-self-consumption
# Mean bias vs. self-consumption capacity share.
# ```

# %% [markdown]
# ## Summary

# %%
print(f"Self-consumption share range in this backtest: {comparison['self_consumption_share'].min():.3f} - {comparison['self_consumption_share'].max():.3f}")
summary = pd.DataFrame({"bias": [comparison["diff"].mean()], "MAE": [comparison["diff"].abs().mean()]})
summary

# %% [markdown]
# ## Takeaways
#
# The diurnal chart above was the real finding of this notebook, and it
# doesn't look like it belongs in the same "curtailment" story as wind's:
# testing a range of hour shifts between the model and SMARD series (not
# shown here, done as a one-off check) found that PECD's solar CF product
# runs **1 hour ahead of true UTC** -- shifting it back cuts MAE against
# SMARD roughly in half (0.033 -> 0.016) and correlation rises from 0.940
# to 0.982, consistently across every year, not just on average. The same
# shift test on PECD's *wind* product found no such improvement, so this
# isn't a bug in how this project reads PECD's files (`pecdr.pecd_io`
# handles both identically) -- it's specific to PECD's own solar product,
# plausibly inherited from ERA5's solar-radiation fields being
# *accumulated over the preceding hour* while wind speed is instantaneous,
# a labeling convention PECD's solar product doesn't appear to correct for.
# Fixed at the source in `pipeline/17_process_pecd_capacity_factors.py`;
# every number in this notebook and in `25_compare_solar_approaches`
# already reflects the correction.
#
# With that artifact removed, what's left is smaller and a genuinely
# different shape than wind's monotonic curtailment pattern: bias is
# positive across most of the CF range but **flips negative at the very
# highest CF bins** (clear-sky summer middays) -- the opposite direction
# curtailment would push it. Not yet explained; a candidate worth checking
# before assuming it's physical is whether the monthly capacity snapshot
# used for weighting lags Germany's rapid recent solar build-out within
# a given month, understating capacity (and so overstating CF) precisely
# when a month's true capacity was still rising toward its end.
#
# The year-over-year growth in bias (2018: 0.006 -> 2025: 0.026) survives
# the timestamp fix unchanged, and self-consumption share tracks it
# closely too -- but self-consumption share has grown monotonically over
# the same period, so this notebook can't separate "more curtailment over
# time" from "more self-consumption over time" from these two panels
# alone. Both remain plausible, real, solar-specific contributors to
# revisit once the per-plant physics replication (this workstream's
# still-open Phase B) gives an independent way to cross-check.
