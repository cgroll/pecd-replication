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
# # Solar PV: first comparison against SMARD
#
# The wind workstream's structure, applied to solar for the first time:
# two ways of turning weather + MaStR capacity into a PV capacity factor,
# neither requiring any new physics work this round (see
# `pecdr/solar_technology.py` and `pipeline/24_build_solar_capacity_by_nuts2_month.py`
# for the newly-built piece: a crosswalk from MaStR's own fields to PECD's
# 4 PV technology codes, since MaStR doesn't label units with them
# directly).
#
# 1. **PECD's own NUTS2 x technology capacity factor x MaStR capacity by
#    technology** -- trusts PECD's official numbers wholesale, reweighted
#    by Germany's actual installed capacity in each of PECD's 4 PV
#    technology segments (60/61/62/63 = industrial rooftop / residential
#    rooftop / utility fixed / utility tracking).
# 2. **This project's existing simple physics baseline**
#    (`pecdr/physics.py`'s `solar_capacity_factor` -- Erbs GHI
#    decomposition, one fixed tilt/azimuth for all of Germany, Faiman
#    cell temperature, PVWatts DC) -- no technology split, reweighted by
#    total installed capacity per NUTS2 zone regardless of technology.
#
# Plus **SMARD's actual DE-LU PV generation** as the real-world ground
# truth neither approach is derived from.
#
# **Not attempted yet**: a full per-plant physics replication using each
# plant's actual orientation/tilt (real data for this already exists in
# MaStR's `solar_technical_detail`, unlike PECD's own assumed
# tilt-distribution approach) -- a bigger undertaking, flagged as the
# natural next phase once this first comparison is in.

# %%
import matplotlib.pyplot as plt
import pandas as pd

from pecdr.capacity_weighting import capacity_weighted_cf, total_hourly_capacity
from pecdr.paths import ProjPaths

paths = ProjPaths()
paths.ensure_directories()

# %% [markdown]
# ## Load all three series, all as capacity factor

# %%
solar_capacity_month = pd.read_parquet(paths.solar_capacity_by_nuts2_month_file)

# Approach 1: PECD's own NUTS2 x technology CF x time-varying MaStR capacity,
# keyed on a flattened "technology_region" composite (e.g. "60_DE11") so the
# existing zone-capacity-weighting machinery (built for wind's single-key
# PEON zones) applies unchanged -- each technology-region pair is just
# another "zone" to weight and sum over.
pecd_solar_cf = pd.read_parquet(paths.pecd_solar_capacity_factors_file)
pecd_solar_cf.columns = [f"{tech}_{region}" for tech, region in pecd_solar_cf.columns]

tech_region_capacity = solar_capacity_month.copy()
tech_region_capacity["region_code"] = tech_region_capacity["pecd_technology"] + "_" + tech_region_capacity["nuts2_region"]
approach1 = capacity_weighted_cf(pecd_solar_cf, tech_region_capacity)

# Approach 2: this project's own simple physics baseline, technology-agnostic,
# weighted by total capacity per NUTS2 zone (summed across all 4 technologies).
own_solar_cf = pd.read_parquet(paths.own_solar_capacity_factors_file)
total_region_capacity = solar_capacity_month.groupby(["nuts2_region", "month"])["capacity_mw"].sum().reset_index()
total_region_capacity = total_region_capacity.rename(columns={"nuts2_region": "region_code"})
approach2 = capacity_weighted_cf(own_solar_cf, total_region_capacity)

# SMARD actual generation (MW) -> implied CF via time-varying total capacity
target_panel = pd.read_parquet(paths.target_panel_file)
total_capacity_hourly = total_hourly_capacity(total_region_capacity, target_panel.index)
smard_implied_cf = target_panel["pv"] / total_capacity_hourly

comparison = pd.DataFrame({
    "1_pecd_official_x_mastr": approach1,
    "2_own_physics_baseline": approach2,
    "3_smard_implied": smard_implied_cf,
}).dropna(how="all")
print(f"Hours with at least one series: {len(comparison):,}")
comparison.describe()

# %% [markdown]
# ## Full-period time series

# %%
fig, ax = plt.subplots(figsize=(14, 5))
for col, label in [
    ("1_pecd_official_x_mastr", "1. PECD official x MaStR"),
    ("2_own_physics_baseline", "2. This project's simple physics baseline"),
    ("3_smard_implied", "3. SMARD actual (implied CF)"),
]:
    comparison[col].plot(ax=ax, label=label, alpha=0.7, linewidth=0.3)
ax.set_ylabel("Germany-wide solar PV capacity factor")
ax.set_title("All three series, full available period")
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "25_solar_approaches_timeseries.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/25_solar_approaches_timeseries.png
# :name: fig-25-solar-approaches-timeseries
# All three solar capacity factor series, full available period.
# ```

# %% [markdown]
# ## Each approach vs. SMARD's actual (implied) capacity factor

# %%
stats_rows = []
fig, axes = plt.subplots(1, 2, figsize=(11, 5.5))
for ax, col, label in zip(axes, ["1_pecd_official_x_mastr", "2_own_physics_baseline"], ["1. PECD official x MaStR", "2. Simple physics baseline"]):
    sub = comparison[[col, "3_smard_implied"]].dropna()
    diff = sub[col] - sub["3_smard_implied"]
    corr = sub[col].corr(sub["3_smard_implied"])
    stats_rows.append({"approach": label, "n_hours": len(sub), "mae": float(diff.abs().mean()), "bias": float(diff.mean()), "corr": float(corr)})

    ax.scatter(sub["3_smard_implied"], sub[col], s=2, alpha=0.1)
    lims = [0, max(sub.max())]
    ax.plot(lims, lims, "k--", alpha=0.5, label="1:1")
    ax.set_xlabel("SMARD-implied CF")
    ax.set_ylabel(f"{label} CF")
    ax.set_title(f"{label}\nMAE={diff.abs().mean():.3f}, corr={corr:.3f}")
fig.tight_layout()
fig.savefig(paths.images_path / "25_solar_approaches_vs_smard.png", dpi=150, bbox_inches="tight")
plt.show()

stats = pd.DataFrame(stats_rows)
stats

# %% [markdown]
# ```{figure} ../../output/images/25_solar_approaches_vs_smard.png
# :name: fig-25-solar-approaches-vs-smard
# Each modeled approach vs. SMARD's actual (implied) PV capacity factor.
# ```

# %% [markdown]
# ## Does each approach's fit to SMARD hold up year to year?

# %%
yearly_rows = []
for col, label in [("1_pecd_official_x_mastr", "1. PECD official x MaStR"), ("2_own_physics_baseline", "2. Simple physics baseline")]:
    sub = comparison[[col, "3_smard_implied"]].dropna()
    diff = sub[col] - sub["3_smard_implied"]
    for year, group in diff.groupby(diff.index.year):
        approach_group = sub.loc[group.index, col]
        smard_group = sub.loc[group.index, "3_smard_implied"]
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
