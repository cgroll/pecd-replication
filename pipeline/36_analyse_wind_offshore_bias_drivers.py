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
# # What drives the offshore gap against SMARD?
#
# Offshore mirror of onshore's `22_analyse_bias_drivers`. `34_compare_wind_offshore_approaches`
# found both approach 1 (PECD official x MaStR) and approach 3 (this
# project's replication) systematically overshoot SMARD's actual
# wind-offshore generation. Since approach 1 isn't derived from this
# project's replication at all, a shared pattern between the two is
# evidence the gap is a genuine physical-vs-grid effect (curtailment,
# outages, storm shutdown), not a defect specific to this project's
# methodology.
#
# Same five panels as onshore, pooled across `pecdr.domain.FULL_YEAR_BACKTEST_YEARS`:
# bias vs. CF level, vs. month, vs. hour of day, vs. a renewable-oversupply
# proxy, and vs. year.

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
# ## Rebuild the same three series as `34_compare_wind_offshore_approaches`
#
# Approach 1 is restricted to the PEOF zones PECD actually models
# (`DE011_OFF`/`DE012_OFF`/`DE02_OFF`) -- see `34`'s note on the
# dead-weight-capacity dilution from PECD's 3 entirely-`NaN` zones.

# %%
mastr_peof_month = pd.read_parquet(paths.mastr_capacity_by_peof_month_file)

pecd_peof_cf = pd.read_parquet(paths.pecd_wind_offshore_capacity_factors_file)
pecd_modeled_zones = pecd_peof_cf.columns[pecd_peof_cf.notna().any()].tolist()
approach1 = capacity_weighted_cf(pecd_peof_cf[pecd_modeled_zones], mastr_peof_month)

approach3 = pd.read_parquet(paths.wind_offshore_full_year_cf_file)["national"]

target_panel = pd.read_parquet(paths.target_panel_file)
total_capacity_hourly = total_hourly_capacity(mastr_peof_month, target_panel.index)
smard_implied_cf = target_panel["wind_offshore"] / total_capacity_hourly

comparison = pd.DataFrame({
    "1_pecd_official_x_mastr": approach1,
    "3_pecd_replication": approach3,
    "4_smard_implied": smard_implied_cf,
}).loc[FULL_YEAR_BACKTEST_YEARS[0]:FULL_YEAR_BACKTEST_YEARS[-1]].dropna()

comparison["diff1"] = comparison["1_pecd_official_x_mastr"] - comparison["4_smard_implied"]
comparison["diff3"] = comparison["3_pecd_replication"] - comparison["4_smard_implied"]

# Renewable-oversupply proxy: (wind + solar) / load, system-wide (not just
# offshore) -- oversupply-driven curtailment depends on the whole system's
# supply/demand balance, not just the offshore zone's own output level.
renewables = target_panel.loc[comparison.index, ["pv", "wind_onshore", "wind_offshore"]].sum(axis=1)
comparison["renewable_share_of_load"] = renewables / target_panel.loc[comparison.index, "load"]

print(f"Hours compared: {len(comparison):,}")
print(f"Approach 1 vs SMARD -- bias: {comparison['diff1'].mean():.4f}, MAE: {comparison['diff1'].abs().mean():.4f}")
print(f"Approach 3 vs SMARD -- bias: {comparison['diff3'].mean():.4f}, MAE: {comparison['diff3'].abs().mean():.4f}")

# %% [markdown]
# ## 1. Does the bias grow with capacity-factor level?

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
fig.savefig(paths.images_path / "36_bias_vs_cf_level.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/36_bias_vs_cf_level.png
# :name: fig-36-bias-vs-cf-level
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
fig.savefig(paths.images_path / "36_bias_by_month.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/36_bias_by_month.png
# :name: fig-36-bias-by-month
# Mean bias by calendar month, both approaches, pooled across 2019-2025.
# ```

# %% [markdown]
# ## 3. Diurnal pattern: bias by hour of day

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
fig.savefig(paths.images_path / "36_bias_by_hour.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/36_bias_by_hour.png
# :name: fig-36-bias-by-hour
# Mean bias by hour of day, both approaches, pooled across 2019-2025.
# ```

# %% [markdown]
# ## 4. Bias vs. renewable oversupply proxy

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
fig.savefig(paths.images_path / "36_bias_vs_oversupply.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/36_bias_vs_oversupply.png
# :name: fig-36-bias-vs-oversupply
# Mean bias vs. renewable share of load (oversupply proxy), both approaches, pooled across 2019-2025.
# ```

# %% [markdown]
# ## 5. Does the bias hold up year to year?

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
fig.savefig(paths.images_path / "36_bias_by_year.png", dpi=150, bbox_inches="tight")
plt.show()

yearly

# %% [markdown]
# ```{figure} ../../output/images/36_bias_by_year.png
# :name: fig-36-bias-by-year
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
# - **CF level: hump-shaped, not monotonic like onshore's.** Bias climbs
#   from ~0 up to a peak around CF~0.5 (+0.13 to +0.22), then *falls back*
#   toward zero (even slightly negative for approach 1) at the highest CF
#   bins (0.8-0.9) -- unlike onshore, where bias grows roughly monotonically
#   all the way to the top. Two plausible, non-exclusive drivers: PECD's own
#   product (approach 1) *does* apply a per-turbine storm-shutdown model in
#   its own methodology (unlike this project's replication, which dropped
#   it -- see `31`'s docstring), which would pull approach 1 down at extreme
#   wind specifically; and this project's own capacity estimate carries real
#   uncertainty in exactly the direction that would produce this shape (see
#   `35` -- a capacity *underestimate* at a given hour inflates
#   `SMARD_MW / our_capacity` right into the highest bins). Both approaches
#   share the reversal, though, which favors something structural over an
#   artifact specific to one methodology -- not fully resolved here.
# - **Month: consistent with the curtailment/oversupply story**, same
#   direction as onshore -- bias is largest in winter (Jan/Feb, Oct-Dec,
#   +0.10 to +0.14) and smallest in summer (Jun-Aug), though unlike onshore
#   it never approaches zero even in summer (+0.055 at the lowest), tracking
#   offshore's consistently higher year-round wind resource.
# - **Hour of day: the opposite of the naive expectation, and different
#   from onshore.** Bias peaks at *midday* (9-13 UTC, when demand and prices
#   are typically highest) and is lowest overnight (00-05 UTC) -- the
#   reverse of "curtailment happens overnight when demand is low." The same
#   ERA5 10:00 UTC artifact already identified for onshore
#   (`pecdr/domain.py`) shows up again here, as a small dip in approach 3
#   only (approach 3 has no correction for it; approach 1, built from PECD's
#   own corrected product, doesn't show it) -- consistent cross-validation
#   of that already-identified, fixable gap, not new evidence either way for
#   curtailment. The midday peak itself is more consistent with solar PV
#   compounding total system oversupply at the same hours offshore wind is
#   already contributing a lot, than with offshore wind curtailment being
#   driven by its own local conditions alone.
# - **Oversupply proxy: the cleanest, most monotonic result of the five,
#   and a stronger signal than onshore's own version of this check.** Bias
#   climbs steadily with `(PV + wind onshore + wind offshore) / load`, all
#   the way to the highest bin (+0.23 to +0.27) -- no reversal at the top,
#   unlike the CF-level panel. Onshore's equivalent panel was flagged as
#   "largely a restatement" of CF level, since the two are highly collinear
#   there; here they behave genuinely differently (CF-level reverses at the
#   top, this doesn't), which is more consistent with a real, at least
#   partially independent, system-wide oversupply effect than with
#   offshore's own wind level alone.
# - **Year: bias roughly doubles from a 2019-2021 baseline (+0.05 to +0.08)
#   to a 2023-2024 peak (+0.10 to +0.14), then eases in 2025 (+0.09 to
#   +0.12)** -- independently corroborating two other findings already in
#   this project: `34`'s yearly bias table (same shape) and `35`'s fitted
#   national capacity trajectory (flat 2020-2024, only converging with
#   MaStR's nameplate figure in 2025). Matches the real-world timeline of
#   Germany's offshore grid-connection build-out (BorWin5/DolWin6-era
#   platforms) catching up with capacity additions.
#
# Net: three independent diagnostics in this project now (this notebook's
# year and oversupply panels, and `35`'s capacity-fitting exercise) converge
# on the same time-varying, system-wide-oversupply-linked story, which is
# more convincing pooled than any single one of them alone. The CF-level
# reversal and the midday-peaked diurnal pattern are the two genuinely
# offshore-specific departures from onshore's equivalent findings -- both
# have plausible explanations (storm-shutdown/capacity-ceiling effects at
# extreme CF; solar-compounded midday oversupply) but neither is nailed
# down without real curtailment or price data, the natural next step this
# notebook doesn't attempt.
