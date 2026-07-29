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
# # Wind-offshore capacity factor: full-period comparison, 2019-2025
#
# Extends the two-snapshot comparison (`31_replicate_wind_offshore_capacity_factor`)
# to every hour of every year this project's full-year backtest covers
# (`pecdr.domain.FULL_YEAR_BACKTEST_YEARS`), reusing this project's own ERA5
# archive and PECD's own multi-year processed PEOF zone capacity factor
# (`pipeline/17`).
#
# PECD's own zone capacity factor is weighted to a national figure using
# **each year's own** plant panel (`wind_offshore_plant_panel_by_year_file`),
# not today's -- otherwise this comparison would reintroduce the exact
# fleet-vintage mismatch `pipeline/32` was built to avoid.

# %%
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from pecdr.domain import FULL_YEAR_BACKTEST_YEARS
from pecdr.paths import ProjPaths

paths = ProjPaths()
paths.ensure_directories()

# %% [markdown]
# ## Load our modeled series and build the PECD-implied comparison series

# %%
ours = pd.read_parquet(paths.wind_offshore_full_year_cf_file)
zone_cols = [c for c in ours.columns if c != "national"]

pecd_peof = pd.read_parquet(paths.pecd_wind_offshore_capacity_factors_file)

pecd_national_parts = []
for year in FULL_YEAR_BACKTEST_YEARS:
    year_weights = pd.read_parquet(paths.wind_offshore_plant_panel_by_year_file(year)).groupby("peof_zone")["capacity_mw"].sum().reindex(zone_cols)
    year_slice = pecd_peof.loc[year, zone_cols]
    pecd_national_parts.append((year_slice * year_weights).sum(axis=1) / year_weights.sum())
pecd_national = pd.concat(pecd_national_parts).reindex(ours.index)

comparison = pd.DataFrame({"our_national_cf": ours["national"], "pecd_implied_national_cf": pecd_national}).dropna()
comparison["diff"] = comparison["our_national_cf"] - comparison["pecd_implied_national_cf"]
print(f"Hours compared: {len(comparison):,}")
print(f"Overall MAE: {comparison['diff'].abs().mean():.4f}")
print(f"Overall bias: {comparison['diff'].mean():.4f}")
print(f"Overall correlation: {comparison['our_national_cf'].corr(comparison['pecd_implied_national_cf']):.4f}")

# %% [markdown]
# ## Time series, full period

# %%
fig, ax = plt.subplots(figsize=(14, 4))
comparison["our_national_cf"].plot(ax=ax, label="Our modeled national CF", alpha=0.8, linewidth=0.4)
comparison["pecd_implied_national_cf"].plot(ax=ax, label="PECD-implied national CF", alpha=0.8, linewidth=0.4)
ax.set_ylabel("Germany-wide offshore wind CF")
ax.set_title(f"{FULL_YEAR_BACKTEST_YEARS[0]}-{FULL_YEAR_BACKTEST_YEARS[-1]}: our modeled vs. PECD-implied national capacity factor")
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "33_full_year_timeseries.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/33_full_year_timeseries.png
# :name: fig-33-full-year-timeseries
# 2019-2025, hourly: our modeled vs. PECD-implied national capacity factor.
# ```

# %% [markdown]
# ## Does the bias grow with wind speed / capacity factor level?

# %%
fig, axes = plt.subplots(1, 2, figsize=(13, 5))

axes[0].scatter(comparison["pecd_implied_national_cf"], comparison["our_national_cf"], s=2, alpha=0.1)
lims = [0, 1]
axes[0].plot(lims, lims, "k--", alpha=0.5, label="1:1")
axes[0].set_xlabel("PECD-implied national CF")
axes[0].set_ylabel("Our modeled national CF")
axes[0].set_title(f"Hourly, {FULL_YEAR_BACKTEST_YEARS[0]}-{FULL_YEAR_BACKTEST_YEARS[-1]}")
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
fig.savefig(paths.images_path / "33_bias_vs_cf_level.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/33_bias_vs_cf_level.png
# :name: fig-33-bias-vs-cf-level
# Left: hourly scatter, 2019-2025. Right: mean bias by PECD capacity-factor bin.
# ```

# %% [markdown]
# ## Does the bias hold up year to year?

# %%
yearly = comparison.groupby(comparison.index.year).apply(
    lambda g: pd.Series({
        "bias": g["diff"].mean(),
        "mae": g["diff"].abs().mean(),
        "corr": g["our_national_cf"].corr(g["pecd_implied_national_cf"]),
        "n_hours": len(g),
    }),
    include_groups=False,
)
yearly

# %% [markdown]
# ## Monthly aggregates

# %%
monthly = comparison.resample("ME").agg(our_mean=("our_national_cf", "mean"), pecd_mean=("pecd_implied_national_cf", "mean"))
monthly["diff"] = monthly["our_mean"] - monthly["pecd_mean"]
monthly.index = monthly.index.strftime("%Y-%m")
monthly
