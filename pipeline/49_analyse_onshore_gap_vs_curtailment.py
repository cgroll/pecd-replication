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
# # Onshore wind: does a level-corrected curtailment estimate explain the potential-observed gap?
#
# [Chapter 46](../notebooks/46_attribute_ambiguous_redispatch_entities.ipynb) reconstructed
# onshore-wind curtailment from named entities plus a seasonal-fingerprint NNLS attribution of
# the ambiguous ones -- but flagged that the result sits well below SMARD's own reported total.
# Once offshore wind (which matches at 100%) is excluded from that chapter's blended 67.5%
# "Erneuerbar" figure, the onshore-only shortfall is worse than it looked: the reconstruction
# captures only **45.1%** of SMARD's reported onshore total, and PV only 23.5%. Worse, that
# shortfall isn't even stable over time -- it was close to zero in 2022 (Redispatch 2.0 renewable
# reporting was brand new) and has drifted up unevenly since.
#
# Rather than accept the shortfall, this chapter asks a narrower, testable question:
# [chapter 48](../notebooks/48_analyse_offshore_gap_vs_curtailment.ipynb) showed that offshore
# wind's *already-trustworthy* curtailment numbers close a large part of the potential-observed
# gap. If onshore's reconstruction is forced to match SMARD's own monthly total exactly -- a pure
# level correction, no new information about *timing* -- does the resulting daily series close
# the gap anywhere near as well? A good result would say the remaining onshore problem really was
# just missing volume. A bad result would say the *timing* of what's currently captured is itself
# not representative of the true, larger curtailment volume -- and no level correction fixes that.

# %%
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import nnls

from pecdr.paths import ProjPaths
from pecdr.redispatch_measures import load_redispatch_measures

paths = ProjPaths()
paths.ensure_directories()

measures = load_redispatch_measures(paths.redispatch_measures_file)
reduction = measures.loc[measures["direction"] == "reduction"]
smard = pd.read_parquet(paths.redispatch_by_source_file)
smard_reduction = smard.loc[smard["direction"] == "reduction"]

inputs = pd.read_parquet(paths.residual_load_inputs_file)
target_panel = pd.read_parquet(paths.target_panel_file).reindex(inputs.index)

overlap_start = max(reduction["month"].min(), smard_reduction["month"].min())
overlap_end = min(reduction["month"].max(), smard_reduction["month"].max())
reduction_overlap = reduction.loc[reduction["month"].between(overlap_start, overlap_end)]
smard_overlap = smard_reduction.loc[smard_reduction["month"].between(overlap_start, overlap_end)]

# %% [markdown]
# ## Step 1: rebuild the onshore reconstruction, at event (not just monthly) resolution
#
# Same seasonal-fingerprint NNLS method as chapter 46 -- repeated here rather than imported,
# following this project's convention of self-contained chapters -- but with one addition needed
# for this chapter's purpose: the fitted wind/PV split for each ambiguous entity-month is broadcast
# back onto every individual *event* in that entity-month (not just the entity-month total), so
# real per-event start timestamps survive into the daily series built further down.

# %%
renewable_reduction = reduction_overlap.loc[reduction_overlap["primary_energy_type"] == "Erneuerbar"]
ambiguous = renewable_reduction.loc[renewable_reduction["tech"] == "ambiguous"]

wind_fingerprint = renewable_reduction.loc[renewable_reduction["tech"] == "offshore_wind"].groupby(renewable_reduction["month"].dt.month)["mwh"].sum()
pv_fingerprint = renewable_reduction.loc[renewable_reduction["tech"] == "pv"].groupby(renewable_reduction["month"].dt.month)["mwh"].sum()
wind_fingerprint = (wind_fingerprint / wind_fingerprint.sum()).reindex(range(1, 13), fill_value=0.0)
pv_fingerprint = (pv_fingerprint / pv_fingerprint.sum()).reindex(range(1, 13), fill_value=0.0)

entity_monthly = ambiguous.groupby(["entity", "month"])["mwh"].sum().reset_index()
entity_monthly["cal_month"] = entity_monthly["month"].dt.month

MIN_MONTHS_TO_FIT = 3
fitted_rows = []
for entity, grp in entity_monthly.groupby("entity"):
    y = grp["mwh"].to_numpy()
    design = np.column_stack([wind_fingerprint.loc[grp["cal_month"]].to_numpy(), pv_fingerprint.loc[grp["cal_month"]].to_numpy()])
    if len(y) < MIN_MONTHS_TO_FIT:
        fitted_rows.append(grp.assign(wind_fraction=np.nan))
        continue
    weights, _ = nnls(design, y)
    predicted_total = design[:, 0] * weights[0] + design[:, 1] * weights[1]
    wind_fraction = np.divide(design[:, 0] * weights[0], predicted_total, out=np.full_like(y, 0.5), where=predicted_total > 0)
    fitted_rows.append(grp.assign(wind_fraction=wind_fraction))

fitted = pd.concat(fitted_rows)
overall_wind_share = (fitted["wind_fraction"] * fitted["mwh"]).sum() / fitted.loc[fitted["wind_fraction"].notna(), "mwh"].sum()
fitted["wind_fraction"] = fitted["wind_fraction"].fillna(overall_wind_share)

ambiguous_events = ambiguous.merge(fitted[["entity", "month", "wind_fraction"]], on=["entity", "month"], how="left")
ambiguous_events = ambiguous_events.assign(wind_mwh=ambiguous_events["mwh"] * ambiguous_events["wind_fraction"])

named_onshore_events = renewable_reduction.loc[renewable_reduction["tech"] == "onshore_wind_named"].assign(wind_mwh=lambda d: d["mwh"])

onshore_events = pd.concat([
    ambiguous_events[["start", "month", "wind_mwh"]],
    named_onshore_events[["start", "month", "wind_mwh"]],
])

# %% [markdown]
# ## Step 2: recalibrate to SMARD's own monthly total
#
# A single constant scale factor for the whole period isn't a fair stand-in -- the true
# under-coverage ratio drifts sharply across years (see chapter 46's year-by-year table: ~6% in
# 2022 rising unevenly to ~64% by 2026 as Redispatch 2.0 reporting matured). Instead, each month
# gets its own factor: SMARD's reported onshore total for that month divided by this
# reconstruction's own (un-scaled) total for the same month -- forcing the monthly *level* to
# match SMARD exactly, by construction.

# %%
reconstructed_monthly_raw = onshore_events.groupby("month")["wind_mwh"].sum()
smard_onshore_monthly = smard_overlap.loc[smard_overlap["energy_source"] == "Wind_Onshore"].groupby("month")["gwh"].sum() * 1000
recalibration_factor = (smard_onshore_monthly / reconstructed_monthly_raw).reindex(reconstructed_monthly_raw.index)

fig, ax = plt.subplots(figsize=(12, 4))
ax.plot(recalibration_factor.index, recalibration_factor.values, marker="o", markersize=3, linewidth=1)
ax.axhline(1, color="k", linewidth=0.8, linestyle="--")
ax.set_ylabel("Recalibration factor (SMARD / raw reconstruction)")
ax.set_title("Onshore wind: monthly recalibration factor")
fig.tight_layout()
fig.savefig(paths.images_path / "49_onshore_recalibration_factor.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/49_onshore_recalibration_factor.png
# :name: fig-49-onshore-recalibration-factor
# Monthly recalibration factor needed to bring the raw NNLS reconstruction up to SMARD's reported
# onshore total. Early months (mid-to-late 2022) require factors as large as ~50-80x -- not a
# stable scale problem, but a sign that almost nothing was captured yet in those months at all.
# From late 2023 onward the factor settles into a much more plausible ~1.2-6x range.
# ```
#
# The pre-2023 spikes are a real caveat worth stating plainly: a month where the raw
# reconstruction is a few thousand MWh against a SMARD total of a few hundred thousand isn't
# "under-scaled", it's a month where the per-measure file barely recorded onshore curtailment as
# its own category yet. Multiplying a near-empty month by 80x doesn't recover real information --
# it amplifies whatever noise happened to be in those few recorded events. Checked directly:
# restricting the whole analysis below to 2023-10 onward (once the factor settles down) changes
# the resulting metrics only marginally, so the full overlap period is kept throughout for
# consistency with chapter 48 -- but the instability above is the reason this chapter's
# recalibrated series should be read as a diagnostic, not a trustworthy curtailment estimate in
# its own right.

# %%
onshore_events = onshore_events.assign(recalibration_factor=onshore_events["month"].map(recalibration_factor))
onshore_events = onshore_events.assign(wind_mwh_recalibrated=onshore_events["wind_mwh"] * onshore_events["recalibration_factor"])

# %% [markdown]
# ## Step 3: does the recalibrated series close the potential-observed gap?
#
# Same structure as chapter 48's offshore analysis: potential, observed, and observed plus
# curtailment added back in, at daily resolution -- computed once for the *raw* (uncalibrated)
# reconstruction and once for the *recalibrated* one, to isolate what the level correction alone
# buys.

# %%
implied_loss_daily = (inputs["P_wind_on_mw"] - target_panel["wind_onshore"]).clip(lower=0).resample("D").sum()

daily_range = pd.date_range(
    max(onshore_events["start"].min().normalize(), implied_loss_daily.index.min()),
    min(onshore_events["start"].max().normalize(), implied_loss_daily.index.max()),
    freq="D",
)
onshore_curtailment_daily = onshore_events.groupby(onshore_events["start"].dt.normalize())["wind_mwh_recalibrated"].sum().reindex(daily_range, fill_value=0.0)
onshore_curtailment_daily_raw = onshore_events.groupby(onshore_events["start"].dt.normalize())["wind_mwh"].sum().reindex(daily_range, fill_value=0.0)
implied_loss_daily = implied_loss_daily.reindex(daily_range)

potential_daily = inputs["P_wind_on_mw"].resample("D").sum().reindex(daily_range)
observed_daily = target_panel["wind_onshore"].resample("D").sum().reindex(daily_range)
reconstructed_daily_raw = observed_daily + onshore_curtailment_daily_raw
reconstructed_daily = observed_daily + onshore_curtailment_daily

fig, ax = plt.subplots(figsize=(13, 4.5))
ax.plot(daily_range, potential_daily, label="Potential (this project's replication)", linewidth=0.6)
ax.plot(daily_range, observed_daily, label="Observed (SMARD)", linewidth=0.6)
ax.plot(daily_range, reconstructed_daily, label="Observed + recalibrated curtailment", linewidth=0.6)
ax.set_ylabel("MWh / day")
ax.set_title("Onshore wind: potential vs. observed vs. observed + recalibrated curtailment, daily")
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "49_onshore_potential_observed_curtailment_daily.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/49_onshore_potential_observed_curtailment_daily.png
# :name: fig-49-onshore-potential-observed-curtailment-daily
# Onshore wind, daily: potential, observed, and observed plus recalibrated curtailment added back
# in, over the full period covered by the per-measure redispatch data.
# ```

# %% [markdown]
# ### Zooming into the same Nov-Dec 2023 window used throughout chapters 39/48

# %%
window_2023 = slice("2023-11-01", "2023-12-31")
fig, ax = plt.subplots(figsize=(13, 4.5))
ax.plot(potential_daily.loc[window_2023].index, potential_daily.loc[window_2023], label="Potential (this project's replication)", linewidth=1.3)
ax.plot(observed_daily.loc[window_2023].index, observed_daily.loc[window_2023], label="Observed (SMARD)", linewidth=1.3)
ax.plot(reconstructed_daily.loc[window_2023].index, reconstructed_daily.loc[window_2023], label="Observed + recalibrated curtailment", linewidth=1.3, linestyle=":")
ax.set_ylabel("MWh / day")
ax.set_title("Onshore wind: potential vs. observed vs. observed + recalibrated curtailment, Nov-Dec 2023")
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "49_onshore_potential_observed_curtailment_daily_window.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/49_onshore_potential_observed_curtailment_daily_window.png
# :name: fig-49-onshore-potential-observed-curtailment-daily-window
# Same Nov-Dec 2023 window used in chapters 39 and 48, for direct visual comparison against
# offshore's equivalent chart.
# ```

# %% [markdown]
# ### Scatter and metrics, mirroring chapter 48's exactly

# %%
def scatter_metrics(potential: pd.Series, actual: pd.Series) -> dict:
    corr = np.corrcoef(potential, actual)[0, 1]
    slope, intercept = np.polyfit(potential, actual, 1)
    residual = actual - potential
    ss_res_identity = (residual ** 2).sum()
    ss_tot = ((actual - actual.mean()) ** 2).sum()
    return {
        "correlation_r": round(corr, 4),
        "regression_slope": round(slope, 4),
        "r2_vs_y_equals_x": round(1 - ss_res_identity / ss_tot, 4),
        "mae_mwh_per_day": round(residual.abs().mean(), 0),
        "rmse_mwh_per_day": round(np.sqrt((residual ** 2).mean()), 0),
        "sum_ratio_actual_over_potential": round(actual.sum() / potential.sum(), 4),
    }

metrics_comparison = pd.DataFrame({
    "observed_only": scatter_metrics(potential_daily, observed_daily),
    "observed_plus_raw_curtailment": scatter_metrics(potential_daily, reconstructed_daily_raw),
    "observed_plus_recalibrated_curtailment": scatter_metrics(potential_daily, reconstructed_daily),
})
metrics_comparison

# %%
fig, ax = plt.subplots(figsize=(6.5, 6.5))
ax.scatter(potential_daily, reconstructed_daily, s=6, alpha=0.35, linewidth=0)
axis_max = max(potential_daily.max(), reconstructed_daily.max())
ax.plot([0, axis_max], [0, axis_max], color="black", linewidth=1, linestyle="--", label="y = x")
ax.set_xlabel("Potential, MWh/day (this project's replication)")
ax.set_ylabel("Observed + recalibrated curtailment, MWh/day")
ax.set_title("Onshore wind, daily: observed + recalibrated curtailment vs. potential")
ax.set_xlim(0, axis_max)
ax.set_ylim(0, axis_max)
ax.set_aspect("equal")
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "49_onshore_scatter_potential_vs_reconstructed_daily.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/49_onshore_scatter_potential_vs_reconstructed_daily.png
# :name: fig-49-onshore-scatter-potential-vs-reconstructed-daily
# Onshore wind, daily: observed plus recalibrated curtailment vs. potential.
# ```

# %% [markdown]
# ## Takeaways
#
# - **Recalibration helps, but nowhere near as much as offshore's real curtailment did.** Against
#   `y = x`, onshore's R² rises from ~0.65 (observed alone) to ~0.70 (raw NNLS curtailment added)
#   to ~0.75 (recalibrated) -- offshore, in chapter 48, rose from 0.21 to 0.85 to 0.90 over the
#   same kind of progression. `sum_ratio` climbs from ~0.77 to ~0.80 here, against offshore's 0.74
#   to 0.87 (to 0.90 with negative prices added).
# - **Onshore's starting point was never as extreme as offshore's.** The observed-only baseline
#   R² here (~0.65) is already far higher than offshore's own observed-only baseline (0.21) --
#   consistent with the known fact that offshore is curtailed roughly 8-9x more heavily per MW
#   installed than onshore (chapter 44). There's simply less raw gap for curtailment to close in
#   the first place.
# - **Forcing the level to match SMARD exactly still leaves a real gap.** This is the key result:
#   the recalibration in step 2 makes the monthly *total* match SMARD by construction, yet the
#   daily reconciliation still falls well short of offshore's. That means the shortfall visible in
#   chapter 46 was not simply "right events, wrong scale" -- something about the *timing or
#   composition* of what this file currently captures for onshore is a worse proxy for true
#   curtailment than offshore's clean, individually-named data ever was. Plausible contributors,
#   not disentangled here: the DSO-level volume missing entirely from this TSO-issued file may
#   have different timing than what is captured; the NNLS wind/PV split itself is uncertain per
#   entity; and this project's own onshore potential replication (chapters 04-23) may carry bias
#   of its own, exactly as suspected for offshore in chapter 48.
# - **This was a deliberately blunt diagnostic, not a new curtailment estimate.** The recalibrated
#   series should not be used downstream as if it were real data -- the point was only to test
#   whether a pure level fix was sufficient. It wasn't, which is itself the useful finding: the
#   onshore/PV attribution problem needs a better underlying entity-level identification (e.g. the
#   geocoding cross-check proposed in chapter 46), not just a bigger multiplier.
