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
# # Comparing all three physically-motivated feature approaches, plus SMARD
#
# This project sits alongside two other ways of turning weather + MaStR
# capacity into a wind-onshore capacity factor, all developed across
# `mastr-power-capacities-germany`, `delu-headline-forecast`, and this
# project. Laid out from least to most physically detailed:
#
# 1. **PECD's own PEON zone capacity factor x MaStR zone capacity**
#    (`~/research/delu-headline-forecast/dhf/pecd.py`) -- trusts PECD's
#    official numbers wholesale, just reweights them by MaStR's installed
#    capacity. No bias adjustment or per-turbine detail *by construction* --
#    it's already PECD's finished product.
# 2. **Physics-based reconstruction from raw ERA5 + MaStR**
#    (`~/research/delu-headline-forecast/dhf/physics.py`) -- computed from
#    scratch, but with the simplest possible physics: one generic turbine
#    power curve for the entire fleet, no GWA2 bias correction.
# 3. **This project's PECD replication** -- computed from scratch with
#    PECD's actual documented methodology as closely as achievable: GWA2
#    bias-adjusted wind speed, alpha-based hub-height extrapolation,
#    per-plant power curves (real matched curve or specific-power-based
#    generic fallback).
#
# Plus **SMARD's actual DE-LU wind-onshore generation** as the real-world
# ground truth none of the three are derived from.
#
# All four series now use a fleet-vintage-correct weighting: approaches 1,
# 2, and the SMARD-implied CF use MaStR's *time-varying* monthly capacity
# as the weighting denominator (`pecdr.capacity_weighting`); approach 3
# (this project) runs each year's weather through **that year's own**
# start-of-year fleet (`pipeline/08_build_wind_onshore_plant_panel.py`,
# `pipeline/10_compute_wind_onshore_full_year.py`) rather than today's
# fleet applied retroactively.

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
# ## Load all four series, all as capacity factor, restricted to the common backtest period

# %%
mastr_peon_month = pd.read_parquet(paths.mastr_capacity_by_peon_month_file)

# Approach 1: PECD's own PEON zone CF x time-varying MaStR PEON capacity
pecd_peon_cf = pd.read_parquet(paths.pecd_wind_onshore_capacity_factors_file)
approach1 = capacity_weighted_cf(pecd_peon_cf, mastr_peon_month)

# Approach 2: delu's own raw-ERA5 + generic-curve PEON zone CF, same weights
delu_own_cf = pd.read_parquet(paths.delu_own_wind_onshore_capacity_factors_file)
delu_own_cf.index.name = "timestamp"
approach2 = capacity_weighted_cf(delu_own_cf, mastr_peon_month)

# Approach 3: this project's replication (already national, each year's own fleet)
approach3 = pd.read_parquet(paths.wind_onshore_full_year_cf_file)["national"]

# SMARD actual generation (MW) -> implied CF via time-varying total capacity
target_panel = pd.read_parquet(paths.target_panel_file)
total_capacity_hourly = total_hourly_capacity(mastr_peon_month, target_panel.index)
smard_implied_cf = target_panel["wind_onshore"] / total_capacity_hourly

comparison = pd.DataFrame({
    "1_pecd_official_x_mastr": approach1,
    "2_delu_physics_no_bias": approach2,
    "3_pecd_replication": approach3,
    "4_smard_implied": smard_implied_cf,
})
comparison = comparison.loc[FULL_YEAR_BACKTEST_YEARS[0]:FULL_YEAR_BACKTEST_YEARS[-1]].dropna(how="all")
print(f"Hours with at least one series: {len(comparison):,}")
comparison.describe()

# %% [markdown]
# ## Full-period time series, all four series

# %%
fig, ax = plt.subplots(figsize=(14, 5))
for col, label in [
    ("1_pecd_official_x_mastr", "1. PECD official x MaStR"),
    ("2_delu_physics_no_bias", "2. delu physics (no bias, generic curve)"),
    ("3_pecd_replication", "3. This project's PECD replication"),
    ("4_smard_implied", "4. SMARD actual (implied CF)"),
]:
    comparison[col].plot(ax=ax, label=label, alpha=0.7, linewidth=0.3)
ax.set_ylabel("Germany-wide onshore wind capacity factor")
ax.set_title(f"All four approaches, {PERIOD_LABEL}")
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "12_all_approaches_timeseries.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/12_all_approaches_timeseries.png
# :name: fig-12-all-approaches-timeseries
# All four wind-onshore capacity factor series, 2019-2025.
# ```

# %% [markdown]
# ## Each modeled approach vs. SMARD's actual (implied) capacity factor
#
# SMARD is the one series here nobody derived their number from -- the
# genuine external ground truth, unlike approach 1 vs. 3 (which both trace
# back to PECD in different ways) or approach 2 vs. 3 (both derived from the
# same raw ERA5).

# %%
stats_rows = []
fig, axes = plt.subplots(1, 3, figsize=(16, 5))
for ax, col, label in zip(axes, ["1_pecd_official_x_mastr", "2_delu_physics_no_bias", "3_pecd_replication"], ["1. PECD official x MaStR", "2. delu physics", "3. PECD replication"]):
    sub = comparison[[col, "4_smard_implied"]].dropna()
    diff = sub[col] - sub["4_smard_implied"]
    corr = sub[col].corr(sub["4_smard_implied"])
    stats_rows.append({"approach": label, "n_hours": len(sub), "mae": float(diff.abs().mean()), "bias": float(diff.mean()), "corr": float(corr)})

    ax.scatter(sub["4_smard_implied"], sub[col], s=2, alpha=0.05)
    lims = [0, max(sub.max())]
    ax.plot(lims, lims, "k--", alpha=0.5, label="1:1")
    ax.set_xlabel("SMARD-implied CF")
    ax.set_ylabel(f"{label} CF")
    ax.set_title(f"{label}\nMAE={diff.abs().mean():.3f}, corr={corr:.3f}")
fig.tight_layout()
fig.savefig(paths.images_path / "12_approaches_vs_smard.png", dpi=150, bbox_inches="tight")
plt.show()

stats = pd.DataFrame(stats_rows)
stats

# %% [markdown]
# ```{figure} ../../output/images/12_approaches_vs_smard.png
# :name: fig-12-approaches-vs-smard
# Each modeled approach vs. SMARD's actual (implied) capacity factor, 2019-2025.
# ```

# %% [markdown]
# ## Does each approach's fit to SMARD hold up year to year?
#
# The pooled stats above could hide a single unusual year. Breaking out
# bias/MAE/corr by year checks whether the fit is stable across the whole
# backtest period, not just true on average.

# %%
yearly_rows = []
for col, label in [
    ("1_pecd_official_x_mastr", "1. PECD official x MaStR"),
    ("2_delu_physics_no_bias", "2. delu physics"),
    ("3_pecd_replication", "3. PECD replication"),
]:
    sub = comparison[[col, "4_smard_implied"]].dropna()
    diff = sub[col] - sub["4_smard_implied"]
    for year, group in diff.groupby(diff.index.year):
        approach_group = sub.loc[group.index, col]
        smard_group = sub.loc[group.index, "4_smard_implied"]
        yearly_rows.append({
            "approach": label,
            "year": year,
            "n_hours": len(group),
            "mae": float(group.abs().mean()),
            "bias": float(group.mean()),
            "corr": float(approach_group.corr(smard_group)),
        })

yearly_stats = pd.DataFrame(yearly_rows).pivot(index="year", columns="approach", values=["bias", "mae", "corr"])
yearly_stats
