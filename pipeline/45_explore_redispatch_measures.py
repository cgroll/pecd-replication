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
# # Data source: netztransparenz's per-measure Redispatch export
#
# The [previous chapter](../notebooks/44_analyse_congestion_curtailment.ipynb)
# covered SMARD's monthly, TSO+DSO, ex-post counterfactual series.
# netztransparenz.de separately publishes a live, per-measure export --
# real start/end timestamps, per-plant/cluster names, a coarse energy-type
# flag -- with different tradeoffs. This notebook describes it on its own
# terms; [the comparison chapter](../notebooks/46_attribute_ambiguous_redispatch_entities.ipynb)
# reconciles the two.

# %%
import matplotlib.pyplot as plt
import pandas as pd

from pecdr.paths import ProjPaths
from pecdr.redispatch_measures import load_redispatch_measures

paths = ProjPaths()
paths.ensure_directories()

measures = load_redispatch_measures(paths.redispatch_measures_file)
reduction = measures.loc[measures["direction"] == "reduction"]
renewable_reduction = reduction.loc[reduction["primary_energy_type"] == "Erneuerbar"]
colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]

# %% [markdown]
# ## Attributes of this data source
#
# | Attribute | Value |
# |---|---|
# | **Grid level** | Every measure's `ANWEISENDER_UENB` (instructing party) is one of the four German TSOs -- checked directly, never a DSO name. This confirms TSO-*issued*, but not necessarily TSO-*connected*-only: a TSO can instruct redispatch for a distribution-connected plant too, so this isn't a clean TSO-vs-DSO split the way SMARD's own `s-nepm_re_eb` series is. |
# | **Frequency** | Per-measure -- real start/end timestamps (often sub-hourly), not a monthly aggregate. |
# | **Source type** | Coarse: `Konventionell` / `Erneuerbar` / `Sonstiges` only. Within `Erneuerbar`, the plant/cluster *name* reveals the specific technology for offshore wind 100% of the time, but only ~1% of onshore wind's and ~4% of PV's true volume -- most of both sit under anonymous substation/cluster codes (see "ambiguous" below). |
# | **Methodology** | Likely ex-post but mechanical -- `GESAMTE_ARBEIT_MWH` reads like an immediate figure (instructed power x duration), not the settled, weather-informed counterfactual SMARD's monthly figure represents. This is an inference from the field's role in a live operational export, not a confirmed specification. |
# | **Location data** | A coarse proxy only: `ANWEISENDER_UENB`/`ANFORDERNDER_UENB` (instructing/requesting TSO, 4 zones) -- no coordinates. TenneT's zone spans both the North Sea coast and Bavaria, so it doesn't map cleanly to "region." |

# %% [markdown]
# ## What the data actually looks like

# %%
measures.head(10)

# %% [markdown]
# ## Relevant facts about this data
#
# **A naming-convention change silently affected technology classification
# partway through the file.** Four of TenneT's North Sea offshore
# grid-connection substations (`Büttel`, `Diele`, `Dörpen-West`,
# `Emden-Ost`) were reported as `"OWP UW ..."` through July 2025, then as
# plain `"UW ..."` from August 2025 onward -- the same physical,
# offshore-only substations, just relabeled. A name-substring classifier
# has no way to know that on its own; `pecdr/redispatch_measures.py`
# handles it with an explicit `RENAMED_OFFSHORE_SUBSTATIONS` list, found by
# noticing an odd shape in an early version of the chart below (offshore
# appearing to collapse for several months, exactly mirrored by a spike in
# the "ambiguous" bucket) -- a reminder that classification keyed on
# scraped naming conventions needs to be re-checked periodically, not
# assumed stable.

# %%
def classify_summary(df: pd.DataFrame) -> pd.Series:
    return df.groupby("tech")["mwh"].sum().sort_values(ascending=False)


classify_summary(renewable_reduction)

# %% [markdown]
# **Almost all reduction volume is "electricity-related" redispatch**, not
# voltage-related or a test/probe measure:

# %%
reason_counts = renewable_reduction["reason"].value_counts()
reason_mwh = renewable_reduction.groupby("reason")["mwh"].sum().sort_values(ascending=False)
pd.DataFrame({"n_measures": reason_counts, "total_mwh": reason_mwh}).sort_values("total_mwh", ascending=False)

# %% [markdown]
# ## Monthly reduction volume by classified technology, over time

# %%
monthly = renewable_reduction.groupby(["month", "tech"])["mwh"].sum().unstack("tech").fillna(0.0)

fig, ax = plt.subplots(figsize=(12, 5))
for i, tech in enumerate(["offshore_wind", "onshore_wind_named", "pv"]):
    ax.plot(monthly.index, monthly[tech], label=tech.replace("_", " "), linewidth=1.3, color=colors[i])
ax.plot(monthly.index, monthly["ambiguous"], label="ambiguous (substation/cluster codes)", linewidth=1.0, color="gray", linestyle="--")
ax.set_ylabel("MWh curtailed (reduction)")
ax.set_title("Monthly redispatch curtailment by classified technology, 2022-2026")
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "45_monthly_by_classified_tech.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/45_monthly_by_classified_tech.png
# :name: fig-45-monthly-by-classified-tech
# Monthly redispatch curtailment volume by name-based technology classification, Jan 2022 onward -- six months earlier than SMARD's own series starts.
# ```

# %% [markdown]
# ## Seasonal pattern, by classified technology

# %%
renewable_reduction = renewable_reduction.copy()
renewable_reduction["calendar_month"] = renewable_reduction["month"].dt.month
seasonal = renewable_reduction.groupby(["tech", "calendar_month"])["mwh"].sum().unstack("tech").fillna(0.0)

fig, ax = plt.subplots(figsize=(10, 5))
for i, tech in enumerate(["offshore_wind", "onshore_wind_named", "pv"]):
    ax.plot(seasonal.index, seasonal[tech], marker="o", label=tech.replace("_", " "), color=colors[i])
ax.plot(seasonal.index, seasonal["ambiguous"], marker="o", label="ambiguous", color="gray", linestyle="--")
ax.set_xlabel("Calendar month")
ax.set_ylabel("Total MWh curtailed, summed across years")
ax.set_title("Seasonal pattern by classified technology")
ax.set_xticks(range(1, 13))
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "45_seasonal_by_classified_tech.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/45_seasonal_by_classified_tech.png
# :name: fig-45-seasonal-by-classified-tech
# Seasonal pattern by classified technology -- the ambiguous bucket's own shape tracks wind's far more closely than PV's, an early hint (confirmed formally in the comparison chapter) that it's mostly onshore wind.
# ```

# %% [markdown]
# ## Spatial proxy: reduction volume by instructing TSO

# %%
tso_totals = renewable_reduction.groupby("instructing_tso")["mwh"].sum().sort_values(ascending=False)
fig, ax = plt.subplots(figsize=(7, 5))
ax.bar(tso_totals.index, tso_totals.values, color=colors[: len(tso_totals)])
ax.set_ylabel("MWh curtailed (reduction), Erneuerbar")
ax.set_title("Renewable redispatch curtailment by instructing TSO")
ax.tick_params(axis="x", rotation=30)
fig.tight_layout()
fig.savefig(paths.images_path / "45_curtailment_by_tso.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/45_curtailment_by_tso.png
# :name: fig-45-curtailment-by-tso
# Renewable redispatch curtailment volume by instructing TSO -- a coarse regional proxy; TenneT's area spans both the North Sea coast and Bavaria.
# ```

# %% [markdown]
# ## Takeaways
#
# - This is a **TSO-issued, per-measure, ex-post-but-mechanical** figure
#   with a much finer time resolution than SMARD's monthly series, but a
#   much coarser technology label for anything except offshore wind.
# - Offshore wind is fully name-identifiable; onshore wind and PV are
#   overwhelmingly hidden behind anonymous substation/cluster codes.
# - A real naming-convention change mid-file is a concrete reminder that
#   scraped classification needs periodic re-validation, not a one-time fit.
