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
# # Solar PV: full-period comparison, technology-aware chain vs. PECD vs. SMARD
#
# Extends `25_compare_solar_approaches` (PECD's own product vs. this
# project's original simple physics baseline vs. SMARD, over the full
# available period) with a third series: the technology- and
# orientation-aware, **PECD-documented physics chain** validated against
# PECD's own product in `27_verify_solar_technology_physics` -- there,
# only on 3 selected days. `pipeline/28_compute_solar_full_year.py` runs
# that same chain over every hour of every year in
# `pecdr.domain.FULL_YEAR_BACKTEST_YEARS` (2019-2025), so this notebook
# can finally ask the question pipeline/27 couldn't: does matching PECD's
# own product more closely (corr 0.934 vs. the original baseline's
# untested match to PECD) also mean matching *reality* (SMARD's actual
# generation) more closely? Matching PECD's own idiosyncrasies and
# matching the real world are not the same claim.
#
# Four series total:
# 1. PECD's own NUTS2 x technology CF x MaStR capacity (unchanged from 25)
# 2. This project's original simple physics baseline (unchanged from 25)
# 3. **New**: the technology- and orientation-aware, PECD-documented chain
#
# Plus SMARD's actual DE-LU PV generation as the real-world ground truth
# none of the three are derived from.

# %%
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from pecdr.capacity_weighting import capacity_weighted_cf, total_hourly_capacity
from pecdr.domain import FULL_YEAR_BACKTEST_YEARS
from pecdr.paths import ProjPaths

paths = ProjPaths()
paths.ensure_directories()

# %% [markdown]
# ## Load all four series, all as capacity factor

# %%
solar_capacity_month = pd.read_parquet(paths.solar_capacity_by_nuts2_month_file)

# Approach 1: PECD's own product x time-varying MaStR capacity (same as pipeline/25).
pecd_solar_cf = pd.read_parquet(paths.pecd_solar_capacity_factors_file)
pecd_solar_cf.columns = [f"{tech}_{region}" for tech, region in pecd_solar_cf.columns]
tech_region_capacity = solar_capacity_month.copy()
tech_region_capacity["region_code"] = tech_region_capacity["pecd_technology"] + "_" + tech_region_capacity["nuts2_region"]
approach1 = capacity_weighted_cf(pecd_solar_cf, tech_region_capacity)

# Approach 2: this project's original simple physics baseline (same as pipeline/25).
own_solar_cf = pd.read_parquet(paths.own_solar_capacity_factors_file)
total_region_capacity = solar_capacity_month.groupby(["nuts2_region", "month"])["capacity_mw"].sum().reset_index()
total_region_capacity = total_region_capacity.rename(columns={"nuts2_region": "region_code"})
approach2 = capacity_weighted_cf(own_solar_cf, total_region_capacity)

# Approach 3: the new technology- and orientation-aware, PECD-documented
# chain (pipeline/27, pipeline/28) -- same (technology, region) weighting
# as approach 1, since it's computed at the same NUTS2 x technology
# resolution as PECD's own product.
own_full_year_cf = pd.read_parquet(paths.own_solar_full_year_cf_file)
own_full_year_cf.columns = [f"{tech}_{region}" for tech, region in own_full_year_cf.columns]
approach3 = capacity_weighted_cf(own_full_year_cf, tech_region_capacity)

# SMARD actual generation (MW) -> implied CF via time-varying total capacity.
target_panel = pd.read_parquet(paths.target_panel_file)
total_capacity_hourly = total_hourly_capacity(total_region_capacity, target_panel.index)
smard_implied_cf = target_panel["pv"] / total_capacity_hourly

comparison = pd.DataFrame({
    "1_pecd_official_x_mastr": approach1,
    "2_own_simple_baseline": approach2,
    "3_own_documented_chain": approach3,
    "4_smard_implied": smard_implied_cf,
}).dropna(how="all")
# Restrict to the period the new chain (approach 3) actually covers.
comparison = comparison.loc[f"{FULL_YEAR_BACKTEST_YEARS[0]}-01-01":f"{FULL_YEAR_BACKTEST_YEARS[-1]}-12-31"]
print(f"Hours with at least one series: {len(comparison):,}")
comparison.describe()

# %% [markdown]
# ## Full-period time series

# %%
fig, ax = plt.subplots(figsize=(14, 5))
for col, label in [
    ("1_pecd_official_x_mastr", "1. PECD official x MaStR"),
    ("2_own_simple_baseline", "2. Original simple physics baseline"),
    ("3_own_documented_chain", "3. New: technology-aware, PECD-documented chain"),
    ("4_smard_implied", "4. SMARD actual (implied CF)"),
]:
    comparison[col].plot(ax=ax, label=label, alpha=0.7, linewidth=0.3)
ax.set_ylabel("Germany-wide solar PV capacity factor")
ax.set_title(f"All four series, {FULL_YEAR_BACKTEST_YEARS[0]}-{FULL_YEAR_BACKTEST_YEARS[-1]}")
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "29_solar_full_year_timeseries.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/29_solar_full_year_timeseries.png
# :name: fig-29-solar-full-year-timeseries
# All four solar capacity factor series, 2019-2025.
# ```

# %% [markdown]
# ## Each modeled approach vs. SMARD's actual (implied) capacity factor
#
# The real test: does the new, technology-aware chain -- which matches
# PECD's own product noticeably better than the original baseline did
# (pipeline/27: corr 0.934) -- also match SMARD's real generation better
# than the original simple baseline does? Or does it just match PECD's
# own idiosyncrasies more closely without being closer to reality?

# %%
stats_rows = []
fig, axes = plt.subplots(1, 3, figsize=(15, 5.5), sharex=True, sharey=True)
approaches = [
    ("1_pecd_official_x_mastr", "1. PECD official x MaStR"),
    ("2_own_simple_baseline", "2. Original simple baseline"),
    ("3_own_documented_chain", "3. New documented chain"),
]
for ax, col, label in zip(axes, [a[0] for a in approaches], [a[1] for a in approaches]):
    sub = comparison[[col, "4_smard_implied"]].dropna()
    diff = sub[col] - sub["4_smard_implied"]
    corr = sub[col].corr(sub["4_smard_implied"])
    stats_rows.append({"approach": label, "n_hours": len(sub), "mae": float(diff.abs().mean()), "bias": float(diff.mean()), "corr": float(corr)})

    ax.scatter(sub["4_smard_implied"], sub[col], s=2, alpha=0.1)
    lims = [0, max(sub.max())]
    ax.plot(lims, lims, "k--", alpha=0.5, label="1:1")
    ax.set_xlabel("SMARD-implied CF")
    ax.set_title(f"{label}\nMAE={diff.abs().mean():.3f}, corr={corr:.3f}")
axes[0].set_ylabel("Modeled CF")
fig.tight_layout()
fig.savefig(paths.images_path / "29_solar_full_year_vs_smard.png", dpi=150, bbox_inches="tight")
plt.show()

stats = pd.DataFrame(stats_rows)
stats

# %% [markdown]
# ```{figure} ../../output/images/29_solar_full_year_vs_smard.png
# :name: fig-29-solar-full-year-vs-smard
# Each modeled approach vs. SMARD's actual (implied) PV capacity factor, 2019-2025.
# ```

# %% [markdown]
# ## Does the new chain's bias grow with capacity-factor level?
#
# Same hypothesis test wind's `pipeline/11` ran: pooled across all years,
# does the new chain's error trend with SMARD's own output level, or sit
# flat across the whole range?

# %%
sub3 = comparison[["3_own_documented_chain", "4_smard_implied"]].dropna()
sub3["diff"] = sub3["3_own_documented_chain"] - sub3["4_smard_implied"]

fig, axes = plt.subplots(1, 2, figsize=(13, 5))
axes[0].scatter(sub3["4_smard_implied"], sub3["3_own_documented_chain"], s=2, alpha=0.1)
lims = [0, max(sub3["4_smard_implied"].max(), sub3["3_own_documented_chain"].max())]
axes[0].plot(lims, lims, "k--", alpha=0.5, label="1:1")
axes[0].set_xlabel("SMARD-implied CF")
axes[0].set_ylabel("New documented-chain CF")
axes[0].set_title(f"Hourly, {FULL_YEAR_BACKTEST_YEARS[0]}-{FULL_YEAR_BACKTEST_YEARS[-1]}")
axes[0].legend()

bins = np.linspace(0, max(sub3["4_smard_implied"].max(), 0.01), 21)
sub3["cf_bin"] = pd.cut(sub3["4_smard_implied"], bins)
bin_stats = sub3.groupby("cf_bin", observed=True)["diff"].agg(["mean", "count"])
bin_centers = [interval.mid for interval in bin_stats.index]
axes[1].bar(bin_centers, bin_stats["mean"], width=(bins[1] - bins[0]) * 0.8)
axes[1].axhline(0, color="k", linewidth=0.8)
axes[1].set_xlabel("SMARD-implied CF (binned)")
axes[1].set_ylabel("Mean bias (ours - SMARD)")
axes[1].set_title("Bias vs. capacity-factor level")

fig.tight_layout()
fig.savefig(paths.images_path / "29_bias_vs_cf_level.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/29_bias_vs_cf_level.png
# :name: fig-29-bias-vs-cf-level
# Left: hourly scatter, new chain vs. SMARD, 2019-2025. Right: mean bias by SMARD capacity-factor bin.
# ```

# %% [markdown]
# ## Does each approach's fit to SMARD hold up year to year?

# %%
yearly_rows = []
for col, label in approaches:
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

# %% [markdown]
# ## Takeaways
#
# Full 2019-2025 backtest (61,368 hours), each approach vs. SMARD's
# actual (implied) capacity factor:
#
# | approach | bias | MAE | corr |
# |---|---|---|---|
# | 1. PECD official x MaStR | 0.010 | 0.016 | 0.981 |
# | 2. Original simple physics baseline | 0.047 | 0.057 | 0.926 |
# | **3. New technology-aware, PECD-documented chain** | **0.032** | **0.046** | **0.937** |
#
# **The new chain is a real, consistent improvement over the original
# simple baseline** -- lower bias, lower MAE, higher correlation, in
# *every single year* 2019-2025 (see `yearly_stats` above), not just on
# average. Matching PECD's own product more closely (pipeline/27: corr
# 0.934 on 3 selected days) turns out to also mean matching reality more
# closely, at least directionally -- that wasn't guaranteed going in,
# since the two claims (matching PECD vs. matching SMARD) are logically
# separate.
#
# **But PECD's own official product remains substantially closer to
# SMARD than either of this project's own-physics approaches** -- roughly
# a 3x smaller MAE and a much tighter scatter (see the 3-panel comparison
# above). PECD's pipeline evidently includes calibration against real
# generation data and/or loss terms this replication doesn't have or
# couldn't reconcile (the still-unresolved inverter-loss step from
# pipeline/27, most likely, plus whatever else isn't documented in the
# PUG at all).
#
# **The new chain systematically over-predicts, and the over-prediction
# grows sharply with output level**, saturating around a +0.08-0.09 CF
# bias above roughly 30% capacity factor (see the bias-vs-level chart).
# Two standing candidates, neither newly ruled in or out by this
# full-year run: the documented inverter-loss polynomial (pipeline/27
# found it makes the match against PECD's own product *worse* when
# applied as written, so it's currently omitted -- but omitting it may
# just be trading one bias for another when compared against real
# generation instead of PECD's product), and unmodeled self-consumption
# (rooftop generation consumed behind the meter never reaches SMARD's
# measured feed-in, and disproportionately so during high-output hours --
# the same hypothesis `pipeline/26_analyse_solar_bias_drivers.py` explored
# for the original baseline).
#
# **All three approaches' error vs. SMARD grows worse year over year**
# (PECD's own bias: 0.0001 in 2020 -> 0.026 in 2025; this project's new
# chain: 0.024 -> 0.046) -- including PECD's own official product, which
# isn't affected by any modeling choice this project makes. That points
# to something external to all three physics chains: growing
# self-consumption share, unmodeled degradation, or a shifting technology
# mix not fully captured by MaStR's own classification -- worth its own
# investigation before trusting any of these approaches for recent years
# specifically.
