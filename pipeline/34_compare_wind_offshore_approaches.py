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
# # Comparing all wind-offshore approaches, plus SMARD
#
# Same comparison as onshore's `12_compare_all_approaches`, adapted to three
# approaches (there's no offshore equivalent of the `delu-headline-forecast`
# sibling project's baseline to reuse as a fourth):
#
# 1. **PECD's own PEOF zone capacity factor x MaStR zone capacity** --
#    trusts PECD's official numbers wholesale, just reweights them by
#    MaStR's installed capacity.
# 2. **This project's own naive physics baseline** (`pipeline/20`) --
#    computed from scratch with the simplest possible physics: one generic
#    turbine power curve for the entire fleet, raw ERA5, no bias
#    correction. This is the "without PECD data" replication.
# 3. **This project's PECD replication** (`pipeline/30`-`32`) -- computed
#    from scratch with PECD's actual documented methodology as closely as
#    achievable: GWA2 bias-adjusted wind speed where available (else raw
#    ERA5 -- see `31`'s docstring), alpha-based hub-height extrapolation,
#    per-plant power curves. No storm-shutdown derate (see `31`/`32`'s
#    docstrings for why).
#
# Plus **SMARD's actual DE-LU wind-offshore generation** as the real-world
# ground truth none of the three are derived from.
#
# All series use a fleet-vintage-correct weighting: approaches 1 and 2, and
# the SMARD-implied CF, use MaStR's *time-varying* monthly PEOF capacity as
# the weighting denominator (`pecdr.capacity_weighting`); approach 3 runs
# each year's weather through **that year's own** start-of-year fleet
# (`pipeline/30`, `pipeline/32`) rather than today's fleet applied
# retroactively.

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
# ## Load all series, all as capacity factor, restricted to the common backtest period
#
# One data-quality wrinkle in approach 1: 3 of PECD's 6 PEOF zones
# (`DE013_OFF`/`DE014_OFF`/`DE015_OFF`) are **100% `NaN`** in PECD's own
# product across the entire 2015-2025 file -- PECD apparently never
# modeled them. `DE013_OFF` still carries real MaStR capacity (up to
# ~300 MW). Passing all 6 zones into `capacity_weighted_cf` unfiltered
# would silently dilute its capacity-weighted denominator with this
# dead-weight capacity -- `DE013_OFF`'s real MW counts toward "total
# capacity" but contributes nothing to the numerator, since pandas'
# default `skipna` sum just drops its `NaN` CF -- systematically pulling
# approach 1's implied CF down for no real-world reason. Restricting to
# the zones PECD actually has data for avoids that; found and confirmed
# while building notebook 35's capacity-fitting exercise.

# %%
mastr_peof_month = pd.read_parquet(paths.mastr_capacity_by_peof_month_file)

# Approach 1: PECD's own PEOF zone CF x time-varying MaStR PEOF capacity,
# restricted to the zones PECD actually models (see note above).
pecd_peof_cf = pd.read_parquet(paths.pecd_wind_offshore_capacity_factors_file)
pecd_modeled_zones = pecd_peof_cf.columns[pecd_peof_cf.notna().any()].tolist()
approach1 = capacity_weighted_cf(pecd_peof_cf[pecd_modeled_zones], mastr_peof_month)

# Approach 2: this project's own raw-ERA5 + generic-curve PEOF zone CF, same weights
own_naive_cf = pd.read_parquet(paths.own_wind_offshore_capacity_factors_file)
own_naive_cf.index.name = "timestamp"
approach2 = capacity_weighted_cf(own_naive_cf, mastr_peof_month)

# Approach 3: this project's replication (already national, each year's own fleet)
approach3 = pd.read_parquet(paths.wind_offshore_full_year_cf_file)["national"]

# SMARD actual generation (MW) -> implied CF via time-varying total capacity
target_panel = pd.read_parquet(paths.target_panel_file)
total_capacity_hourly = total_hourly_capacity(mastr_peof_month, target_panel.index)
smard_implied_cf = target_panel["wind_offshore"] / total_capacity_hourly

comparison = pd.DataFrame({
    "1_pecd_official_x_mastr": approach1,
    "2_naive_physics_no_pecd": approach2,
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
    ("2_naive_physics_no_pecd", "2. Naive physics (no PECD data)"),
    ("3_pecd_replication", "3. This project's PECD replication"),
    ("4_smard_implied", "4. SMARD actual (implied CF)"),
]:
    comparison[col].plot(ax=ax, label=label, alpha=0.7, linewidth=0.3)
ax.set_ylabel("Germany-wide offshore wind capacity factor")
ax.set_title(f"All four approaches, {PERIOD_LABEL}")
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "34_all_approaches_timeseries.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/34_all_approaches_timeseries.png
# :name: fig-34-all-approaches-timeseries
# All four wind-offshore capacity factor series, 2019-2025.
# ```

# %% [markdown]
# ## Each modeled approach vs. SMARD's actual (implied) capacity factor

# %%
stats_rows = []
fig, axes = plt.subplots(1, 3, figsize=(16, 5))
for ax, col, label in zip(axes, ["1_pecd_official_x_mastr", "2_naive_physics_no_pecd", "3_pecd_replication"], ["1. PECD official x MaStR", "2. Naive physics (no PECD)", "3. PECD replication"]):
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
fig.savefig(paths.images_path / "34_approaches_vs_smard.png", dpi=150, bbox_inches="tight")
plt.show()

stats = pd.DataFrame(stats_rows)
stats

# %% [markdown]
# ```{figure} ../../output/images/34_approaches_vs_smard.png
# :name: fig-34-approaches-vs-smard
# Each modeled approach vs. SMARD's actual (implied) capacity factor, 2019-2025.
# ```

# %% [markdown]
# ## Does each approach's fit to SMARD hold up year to year?

# %%
yearly_rows = []
for col, label in [
    ("1_pecd_official_x_mastr", "1. PECD official x MaStR"),
    ("2_naive_physics_no_pecd", "2. Naive physics (no PECD)"),
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
