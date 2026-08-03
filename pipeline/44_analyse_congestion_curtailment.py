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
# # Data source: SMARD's monthly congestion-management series
#
# Before analysing curtailment, it's worth being precise about what this
# data actually measures -- its scope, its frequency, and how its numbers
# are calculated. This notebook covers SMARD's monthly series; the
# [next chapter](../notebooks/45_explore_redispatch_measures.ipynb) covers a
# second, higher-frequency source, and
# [the comparison chapter](../notebooks/46_attribute_ambiguous_redispatch_entities.ipynb)
# reconciles the two.

# %%
import matplotlib.pyplot as plt
import pandas as pd

from pecdr.paths import ProjPaths
from pecdr.smard_redispatch import download_smard_chart_series

paths = ProjPaths()
paths.ensure_directories()

redispatch = pd.read_parquet(paths.redispatch_by_source_file)
RENEWABLE_SOURCES = ["Wind_Onshore", "Wind_Offshore", "Photovoltaik"]
colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]

# %% [markdown]
# ## Attributes of this data source
#
# | Attribute | Value |
# |---|---|
# | **Grid level** | TSO **and** DSO combined -- checked directly: SMARD separately publishes a TSO-vs-DSO split for renewables (`s-nepm_re_eb-1-1x`), and summing its two columns lands within 0.3% of this series' renewable total for the same period. Not TSO-only. |
# | **Frequency** | Monthly |
# | **Measure types included** | **Not redispatch-only.** Summing this series' reduction *and* increase columns across all technologies matches, almost to the GWh, the sum of SMARD's three separately-published measure-type totals (Countertrading + Grid reserve + Redispatch-with-market-power-plants) -- see the verification section below. Countertrading and grid-reserve volume are folded into this "by energy source" view, not excluded from it. |
# | **Methodology** | **Ex-post, counterfactual.** The compensable quantity ("Ausfallarbeit") is defined as theoretical feed-in minus actual feed-in, computed after the measure using either a frozen pre-measure baseline or (for wind) actual wind speed plus the turbine's certified power curve -- see BDEW's [methodology guide](https://www.bdew.de/media/documents/Awh_2020-05_RD_2.0_LF_Ausfallarbeit.pdf). This is not a live instructed-power reading. |
# | **Location data** | None. Purely a national total -- no TSO, region, or plant-level breakdown in this series. |

# %% [markdown]
# ## Verifying our understanding against SMARD's own page
#
# SMARD publishes a yearly breakdown by measure type
# (`s-nepm_entw-1-1`) that isn't the series we use for the technology
# charts below, but reproducing its numbers is a good independent check
# that the CSV-parsing approach (`pecdr/smard_redispatch.py`) is sound. See
# [SMARD: "Volume of measures stable in the year as a whole"](https://www.smard.de/page/en/topic-article/5892/220534/volume-of-measures-stable-in-the-year-as-a-whole)
# for the interactive chart this reproduces.

# %%
measure_type_yearly = download_smard_chart_series(
    "s-nepm_entw-1-1",
    ["countertrading_gwh", "grid_reserve_gwh", "renewable_gwh", "feed_in_mgmt_gwh", "conventional_gwh", "other_gwh"],
)
measure_type_yearly.loc[measure_type_yearly["date"].dt.year == 2024]

# %% [markdown]
# This should read `5,739 / 1,787 / 9,389 / 0 / 13,403` GWh for 2024 --
# matching the page's own tooltip exactly (checked at the time this was
# written). That's real confirmation the data pipeline reads what it claims
# to read.

# %% [markdown]
# ## What the data actually looks like

# %%
redispatch.head(10)

# %% [markdown]
# ## Relevant facts about this data
#
# **Countertrading has no meaningful technology attribution.** It's a
# market transaction (buying/selling power to relieve a constraint), not an
# instruction to a specific named plant, so it can't be attributed a
# technology -- it should land in `Unbekannt`. Checked directly: monthly
# Countertrading volume (`s-nepm_ct-1-1`) correlates with `Unbekannt`
# (summed across both directions) at **0.95** over the whole series, though
# `Unbekannt` runs 1.4-1.8x larger than Countertrading alone -- the rest is
# plausibly grid-reserve or "not attributable" redispatch, which also lack
# a specific plant to attribute.

# %%
countertrading = download_smard_chart_series("s-nepm_ct-1-1", ["countertrading_gwh"])
unbekannt = redispatch.loc[redispatch["energy_source"] == "Unbekannt"].groupby("month")["gwh"].sum().rename("unbekannt_gwh")
ct_vs_unbekannt = countertrading.set_index("date").join(unbekannt, how="inner")
print(f"correlation(countertrading, unbekannt): {ct_vs_unbekannt['countertrading_gwh'].corr(ct_vs_unbekannt['unbekannt_gwh']):.2f}")

# %% [markdown]
# **Feed-in management is essentially zero in recent years** (see the 2024
# row above) -- the older, EEG-based curtailment mechanism has been folded
# into Redispatch 2.0's unified framework rather than continuing as a
# separate category.

# %% [markdown]
# ## Curtailment (reduction) volume by technology over time

# %%
reduction = redispatch.loc[redispatch["direction"] == "reduction"]
reduction_wide = reduction.pivot(index="month", columns="energy_source", values="gwh")

fig, ax = plt.subplots(figsize=(12, 5))
for i, source in enumerate(RENEWABLE_SOURCES):
    ax.plot(reduction_wide.index, reduction_wide[source], label=source.replace("_", " "), linewidth=1.3, color=colors[i])
other_sources = [c for c in reduction_wide.columns if c not in RENEWABLE_SOURCES]
ax.plot(reduction_wide.index, reduction_wide[other_sources].sum(axis=1), label="All conventional + other", linewidth=1.0, color="gray", linestyle="--")
ax.set_ylabel("GWh curtailed (reduction)")
ax.set_title("Monthly redispatch curtailment by energy source, 2022-2026")
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "44_curtailment_by_source_over_time.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/44_curtailment_by_source_over_time.png
# :name: fig-44-curtailment-by-source-over-time
# Monthly redispatch curtailment (reduction) volume by energy source. Wind onshore and offshore dominate; PV curtailment is smaller but visibly seasonal.
# ```

# %% [markdown]
# ## How much, in total, and whose share?

# %%
total_reduction_by_source = reduction.groupby("energy_source")["gwh"].sum().sort_values(ascending=False)
share = (total_reduction_by_source / total_reduction_by_source.sum() * 100).round(1)
summary = pd.DataFrame({"total_gwh": total_reduction_by_source.round(0), "share_pct": share})
summary

# %%
fig, ax = plt.subplots(figsize=(8, 5))
bar_colors = [colors[RENEWABLE_SOURCES.index(s) % len(colors)] if s in RENEWABLE_SOURCES else "lightgray" for s in total_reduction_by_source.index]
ax.bar([s.replace("_", " ") for s in total_reduction_by_source.index], total_reduction_by_source.values, color=bar_colors)
ax.set_ylabel("Total GWh curtailed, Jul 2022 - latest")
ax.set_title("Cumulative redispatch curtailment by energy source")
ax.tick_params(axis="x", rotation=45)
fig.tight_layout()
fig.savefig(paths.images_path / "44_cumulative_curtailment_by_source.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/44_cumulative_curtailment_by_source.png
# :name: fig-44-cumulative-curtailment-by-source
# Total curtailed energy per source over the full period covered by this data -- `Unbekannt` (mostly countertrading) is the single largest bar.
# ```

# %% [markdown]
# ## When during the year does curtailment happen?

# %%
reduction_renewables = reduction.loc[reduction["energy_source"].isin(RENEWABLE_SOURCES)].copy()
reduction_renewables["calendar_month"] = reduction_renewables["month"].dt.month
seasonal = reduction_renewables.groupby(["energy_source", "calendar_month"])["gwh"].mean().unstack("energy_source")

fig, ax = plt.subplots(figsize=(10, 5))
for i, source in enumerate(RENEWABLE_SOURCES):
    ax.plot(seasonal.index, seasonal[source], marker="o", label=source.replace("_", " "), color=colors[i])
ax.set_xlabel("Calendar month")
ax.set_ylabel("Average GWh curtailed")
ax.set_title("Seasonal pattern of curtailment, averaged across 2022-2026")
ax.set_xticks(range(1, 13))
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "44_seasonal_curtailment_pattern.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/44_seasonal_curtailment_pattern.png
# :name: fig-44-seasonal-curtailment-pattern
# Average curtailment by calendar month -- wind peaks in autumn/winter; PV's curtailment tracks its own generation season, peaking in spring/summer.
# ```

# %% [markdown]
# ## Congestion management by type of measure, 2015-2026

# %%
fig, ax = plt.subplots(figsize=(12, 5))
measure_cols = ["countertrading_gwh", "grid_reserve_gwh", "renewable_gwh", "feed_in_mgmt_gwh", "conventional_gwh"]
measure_labels = ["Countertrading", "Redispatch (reserve plants)", "Redispatch (renewables)", "Feed-in management", "Redispatch (conventional)"]
ax.stackplot(
    measure_type_yearly["date"],
    [measure_type_yearly[c] for c in measure_cols],
    labels=measure_labels,
    colors=[colors[i % len(colors)] for i in range(len(measure_cols))],
    alpha=0.85,
)
ax.set_ylabel("GWh")
ax.set_title("Congestion management volume by type of measure, 2015-2026")
ax.legend(loc="upper left")
fig.tight_layout()
fig.savefig(paths.images_path / "44_measure_type_over_time.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/44_measure_type_over_time.png
# :name: fig-44-measure-type-over-time
# Total congestion-management volume by measure type, 2015-2026 -- redispatch with renewables only became a distinct, large category from 2022 onward (Redispatch 2.0).
# ```

# %% [markdown]
# ## Takeaways
#
# - This is a **TSO+DSO, monthly, ex-post counterfactual** figure that
#   folds in countertrading and grid-reserve volume -- not a narrow,
#   redispatch-only, TSO-only, real-time reading. Keep that in mind when
#   comparing it against any other source (see the comparison chapter).
# - Wind dominates curtailment volume; offshore is curtailed
#   disproportionately to its fleet size; PV's smaller curtailment tracks
#   its own generation season.
# - `Unbekannt` -- mostly countertrading, which has no plant to attribute a
#   technology to -- is the single largest category, bigger than any one
#   generation technology.
