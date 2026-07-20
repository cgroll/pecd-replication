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
# # Wind-onshore capacity factor: full-year 2020 comparison
#
# Extends the two-snapshot comparison (`09_replicate_wind_onshore_capacity_factor`)
# to every hour of 2020 (8,784 hours) -- made possible without any new
# downloads by reusing ~/research/delu-headline-forecast's already-downloaded
# ERA5 archive and the full-year PECD ground truth already fetched (but only
# previously read at two timestamps) in pipeline/01/02/07.
#
# This directly tests the hypothesis from the two-snapshot result: a
# systematic over-estimate that appeared only at the high-wind snapshot,
# suspected to be missing intra-farm wake losses (which scale with wind
# speed/thrust, unlike the flat "other losses" derate this project applies).
# With a full year of hours instead of one high-wind and one low-wind point,
# that hypothesis becomes testable: does the bias actually grow with wind
# speed / capacity factor level, across the whole distribution?

# %%
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from pecdr.paths import ProjPaths
from pecdr.pecd_io import load_region_timeseries_zip

paths = ProjPaths()
paths.ensure_directories()

# %% [markdown]
# ## Load our modeled series and build the PECD-implied comparison series

# %%
ours = pd.read_parquet(paths.wind_onshore_full_year_cf_file)
zone_cols = [c for c in ours.columns if c != "national"]

pecd_peon = load_region_timeseries_zip(paths.pecd_peon_capacity_factor_zip("2020"))

plants_capacity = pd.read_parquet(paths.wind_onshore_plant_panel_file).groupby("peon_zone")["capacity_mw"].sum()
weights = plants_capacity.reindex(zone_cols)
pecd_national = (pecd_peon[zone_cols] * weights).sum(axis=1) / weights.sum()
pecd_national = pecd_national.reindex(ours.index)

comparison = pd.DataFrame({"our_national_cf": ours["national"], "pecd_implied_national_cf": pecd_national}).dropna()
comparison["diff"] = comparison["our_national_cf"] - comparison["pecd_implied_national_cf"]
print(f"Hours compared: {len(comparison):,}")
print(f"Overall MAE: {comparison['diff'].abs().mean():.4f}")
print(f"Overall bias: {comparison['diff'].mean():.4f}")
print(f"Overall correlation: {comparison['our_national_cf'].corr(comparison['pecd_implied_national_cf']):.4f}")

# %% [markdown]
# ## Time series, full year

# %%
fig, ax = plt.subplots(figsize=(14, 4))
comparison["our_national_cf"].plot(ax=ax, label="Our modeled national CF", alpha=0.8, linewidth=0.6)
comparison["pecd_implied_national_cf"].plot(ax=ax, label="PECD-implied national CF", alpha=0.8, linewidth=0.6)
ax.set_ylabel("Germany-wide onshore wind CF")
ax.set_title("Full-year 2020: our modeled vs. PECD-implied national capacity factor")
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "11_full_year_timeseries.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/11_full_year_timeseries.png
# :name: fig-11-full-year-timeseries
# Full year 2020, hourly: our modeled vs. PECD-implied national capacity factor.
# ```

# %% [markdown]
# ## Does the bias grow with wind speed / capacity factor level?
#
# Directly tests the two-snapshot hypothesis: if missing wake losses (which
# scale with wind speed/thrust) are the driver, bias should trend upward as
# PECD's own capacity factor increases, not sit flat across the whole range.

# %%
fig, axes = plt.subplots(1, 2, figsize=(13, 5))

axes[0].scatter(comparison["pecd_implied_national_cf"], comparison["our_national_cf"], s=2, alpha=0.2)
lims = [0, 1]
axes[0].plot(lims, lims, "k--", alpha=0.5, label="1:1")
axes[0].set_xlabel("PECD-implied national CF")
axes[0].set_ylabel("Our modeled national CF")
axes[0].set_title("Hourly, all of 2020")
axes[0].legend()

bins = np.linspace(0, 1, 21)
comparison["cf_bin"] = pd.cut(comparison["pecd_implied_national_cf"], bins)
bin_stats = comparison.groupby("cf_bin", observed=True)["diff"].agg(["mean", "count"])
bin_centers = [interval.mid for interval in bin_stats.index]
axes[1].bar(bin_centers, bin_stats["mean"], width=0.04)
axes[1].axhline(0, color="k", linewidth=0.8)
axes[1].set_xlabel("PECD-implied national CF (binned)")
axes[1].set_ylabel("Mean bias (ours - PECD)")
axes[1].set_title("Bias vs. capacity-factor level")

fig.tight_layout()
fig.savefig(paths.images_path / "11_bias_vs_cf_level.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/11_bias_vs_cf_level.png
# :name: fig-11-bias-vs-cf-level
# Left: hourly scatter, all of 2020. Right: mean bias by PECD capacity-factor bin -- tests whether bias grows with wind speed/output level.
# ```

# %% [markdown]
# ## Monthly aggregates

# %%
monthly = comparison.resample("ME").agg(our_mean=("our_national_cf", "mean"), pecd_mean=("pecd_implied_national_cf", "mean"))
monthly["diff"] = monthly["our_mean"] - monthly["pecd_mean"]
monthly.index = monthly.index.strftime("%Y-%m")
monthly
