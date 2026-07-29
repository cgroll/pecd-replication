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
# # Illustrating the residual-load model
#
# Supporting charts for the teaching walkthrough
# (`book/markdown/residual_load_walkthrough.md`) -- not new analysis, just
# focused illustrations of results already established in notebooks 38-40,
# using representative time windows instead of the full 7-year backtest
# (too dense to read at a glance).

# %%
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from pecdr.paths import ProjPaths
from pecdr.residual_load import AGGREGATE_DEMAND_FORMULA, curtailment_rate, fit_curtailment_curve, predict_curtailment_mw

paths = ProjPaths()
paths.ensure_directories()

inputs = pd.read_parquet(paths.residual_load_inputs_file)
target_panel = pd.read_parquet(paths.target_panel_file).reindex(inputs.index)

# %% [markdown]
# ## Wind offshore: potential vs. observed, a representative window
#
# Chosen deliberately in winter, when offshore wind (and curtailment) is at
# its most active. This gap is **not** apples-to-apples either -- wind has
# no behind-the-meter self-consumption, but curtailment alone still opens up
# a real, substantial gap between what could have been generated and what
# actually reached the grid.

# %%
window_wind = slice("2023-11-01", "2023-12-31")
fig, ax = plt.subplots(figsize=(13, 4.5))
ax.plot(inputs.loc[window_wind].index, inputs.loc[window_wind, "P_wind_off_mw"], label="Potential (this project's replication)", linewidth=0.9)
ax.plot(target_panel.loc[window_wind].index, target_panel.loc[window_wind, "wind_offshore"], label="Observed (SMARD)", linewidth=0.9)
ax.set_ylabel("MW")
ax.set_title("Wind offshore: potential vs. observed, Nov-Dec 2023")
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "41_wind_offshore_potential_vs_observed.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/41_wind_offshore_potential_vs_observed.png
# :name: fig-41-wind-offshore-potential-vs-observed
# Wind offshore potential vs. observed generation, Nov-Dec 2023 -- the gap is almost entirely curtailment (+ minor repair/model error), since wind has no behind-the-meter term.
# ```

# %% [markdown]
# ## Solar PV: potential vs. observed, a representative window
#
# Summer, when PV output (and both curtailment and self-consumption) is
# highest. This gap mixes two things the wind chart above doesn't have to:
# curtailment *and* behind-the-meter self-consumption.

# %%
window_pv = slice("2023-06-01", "2023-07-31")
fig, ax = plt.subplots(figsize=(13, 4.5))
ax.plot(inputs.loc[window_pv].index, inputs.loc[window_pv, "P_pv_mw"], label="Potential (this project's replication)", linewidth=0.9)
ax.plot(target_panel.loc[window_pv].index, target_panel.loc[window_pv, "pv"], label="Observed (SMARD)", linewidth=0.9)
ax.set_ylabel("MW")
ax.set_title("Solar PV: potential vs. observed, Jun-Jul 2023")
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "41_pv_potential_vs_observed.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/41_pv_potential_vs_observed.png
# :name: fig-41-pv-potential-vs-observed
# Solar PV potential vs. observed generation, Jun-Jul 2023 -- the gap here is curtailment *and* self-consumption combined.
# ```

# %% [markdown]
# ## Decomposing PV's gap: curtailment vs. everything else
#
# Rebuilds notebook 39's decomposition (wind-calibrated curtailment curve,
# applied to PV via the potential-based oversupply proxy) to produce one
# summary number for the illustration below.

# %%
import statsmodels.formula.api as smf  # noqa: E402

demand_model = smf.ols(AGGREGATE_DEMAND_FORMULA, data=inputs).fit()
d_true_hat = demand_model.predict(inputs.assign(P_pv_mw=0.0))

p_total = inputs["P_wind_on_mw"] + inputs["P_wind_off_mw"] + inputs["P_pv_mw"]
oversupply_proxy = p_total / d_true_hat
bins = np.linspace(0, oversupply_proxy.quantile(0.995), 21)

min_potential_on = 0.05 * inputs["P_wind_on_mw"].max()
min_potential_off = 0.05 * inputs["P_wind_off_mw"].max()
p_wind_total = inputs["P_wind_on_mw"].where(inputs["P_wind_on_mw"] > min_potential_on, 0) + inputs["P_wind_off_mw"].where(
    inputs["P_wind_off_mw"] > min_potential_off, 0
)
gap_wind_total = (inputs["P_wind_on_mw"] - target_panel["wind_onshore"]).where(inputs["P_wind_on_mw"] > min_potential_on, 0) + (
    inputs["P_wind_off_mw"] - target_panel["wind_offshore"]
).where(inputs["P_wind_off_mw"] > min_potential_off, 0)
rate_wind_pooled = (gap_wind_total / p_wind_total).where(p_wind_total > 0)
curve = fit_curtailment_curve(rate_wind_pooled, oversupply_proxy, bins)

gap_pv = inputs["P_pv_mw"] - target_panel["pv"]
predicted_curtailment_pv = predict_curtailment_mw(curve, oversupply_proxy, inputs["P_pv_mw"])
residual_pv = gap_pv - predicted_curtailment_pv

raw_gap, curtailment_part, residual_part = gap_pv.mean(), predicted_curtailment_pv.mean(), residual_pv.mean()
print(f"Raw gap: {raw_gap:.0f} MW = curtailment {curtailment_part:.0f} MW + residual {residual_part:.0f} MW")

fig, ax = plt.subplots(figsize=(4.5, 5.5))
colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
ax.bar(["PV's average gap\nvs. SMARD"], [curtailment_part], width=0.5, color=colors[0])
ax.bar(["PV's average gap\nvs. SMARD"], [residual_part], bottom=[curtailment_part], width=0.5, color=colors[1])
ax.text(0, curtailment_part / 2, f"Predicted\ncurtailment\n{curtailment_part:.0f} MW", ha="center", va="center", color="white", fontweight="bold")
ax.text(
    0,
    curtailment_part + residual_part / 2,
    f"Residual (self-consumption\n+ repair + model error)\n{residual_part:.0f} MW",
    ha="center",
    va="center",
    color="white",
    fontweight="bold",
    fontsize=8,
)
ax.set_ylabel("MW")
ax.set_title("PV's gap against SMARD, decomposed")
fig.tight_layout()
fig.savefig(paths.images_path / "41_pv_gap_decomposition.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/41_pv_gap_decomposition.png
# :name: fig-41-pv-gap-decomposition
# PV's average gap against SMARD, decomposed into wind-calibrated predicted curtailment and everything left over.
# ```
