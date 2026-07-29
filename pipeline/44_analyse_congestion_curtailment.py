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
# # How much curtailment actually happens, and when?
#
# Before building any model of curtailment, it's worth just looking at real
# ground truth: since July 2022, SMARD publishes how much feed-in was
# reduced or increased under Germany's Redispatch 2.0 regime, broken down
# by energy carrier. This notebook is purely descriptive -- no modeling, no
# comparison to this project's own estimates (see `pecdr/smard_redispatch.py`
# and `book/markdown/congestion_curtailment_data.md` for how the data is
# fetched and what it can/can't tell us).
#
# Two important scope limits to keep in view throughout: this is **monthly,
# national-only** data (no hour-of-day or regional detail), and it's
# **redispatch specifically** -- grid-operator-ordered curtailment, not
# market-based (negative-price) curtailment, which is a separate mechanism
# this data doesn't capture at all.

# %%
import matplotlib.pyplot as plt
import pandas as pd

from pecdr.paths import ProjPaths

paths = ProjPaths()
paths.ensure_directories()

redispatch = pd.read_parquet(paths.redispatch_by_source_file)
RENEWABLE_SOURCES = ["Wind_Onshore", "Wind_Offshore", "Photovoltaik"]
colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]

# %% [markdown]
# ## Reductions vs. increases: a quick sanity check on semantics
#
# "Reduction" is curtailment-down (feed-in cut below what a plant could
# have produced); "increase" is counter-trading up-regulation (a plant
# asked to produce *more* to compensate elsewhere on the grid). If the data
# means what it says, increases should be dominated by conventional/gas
# plants, since curtailing renewables and then also asking them to ramp up
# doesn't make physical sense -- renewables should appear almost
# exclusively on the reduction side.

# %%
totals_by_direction = redispatch.groupby(["direction", "energy_source"])["gwh"].sum().unstack("direction").fillna(0.0)
totals_by_direction["reduction_share_of_total"] = totals_by_direction["reduction"] / (
    totals_by_direction["reduction"] + totals_by_direction["increase"]
)
totals_by_direction.sort_values("reduction", ascending=False)

# %% [markdown]
# As expected: the three renewable sources sit at (or very near) 100%
# reduction share, while conventional sources split much more evenly
# between the two directions -- confirms the reduction/increase labeling
# behaves the way the terminology suggests.

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
# Total curtailed energy per source over the full period covered by this data.
# ```
#
# Worth noting directly: wind offshore's cumulative curtailment (16,108 GWh)
# is actually *larger* than wind onshore's (12,873 GWh), despite offshore's
# installed fleet being only about a seventh the size of onshore's (~9.2 GW
# vs. ~63.1 GW in 2025 -- see `pecdr.paths.ProjPaths.residual_load_inputs_file`'s
# `Capacity_wind_off_mw`/`Capacity_wind_on_mw` columns). Per MW installed,
# that's roughly **8-9x more curtailment for offshore than onshore** over
# this period -- consistent with known transmission bottlenecks moving
# northern offshore generation south to load centers.

# %% [markdown]
# ## When during the year does curtailment happen?
#
# The closest this monthly data can get to "when": averaging by calendar
# month across the ~3.5 years covered, separately per renewable technology.

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
# Average curtailment by calendar month -- wind (both onshore and offshore) peaks in the windier autumn/winter months; PV's curtailment tracks its own generation season, peaking in spring/summer.
# ```

# %% [markdown]
# ## Takeaways
#
# - **Wind dominates curtailment volume**, and offshore is curtailed far
#   more heavily relative to its fleet size than onshore -- a real,
#   measured asymmetry this project's model doesn't currently distinguish
#   (the curtailment curve in notebooks 39/40/42 is calibrated on *pooled*
#   onshore+offshore wind, then transferred to PV as well).
# - **PV curtailment is real but smaller in absolute terms**, and clearly
#   seasonal, peaking alongside PV's own generation season rather than at
#   some independent time.
# - **This is a lower bound on total curtailment**, not the whole picture:
#   it only captures grid-operator-ordered redispatch, not market-based
#   (negative-price) curtailment, which this data source doesn't report at
#   all.
# - The natural next question -- does this real data actually support the
#   wind-to-PV curve-transfer assumption used in the residual-load model,
#   or does it call for a PV-specific curve -- is deliberately left open
#   here; this chapter's only job was building a feel for the data itself.
