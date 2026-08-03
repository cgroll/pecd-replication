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
# # Comparing the two data sources
#
# [Chapter 1](../notebooks/44_analyse_congestion_curtailment.ipynb) covered
# SMARD's monthly, TSO+DSO, ex-post counterfactual series;
# [chapter 2](../notebooks/45_explore_redispatch_measures.ipynb) covered
# netztransparenz's per-measure, TSO-issued, mostly technology-anonymous
# export. This notebook reconciles the two: how much do their totals
# actually agree, per technology and in aggregate, why they differ, and how
# far a statistical attribution can go in resolving the per-measure file's
# missing technology labels.

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

overlap_start = max(reduction["month"].min(), smard_reduction["month"].min())
overlap_end = min(reduction["month"].max(), smard_reduction["month"].max())
print(f"Overlapping period used throughout: {overlap_start.date()} .. {overlap_end.date()}")

reduction_overlap = reduction.loc[reduction["month"].between(overlap_start, overlap_end)]
smard_overlap = smard_reduction.loc[smard_reduction["month"].between(overlap_start, overlap_end)]

# %% [markdown]
# ## Do the aggregate totals match?
#
# Not evenly -- the gap is concentrated in one category, not spread across
# all of them.

# %%
this_file_by_type = reduction_overlap.groupby("primary_energy_type")["mwh"].sum()
smard_by_col = smard_overlap.groupby("energy_source")["gwh"].sum() * 1000  # GWh -> MWh

RENEWABLE_COLS = ["Wind_Onshore", "Wind_Offshore", "Photovoltaik", "Sonstige_Erneuerbare"]
CONVENTIONAL_COLS = ["Braunkohle", "Steinkohle", "Erdgas", "Kernenergie", "Biomasse", "Pumpspeicher", "Wasserkraft", "Sonstige_Konventionelle"]
UNKNOWN_COLS = ["Unbekannt"]

category_comparison = pd.DataFrame([
    {
        "category": this_key,
        "this_file_mwh": this_file_by_type.get(this_key, 0.0),
        "smard_mwh": smard_by_col.reindex(smard_keys).sum(),
    }
    for this_key, smard_keys in [("Erneuerbar", RENEWABLE_COLS), ("Konventionell", CONVENTIONAL_COLS), ("Sonstiges", UNKNOWN_COLS)]
])
category_comparison["ratio_pct"] = (category_comparison["this_file_mwh"] / category_comparison["smard_mwh"] * 100).round(1)
category_comparison

# %% [markdown]
# Conventional plants match reasonably well (~93%); renewables have a real
# but moderate gap (~68%); the `Sonstiges`/`Unbekannt` catch-all -- mostly
# countertrading, per the previous chapter -- is the dominant driver of the
# overall shortfall, matching only ~13%. netztransparenz's per-measure
# "Redispatch" export barely captures countertrading at all (its own
# `Strombedingter Countertrade DE-DK1/DE-DK2/DE-NO2` reason codes are a
# tiny fraction of total volume), while SMARD folds all of it into the
# by-energy-source view (chapter 1).

# %% [markdown]
# ## Why the totals differ: three factors, not one
#
# 1. **Grid-level scope.** SMARD's renewable figure is TSO+DSO combined
#    (chapter 1); this file is TSO-issued only.
# 2. **Measure-type scope.** SMARD's figure folds in countertrading and
#    grid-reserve volume; this file is almost entirely `Strombedingter`/
#    `Spannungsbedingter Redispatch` (chapter 2).
# 3. **Settlement methodology.** SMARD's figure is a settled, ex-post
#    counterfactual ("Ausfallarbeit") that's systematically larger than a
#    simple instructed-power reading whenever conditions improved during a
#    measure (chapter 1's methodology section) -- this file's own
#    `GESAMTE_ARBEIT_MWH` is plausibly the latter, simpler quantity.
#
# None of these were individually sufficient to fully explain the gap when
# checked in isolation earlier in this investigation -- it's a combination.

# %% [markdown]
# ## Does the technology-level picture hold up?

# %%
renewable_reduction = reduction_overlap.loc[reduction_overlap["primary_energy_type"] == "Erneuerbar"]
name_attribution = renewable_reduction.groupby("tech")["mwh"].sum()

tech_comparison = pd.DataFrame({
    "this_file_named_mwh": [
        name_attribution.get("offshore_wind", 0.0),
        name_attribution.get("onshore_wind_named", 0.0),
        name_attribution.get("pv", 0.0),
    ],
    "smard_reported_mwh": [
        smard_by_col.get("Wind_Offshore", 0.0),
        smard_by_col.get("Wind_Onshore", 0.0),
        smard_by_col.get("Photovoltaik", 0.0),
    ],
}, index=["offshore_wind", "onshore_wind", "pv"])
tech_comparison["named_share_of_smard_pct"] = (tech_comparison["this_file_named_mwh"] / tech_comparison["smard_reported_mwh"] * 100).round(1)
tech_comparison

# %% [markdown]
# Offshore wind is named individually for essentially every measure and
# matches SMARD's own figure almost exactly (100%) -- trustworthy at this
# file's native per-measure time resolution. Onshore wind and PV are only
# individually named a small fraction of the time; the rest sits under
# anonymous substation/cluster codes ("ambiguous").

# %%
offshore_by_month = renewable_reduction.loc[renewable_reduction["tech"] == "offshore_wind"].groupby("month")["mwh"].sum()
smard_offshore_by_month = smard_overlap.loc[smard_overlap["energy_source"] == "Wind_Offshore"].groupby("month")["gwh"].sum() * 1000

fig, ax = plt.subplots(figsize=(12, 4))
ax.plot(offshore_by_month.index, offshore_by_month.values, label="This file (named offshore entities)", linewidth=1.3)
ax.plot(smard_offshore_by_month.index, smard_offshore_by_month.values, label="SMARD reported", linewidth=1.3, linestyle="--")
ax.set_ylabel("MWh")
ax.set_title("Offshore wind reduction volume: this file vs. SMARD")
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "46_offshore_wind_by_source.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/46_offshore_wind_by_source.png
# :name: fig-46-offshore-wind-by-source
# Monthly offshore-wind reduction volume: this file's individually-named offshore entities vs. SMARD's own reported total. The two lines sit almost on top of each other -- the clearest visual confirmation of the 100% match above, and unlike the onshore/PV reconstruction further down, this one needs no statistical attribution at all.
# ```

# %% [markdown]
# ## Geo-information: both sources are limited, in different ways
#
# **SMARD's monthly series has none at all** -- purely a national total.
# **This per-measure file has a coarse proxy only**: the instructing TSO
# (`ANWEISENDER_UENB`, 4 zones), with the caveat that TenneT's zone spans
# both the North Sea coast and Bavaria. Neither source has real
# coordinates or a finer administrative region field.

# %% [markdown]
# ## Attributing the ambiguous entities
#
# Rather than allocating individual *measures* (tens of thousands of them,
# no natural prior to optimize against), the right unit is the **entity**
# -- each of the ~200 substation/cluster names is a physical grid
# connection point whose technology mix is very unlikely to change month
# to month.

# %% [markdown]
# ### Attempt 1: MaStR -- a clean dead end
#
# MaStR models grid connection points as a first-class concept
# (`netzanschlusspunkte`/`GridConnections`, with human-readable name
# fields, linked to the actual generation units) -- checked by reading
# `open_mastr`'s ORM directly. In practice: getting this data required a
# fresh ~25-minute bulk download (5.77 million grid-connection rows, 6.68
# million location rows), and it turned out to be a dead end, not just
# inconclusive. Both name fields are populated at individual
# household/plant level (`"Egenbüttelweg 45, i.B. 05.07.2017, 7,99 kWp"`,
# or opaque internal IDs), not TSO-level substation/cluster names.
# Searching all 5.77 million rows for the actual place-name fragments
# behind the biggest ambiguous entities (`Dörpen`, `Diele`, `Süderdonn`,
# `Heide West`, `Handewitt`) returned zero matches; a `Büttel` search
# returned 21 rows, none of them the actual `UW Büttel` entity (all
# unrelated coincidences like `Egenbüttelweg`). MaStR conceptually
# supports this kind of join, but the TSOs' own redispatch-cluster naming
# is evidently their own internal convention with no counterpart in
# MaStR's registry.

# %% [markdown]
# ### Attempt 2: seasonal-fingerprint attribution
#
# Wind and PV curtailment have close-to-opposite seasonal shapes. This
# builds a normalized reference shape for each from the cleanly-identified
# subsets, then fits each ambiguous entity's own monthly series as a
# non-negative combination of the two via `scipy.optimize.nnls` -- a
# small, well-determined regression *per entity* (2 unknowns against
# however many months of its own history exist), not one large fit across
# all ~200 entities simultaneously (which would be underdetermined, given
# only ~50 months of aggregate constraints to pin down ~400 unknowns).

# %%
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
        fitted_rows.append(grp.assign(wind_mwh=np.nan, pv_mwh=np.nan))
        continue
    weights, _ = nnls(design, y)
    predicted_total = design[:, 0] * weights[0] + design[:, 1] * weights[1]
    wind_fraction = np.divide(design[:, 0] * weights[0], predicted_total, out=np.full_like(y, 0.5), where=predicted_total > 0)
    fitted_rows.append(grp.assign(wind_mwh=wind_fraction * y, pv_mwh=(1 - wind_fraction) * y))

fitted = pd.concat(fitted_rows)
resolved = fitted.dropna(subset=["wind_mwh"])
overall_wind_share = resolved["wind_mwh"].sum() / (resolved["wind_mwh"].sum() + resolved["pv_mwh"].sum())
fitted["wind_mwh"] = fitted["wind_mwh"].fillna(fitted["mwh"] * overall_wind_share)
fitted["pv_mwh"] = fitted["pv_mwh"].fillna(fitted["mwh"] * (1 - overall_wind_share))
print(f"Volume-weighted wind share among directly-fit entities: {overall_wind_share:.1%}")

entity_summary = (
    fitted.groupby("entity")
    .agg(n_months=("mwh", "size"), total_mwh=("mwh", "sum"), wind_mwh=("wind_mwh", "sum"), pv_mwh=("pv_mwh", "sum"))
    .assign(wind_share=lambda d: d["wind_mwh"] / d["total_mwh"])
    .sort_values("total_mwh", ascending=False)
)
entity_summary.head(15)

# %% [markdown]
# Physically sensible without ever being told any geography: Schleswig-
# Holstein entities (`SHN Cluster Heide West`, `Husum Nord`, `Klixbüll`)
# and other northern substations (`50H UW Bertikow`, `AVA Cluster
# Voslapp`) come out essentially 100% wind; Bavarian entities
# (`BAG NWAK-Cluster 15 Pleinting`, `17 Altheim`, `EE Bayern`) come out
# strongly PV-dominated -- matching real German energy geography.

# %% [markdown]
# ## Reconstructed vs. SMARD, and the volume caveat that still applies

# %%
smard_wide = smard_overlap.pivot(index="month", columns="energy_source", values="gwh") * 1000
monthly_attributed = fitted.groupby("month")[["wind_mwh", "pv_mwh"]].sum()
named = renewable_reduction.loc[renewable_reduction["tech"].isin(["onshore_wind_named", "pv"])]
named_monthly = named.groupby(["month", "tech"])["mwh"].sum().unstack("tech").reindex(monthly_attributed.index).fillna(0.0)

reconstructed = pd.DataFrame({
    "onshore_wind_mwh": monthly_attributed["wind_mwh"] + named_monthly.get("onshore_wind_named", 0.0),
    "pv_mwh": monthly_attributed["pv_mwh"] + named_monthly.get("pv", 0.0),
})

fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
for ax, tech, smard_col in zip(axes, ["onshore_wind_mwh", "pv_mwh"], ["Wind_Onshore", "Photovoltaik"]):
    ax.plot(reconstructed.index, reconstructed[tech], label="Reconstructed (this file, attributed)", linewidth=1.3)
    ax.plot(reconstructed.index, smard_wide[smard_col].reindex(reconstructed.index), label="SMARD reported", linewidth=1.3, linestyle="--")
    ax.set_ylabel("MWh")
    ax.set_title(tech.replace("_", " "))
    ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "46_reconstructed_vs_smard.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/46_reconstructed_vs_smard.png
# :name: fig-46-reconstructed-vs-smard
# Reconstructed monthly onshore-wind and PV reduction volume (named + attributed ambiguous entities) vs. SMARD's own reported monthly totals. The shape tracks reasonably; the consistent shortfall is the same aggregate volume gap documented above, not a shape mismatch.
# ```
#
# The reconstructed series tracks SMARD's *shape* reasonably (peaks and
# troughs align) but sits consistently below it -- the same ~32% aggregate
# renewables shortfall from the top of this notebook, not a new error
# introduced by the attribution. **This makes the per-measure file (and
# this attribution) a better source for relative technology split and
# timing than for absolute monthly levels.**

# %% [markdown]
# ## What's still open
#
# - Understanding the residual gap even after accounting for grid-level,
#   measure-type, and methodology differences.
# - A geographic cross-check: geocode each ambiguous entity's place name
#   and look up nearby installed wind/PV capacity directly from the MaStR
#   technology tables (`wind.parquet`/`solar.parquet`, which do have
#   `longitude`/`latitude`) as an independent check on the
#   seasonal-fingerprint attribution above -- not yet done.
# - See the next section: real curtailment turns out not to fully explain
#   the raw potential-vs-observed gap either, which points at this
#   project's own "potential" replication rather than at either curtailment
#   source.

# %% [markdown]
# ## Does real curtailment explain the potential-vs-observed gap?
#
# [The residual-load walkthrough](../markdown/residual_load_walkthrough.md)
# shows offshore wind's raw potential-minus-observed gap and calls it
# "(almost) entirely loss" -- there's no behind-the-meter term to blur it,
# unlike PV. Now that both real curtailment sources agree closely with each
# other for offshore wind (checked earlier in this notebook), it's worth
# checking whether they also explain that raw gap, or whether a real chunk
# of it is something else.

# %%
inputs = pd.read_parquet(paths.residual_load_inputs_file)
target_panel = pd.read_parquet(paths.target_panel_file).reindex(inputs.index)
implied_loss_mwh = (inputs["P_wind_off_mw"] - target_panel["wind_offshore"]).clip(lower=0).resample("MS").sum()

offshore_reduction = reduction.loc[reduction["tech"] == "offshore_wind"]
offshore_curtailment_mwh = offshore_reduction.groupby("month")["mwh"].sum()
gap_months = implied_loss_mwh.index.intersection(offshore_curtailment_mwh.index)

gap_comparison = pd.DataFrame({
    "implied_loss_mwh": implied_loss_mwh.reindex(gap_months),
    "actual_curtailment_mwh": offshore_curtailment_mwh.reindex(gap_months),
})
gap_comparison["explained_share_pct"] = (gap_comparison["actual_curtailment_mwh"] / gap_comparison["implied_loss_mwh"] * 100).round(1)
gap_comparison["explained_share_pct"].describe()

# %%
fig, ax = plt.subplots(figsize=(12, 4.5))
ax.plot(gap_comparison.index, gap_comparison["implied_loss_mwh"], label="Implied loss (potential - observed, hourly, clipped at 0)", linewidth=1.3)
ax.plot(gap_comparison.index, gap_comparison["actual_curtailment_mwh"], label="Actual curtailment (this file, named offshore entities)", linewidth=1.3, linestyle="--")
ax.set_ylabel("MWh / month")
ax.set_title("Offshore wind: raw potential-observed gap vs. real curtailment volume")
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "46_offshore_gap_vs_curtailment.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/46_offshore_gap_vs_curtailment.png
# :name: fig-46-offshore-gap-vs-curtailment
# Offshore wind, monthly: the raw potential-minus-observed gap vs. actual reported curtailment volume. Real curtailment sits well below the raw gap in every single month.
# ```
#
# ### Same comparison, daily resolution
#
# The monthly view could still hide a good day-to-day match underneath a
# noisy aggregate. It doesn't -- the same shortfall shows up day by day,
# not just after aggregating away the noise.

# %%
implied_loss_daily = (inputs["P_wind_off_mw"] - target_panel["wind_offshore"]).clip(lower=0).resample("D").sum()

daily_range = pd.date_range(
    max(offshore_reduction["start"].min().normalize(), implied_loss_daily.index.min()),
    min(offshore_reduction["start"].max().normalize(), implied_loss_daily.index.max()),
    freq="D",
)
offshore_curtailment_daily = offshore_reduction.groupby(offshore_reduction["start"].dt.normalize())["mwh"].sum().reindex(daily_range, fill_value=0.0)
implied_loss_daily = implied_loss_daily.reindex(daily_range)

fig, ax = plt.subplots(figsize=(13, 4.5))
ax.plot(daily_range, implied_loss_daily, label="Implied loss (potential - observed, daily, clipped at 0)", linewidth=0.5)
ax.plot(daily_range, offshore_curtailment_daily, label="Actual curtailment (this file, named offshore entities)", linewidth=0.5)
ax.set_ylabel("MWh / day")
ax.set_title("Offshore wind: raw potential-observed gap vs. real curtailment volume, daily")
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "46_offshore_gap_vs_curtailment_daily.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/46_offshore_gap_vs_curtailment_daily.png
# :name: fig-46-offshore-gap-vs-curtailment-daily
# Same comparison at daily resolution. The gap between the two lines is the norm, not an artifact of monthly smoothing -- on most individual days, real curtailment covers only a fraction of the raw potential-observed gap, and on many low-curtailment days it covers essentially none of it.
# ```

# %% [markdown]
# ### The same story on the original potential/observed axes
#
# Rather than looking at the gap in isolation, plotting potential, observed,
# and observed-plus-real-curtailment together shows directly how much of
# the gap adding real curtailment back in actually closes.

# %%
potential_monthly = inputs["P_wind_off_mw"].resample("MS").sum()
observed_monthly = target_panel["wind_offshore"].resample("MS").sum()
reconstructed_monthly = observed_monthly.reindex(gap_months) + offshore_curtailment_mwh.reindex(gap_months)

fig, ax = plt.subplots(figsize=(12, 4.5))
ax.plot(gap_months, potential_monthly.reindex(gap_months), label="Potential (this project's replication)", linewidth=1.3)
ax.plot(gap_months, observed_monthly.reindex(gap_months), label="Observed (SMARD)", linewidth=1.3, linestyle="--")
ax.plot(gap_months, reconstructed_monthly, label="Observed + actual curtailment", linewidth=1.3, linestyle=":")
ax.set_ylabel("MWh / month")
ax.set_title("Offshore wind: potential vs. observed vs. observed + real curtailment")
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "46_offshore_potential_observed_curtailment.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/46_offshore_potential_observed_curtailment.png
# :name: fig-46-offshore-potential-observed-curtailment
# Offshore wind, monthly: potential, observed, and observed plus real curtailment added back in. The dotted line moves partway toward potential but consistently falls short of closing the gap.
# ```

# %%
potential_daily = inputs["P_wind_off_mw"].resample("D").sum().reindex(daily_range)
observed_daily = target_panel["wind_offshore"].resample("D").sum().reindex(daily_range)
reconstructed_daily = observed_daily + offshore_curtailment_daily

fig, ax = plt.subplots(figsize=(13, 4.5))
ax.plot(daily_range, potential_daily, label="Potential (this project's replication)", linewidth=0.5)
ax.plot(daily_range, observed_daily, label="Observed (SMARD)", linewidth=0.5)
ax.plot(daily_range, reconstructed_daily, label="Observed + actual curtailment", linewidth=0.5)
ax.set_ylabel("MWh / day")
ax.set_title("Offshore wind: potential vs. observed vs. observed + real curtailment, daily")
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "46_offshore_potential_observed_curtailment_daily.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/46_offshore_potential_observed_curtailment_daily.png
# :name: fig-46-offshore-potential-observed-curtailment-daily
# Same three-way comparison at daily resolution. Observed-plus-curtailment tracks observed closely with only a modest lift toward potential on most days -- confirming, day by day, that real curtailment closes only part of the gap.
# ```
#
# ### Same three lines, zoomed into one representative window
#
# The full-period line above is too dense to read as a time series. Zooming
# into the same Nov-Dec 2023 window as
# [the residual-load walkthrough's own potential-vs-observed chart](../markdown/residual_load_walkthrough.md)
# makes the day-by-day relationship between the three series legible, and
# lets it be compared directly against that earlier, curtailment-free view.

# %%
window_2023 = slice("2023-11-01", "2023-12-31")
fig, ax = plt.subplots(figsize=(13, 4.5))
ax.plot(potential_daily.loc[window_2023].index, potential_daily.loc[window_2023], label="Potential (this project's replication)", linewidth=1.3)
ax.plot(observed_daily.loc[window_2023].index, observed_daily.loc[window_2023], label="Observed (SMARD)", linewidth=1.3)
ax.plot(reconstructed_daily.loc[window_2023].index, reconstructed_daily.loc[window_2023], label="Observed + actual curtailment", linewidth=1.3)
ax.set_ylabel("MWh / day")
ax.set_title("Offshore wind: potential vs. observed vs. observed + real curtailment, Nov-Dec 2023")
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "46_offshore_potential_observed_curtailment_daily_window.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/46_offshore_potential_observed_curtailment_daily_window.png
# :name: fig-46-offshore-potential-observed-curtailment-daily-window
# Same comparison, zoomed to Nov-Dec 2023. Observed + curtailment (green) sits between observed (orange) and potential (blue) on almost every day, closing part of the gap but rarely all of it -- especially visible on the high-potential plateau days where potential flatlines near its ceiling.
# ```
#
# It doesn't. Real curtailment explains only **~40% on average** of the
# raw gap (median ~44%), and never all of it -- the explained share
# ranges from essentially 0% (October 2021 - January 2022, before
# Redispatch 2.0 covered renewable curtailment as a distinct, separately
# reported category -- chapter 1) up to ~82% in a single best month. This
# is not a data-quality problem between the two curtailment sources -- they
# were just shown to agree with each other almost exactly for offshore
# wind. The more likely explanation is bias in this project's own
# "potential" replication (notebooks 31-36's offshore bias-correction
# chain): `P_wind_off_mw` is itself an estimate built from bias-corrected
# wind speed and a power curve, not a direct measurement, so a systematic
# overestimate there would show up here as apparent "gap" that no amount of
# real curtailment data could ever close. **The "(almost) entirely loss"
# framing in the residual-load walkthrough is too strong for offshore
# wind** -- a substantial share of that gap is more likely replication bias
# than real curtailment.

# %% [markdown]
# ### Scatter: observed + curtailment vs. potential, daily
#
# One more angle on the same question: each point is one day, x is this
# project's replicated potential, y is SMARD-observed plus real curtailment
# added back in. Points on the `y = x` line would mean real curtailment
# fully closes the gap.

# %%
fig, ax = plt.subplots(figsize=(6.5, 6.5))
ax.scatter(potential_daily, reconstructed_daily, s=6, alpha=0.35, linewidth=0)
axis_max = max(potential_daily.max(), reconstructed_daily.max())
ax.plot([0, axis_max], [0, axis_max], color="black", linewidth=1, linestyle="--", label="y = x")
ax.set_xlabel("Potential, MWh/day (this project's replication)")
ax.set_ylabel("Observed + actual curtailment, MWh/day")
ax.set_title("Offshore wind, daily: observed + curtailment vs. potential")
ax.set_xlim(0, axis_max)
ax.set_ylim(0, axis_max)
ax.set_aspect("equal")
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "46_offshore_scatter_potential_vs_reconstructed_daily.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/46_offshore_scatter_potential_vs_reconstructed_daily.png
# :name: fig-46-offshore-scatter-potential-vs-reconstructed-daily
# Offshore wind, daily: observed plus real curtailment vs. potential. Tightly correlated (r = 0.97) but sitting systematically below `y = x` -- a best-fit slope of 0.83, and the reconstructed total recovers about 87% of potential's daily sum over the whole period.
# ```

# %% [markdown]
# ### Same scatter, without adding curtailment back in
#
# The natural comparison: does adding real curtailment back onto observed
# actually move the picture closer to potential, or is the scatter above
# just what potential-vs-observed always looks like for offshore wind?

# %%
fig, ax = plt.subplots(figsize=(6.5, 6.5))
ax.scatter(potential_daily, observed_daily, s=6, alpha=0.35, linewidth=0, color="C1")
axis_max_obs = max(potential_daily.max(), observed_daily.max())
ax.plot([0, axis_max_obs], [0, axis_max_obs], color="black", linewidth=1, linestyle="--", label="y = x")
ax.set_xlabel("Potential, MWh/day (this project's replication)")
ax.set_ylabel("Observed, MWh/day (SMARD, no curtailment added)")
ax.set_title("Offshore wind, daily: observed vs. potential (raw, no curtailment)")
ax.set_xlim(0, axis_max_obs)
ax.set_ylim(0, axis_max_obs)
ax.set_aspect("equal")
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "46_offshore_scatter_potential_vs_observed_daily.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/46_offshore_scatter_potential_vs_observed_daily.png
# :name: fig-46-offshore-scatter-potential-vs-observed-daily
# Same scatter, but observed alone (no curtailment added back). Visibly more spread out from `y = x`, and the spread widens more sharply at high potential than the reconstructed version above does.
# ```

# %% [markdown]
# ### Which relationship is actually tighter?
#
# Eyeballing two scatter plots isn't a comparison -- computing the same
# metrics against both puts a number on the visual difference above.

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
    "observed_plus_curtailment": scatter_metrics(potential_daily, reconstructed_daily),
})
metrics_comparison

# %% [markdown]
# Adding real curtailment back onto observed makes the relationship to
# potential meaningfully tighter on every one of these metrics, not just
# one favorable one: correlation rises from 0.94 to 0.97, the R² against
# `y = x` itself (not a best-fit line -- literally "how close to matching
# potential exactly") nearly quadruples from 0.21 to 0.85, and the typical
# daily error (RMSE) drops by almost half, from ~35,200 to ~19,900 MWh/day.
# So real curtailment is doing real, substantial work in explaining the
# potential-observed gap -- it closes a large part of it (the R² jump is
# the clearest evidence of that) -- it just doesn't close all of it, which
# is the same conclusion the monthly comparison earlier in this section
# reached from a completely different angle (aggregate volume, not daily
# scatter).
