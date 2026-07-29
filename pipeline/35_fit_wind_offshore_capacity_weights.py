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
# # Fitting optimal PEOF-zone capacity weights: is the bias just wrong fleet numbers?
#
# `34_compare_wind_offshore_approaches` found "PECD official x MaStR" biased
# +0.060 CF against SMARD, using **our own** `mastr_capacity_by_peof_month`
# panel as the capacity weights on both sides of that comparison. That
# panel is not one of PECD's outputs -- it's built here from MaStR's
# `commissioning_date`/`final_shutdown_date`, so if it's wrong (e.g.
# commissioning dates front-run real grid-connection ramp-up, or units are
# assigned to the wrong PEOF zone), that alone could manufacture the bias
# without any real curtailment involved.
#
# This asks a sharper question: **holding PECD's own zone capacity-factor
# shapes fixed, what's the best possible per-zone capacity vector, and how
# much of the SMARD gap does it close?** If the optimal vector still can't
# explain SMARD well, wrong fleet numbers are ruled out as the (sole)
# explanation.
#
# ## Method
#
# Solve `SMARD_actual_MW(t) ~ sum_z w_z(t) * PECD_CF_z(t)` for the
# per-zone capacity weights `w_z(t)`, via ordinary least squares with two
# physical constraints: `w_z(t) >= 0`, and `w_z` monotonically
# non-decreasing in `t` (no German offshore capacity was decommissioned in
# 2019-2025, only added). The monotonicity constraint turns into a plain
# non-negativity constraint via a reparametrization: instead of estimating
# `w_z(t)` directly, estimate non-negative **monthly increments**
# `d_z[m] >= 0` (capacity newly delivering in zone `z`, month `m` -- the
# first month's increment absorbs whatever was already installed before the
# fit window starts), so `w_z(t) = sum_{k <= month(t)} d_z[k]` is
# automatically monotonic. Substituting back in, the model is linear again
# in `d`, solved with plain NNLS (`scipy.optimize.nnls`) on a transformed
# design matrix: column `(z, k)` at hour `t` is `PECD_CF_z(t)` if
# `month(t) >= k`, else 0.
#
# ## Two things this can't cleanly separate
#
# - **Only 3 of PECD's 6 PEOF zones have any data at all.**
#   `DE013_OFF`/`DE014_OFF`/`DE015_OFF` are 100% `NaN` in PECD's own
#   product across the entire 2015-2025 file -- PECD apparently never
#   modeled them. `DE013_OFF` still carries real MaStR capacity (up to
#   ~300 MW) -- a separate, genuine data-quality issue: the *previous*
#   notebook's "PECD official x MaStR" number silently dilutes its
#   capacity-weighted denominator with this dead-weight capacity (MaStR
#   capacity that contributes zero numerator, since its CF is `NaN` and
#   pandas' default `skipna` sum just drops it). Only the 3 zones PECD
#   actually models (`DE011_OFF`, `DE012_OFF`, `DE02_OFF`) can be fit or
#   fairly compared here.
# - **Those 3 zones sit close together and see highly correlated wind**, so
#   the design matrix is poorly conditioned for separating *individual*
#   zone weights -- capacity can trade between `DE011_OFF` and `DE012_OFF`
#   in the fit without much cost in fit quality. The **national total**
#   (summed across zones) is the trustworthy readout; per-zone trajectories
#   below are shown but shouldn't be over-interpreted individually.

# %%
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import nnls

from pecdr.capacity_weighting import hourly_capacity_by_zone
from pecdr.domain import FULL_YEAR_BACKTEST_YEARS
from pecdr.paths import ProjPaths

paths = ProjPaths()
paths.ensure_directories()

PERIOD_LABEL = f"{FULL_YEAR_BACKTEST_YEARS[0]}-{FULL_YEAR_BACKTEST_YEARS[-1]}"

# %% [markdown]
# ## Load data and restrict to PECD's actually-modeled zones

# %%
pecd_peof_cf = pd.read_parquet(paths.pecd_wind_offshore_capacity_factors_file)
target_panel = pd.read_parquet(paths.target_panel_file)
mastr_peof_month = pd.read_parquet(paths.mastr_capacity_by_peof_month_file)

all_zones = pecd_peof_cf.columns.tolist()
valid_zones = pecd_peof_cf.columns[pecd_peof_cf.notna().any()].tolist()
print(f"PEOF zones in PECD's product: {all_zones}")
print(f"Zones PECD actually has data for: {valid_zones}")
print(f"Zones dropped as 100% NaN in PECD's own product: {sorted(set(all_zones) - set(valid_zones))}")

cf = pecd_peof_cf.loc[FULL_YEAR_BACKTEST_YEARS[0]:FULL_YEAR_BACKTEST_YEARS[-1], valid_zones]
smard_mw = target_panel["wind_offshore"].reindex(cf.index)
keep = smard_mw.notna()
cf, smard_mw = cf[keep], smard_mw[keep]
print(f"Hours in fit: {len(cf):,}")

# %% [markdown]
# ## Build the monotonic-increment design matrix and solve NNLS

# %%
zones = list(cf.columns)
row_period = cf.index.to_period("M")
months = row_period.unique().sort_values()
month_idx = months.get_indexer(row_period)
n_zones, n_months = len(zones), len(months)

# mask[t, k] = True if hour t's month is on or after month k -- shared
# across zones, since it only depends on which month each hour falls in.
month_mask = np.arange(n_months)[None, :] <= month_idx[:, None]
design_matrix = np.hstack([cf[z].to_numpy()[:, None] * month_mask for z in zones])

fitted_increments, residual_norm = nnls(design_matrix, smard_mw.to_numpy(), maxiter=10_000)
fitted_capacity_by_month = fitted_increments.reshape(n_zones, n_months).cumsum(axis=1)
fitted_capacity = pd.DataFrame(fitted_capacity_by_month.T, index=months, columns=zones)
print(f"Non-zero monthly increments: {(fitted_increments > 1.0).sum()} / {len(fitted_increments)}")
fitted_capacity.iloc[[0, -1]]

# %% [markdown]
# ## Fitted capacity vs. MaStR-derived capacity, over time

# %%
mastr_wide = (
    mastr_peof_month.assign(year_month=lambda d: d["month"].dt.to_period("M"))
    .groupby(["year_month", "region_code"])["capacity_mw"]
    .sum()
    .unstack("region_code")
    .reindex(months)
    .reindex(columns=zones)
    .fillna(0)
)

fig, axes = plt.subplots(2, 2, figsize=(13, 8), sharex=True)
per_zone_axes, total_ax = axes.flat[: len(zones)], axes.flat[len(zones)]
for ax, zone in zip(per_zone_axes, zones):
    fitted_capacity[zone].plot(ax=ax, label="Fitted (optimal)", linewidth=1.5)
    mastr_wide[zone].plot(ax=ax, label="MaStR-derived", linewidth=1.5, linestyle="--")
    ax.set_title(zone)
    ax.set_ylabel("Capacity (MW)")
    ax.legend()
for ax in axes.flat[len(zones) + 1 :]:
    ax.set_visible(False)

fitted_capacity.sum(axis=1).plot(ax=total_ax, label="Fitted total", linewidth=1.5, color="black")
mastr_wide.sum(axis=1).plot(ax=total_ax, label="MaStR total (3 modeled zones)", linewidth=1.5, linestyle="--", color="black")
total_ax.set_title("National total (3 PECD-modeled zones)")
total_ax.set_ylabel("Capacity (MW)")
total_ax.legend()
fig.suptitle(f"Fitted vs. MaStR-derived offshore capacity, {PERIOD_LABEL}")
fig.tight_layout()
fig.savefig(paths.images_path / "35_fitted_capacity_trajectories.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/35_fitted_capacity_trajectories.png
# :name: fig-35-fitted-capacity-trajectories
# Fitted (optimal, monotonic) vs. MaStR-derived offshore capacity by PEOF zone and nationally, 2019-2025.
# ```

# %% [markdown]
# ## Does the optimal capacity vector actually fit SMARD better?
#
# Compares the fitted-optimal reconstruction against the MaStR-weighted
# reconstruction, **both restricted to the same 3 PECD-modeled zones** (so
# this isolates the effect of *reweighting* capacity, not the separate
# dead-weight-capacity issue from `DE013_OFF`) -- both in MW directly
# against SMARD's actual generation.

# %%
predicted_fitted_mw = design_matrix @ fitted_increments

mastr_hourly = hourly_capacity_by_zone(mastr_peof_month, cf.index, zone_col="region_code").reindex(columns=zones).fillna(0)
predicted_mastr_mw = (cf.to_numpy() * mastr_hourly.to_numpy()).sum(axis=1)

smard_values = smard_mw.to_numpy()
stats = pd.DataFrame([
    {
        "capacity_vector": "Fitted (optimal, monotonic)",
        "mae_mw": float(np.mean(np.abs(predicted_fitted_mw - smard_values))),
        "bias_mw": float(np.mean(predicted_fitted_mw - smard_values)),
        "corr": float(np.corrcoef(predicted_fitted_mw, smard_values)[0, 1]),
    },
    {
        "capacity_vector": "MaStR-derived (3 PECD-modeled zones)",
        "mae_mw": float(np.mean(np.abs(predicted_mastr_mw - smard_values))),
        "bias_mw": float(np.mean(predicted_mastr_mw - smard_values)),
        "corr": float(np.corrcoef(predicted_mastr_mw, smard_values)[0, 1]),
    },
])
stats

# %% [markdown]
# ## Time series: both reconstructions vs. SMARD actual

# %%
fig, ax = plt.subplots(figsize=(14, 4))
pd.Series(smard_values, index=cf.index).plot(ax=ax, label="SMARD actual", alpha=0.8, linewidth=0.4)
pd.Series(predicted_fitted_mw, index=cf.index).plot(ax=ax, label="Fitted-optimal reconstruction", alpha=0.8, linewidth=0.4)
pd.Series(predicted_mastr_mw, index=cf.index).plot(ax=ax, label="MaStR-weighted reconstruction", alpha=0.8, linewidth=0.4)
ax.set_ylabel("Germany-wide offshore wind generation (MW)")
ax.set_title(f"Fitted vs. MaStR-weighted vs. SMARD actual, {PERIOD_LABEL}")
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "35_fit_quality_vs_smard.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/35_fit_quality_vs_smard.png
# :name: fig-35-fit-quality-vs-smard
# Fitted-optimal and MaStR-weighted reconstructions vs. SMARD's actual offshore generation, 2019-2025.
# ```
#
# ## Reading the result
#
# The optimal capacity vector drives bias to roughly zero (vs. a clear
# positive bias from the MaStR-derived weights) -- a real chunk of the
# previously-observed bias **is** attributable to our own capacity
# accounting, not to PECD's modeling or to curtailment. But correlation
# barely moves between the two -- reweighting capacity fixes the *level*,
# not the *shape*. Since the fitted vector is, by construction, the best
# any monotonic per-zone capacity story can possibly do, the remaining
# correlation gap can't be closed by better fleet data -- it needs
# something dynamic that a static (or monotonically growing) capacity
# vector structurally can't represent: curtailment, outages, or another
# time-varying effect neither this fit nor PECD's own product attempts to
# model.
