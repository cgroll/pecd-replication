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
# # Walk-forward CF-conditional bias correction
#
# `22_analyse_bias_drivers` found this project's replication (approach 3)
# overshoots SMARD's actual wind-onshore CF in a way that grows roughly
# monotonically with CF level, and recommended a CF-conditional statistical
# correction as the practical next step rather than trying to model
# curtailment mechanistically (no public ground truth exists to calibrate
# a mechanistic model against -- see `../markdown/index.md`).
#
# This notebook fits that correction and tests it honestly: a monotonic
# calibration curve (`pecdr.bias_correction`, isotonic regression of SMARD
# CF on modeled CF) is fit on **one calendar year only**, then applied to
# the **next** year -- never fit and evaluated on the same data. Walk
# forward across the whole backtest period: train on 2019, correct 2020;
# train on 2020, correct 2021; ... train on 2024, correct 2025. 2019 itself
# is left uncorrected (no earlier year available in this project's
# backtest range) and serves as the uncorrected baseline.

# %%
import matplotlib.pyplot as plt
import pandas as pd

from pecdr.bias_correction import apply_correction, fit_isotonic_correction
from pecdr.capacity_weighting import total_hourly_capacity
from pecdr.domain import FULL_YEAR_BACKTEST_YEARS
from pecdr.paths import ProjPaths

paths = ProjPaths()
paths.ensure_directories()

TEST_YEARS = FULL_YEAR_BACKTEST_YEARS[1:]  # 2019 has no earlier year to train on

# %% [markdown]
# ## Rebuild this project's replication vs. SMARD, full backtest period

# %%
mastr_peon_month = pd.read_parquet(paths.mastr_capacity_by_peon_month_file)
target_panel = pd.read_parquet(paths.target_panel_file)
total_capacity_hourly = total_hourly_capacity(mastr_peon_month, target_panel.index)
smard_implied_cf = target_panel["wind_onshore"] / total_capacity_hourly

model_cf = pd.read_parquet(paths.wind_onshore_full_year_cf_file)["national"]

comparison = pd.DataFrame({"model_cf": model_cf, "smard_cf": smard_implied_cf}).loc[
    FULL_YEAR_BACKTEST_YEARS[0]:FULL_YEAR_BACKTEST_YEARS[-1]
].dropna()

# %% [markdown]
# ## Walk forward: fit on year Y-1, correct year Y

# %%
corrected_parts = []
for test_year in TEST_YEARS:
    train_year = str(int(test_year) - 1)
    train = comparison.loc[train_year]
    test = comparison.loc[test_year]

    x_sorted, fitted_y = fit_isotonic_correction(train["model_cf"], train["smard_cf"])
    corrected_parts.append(apply_correction(x_sorted, fitted_y, test["model_cf"]))

comparison["corrected_cf"] = pd.concat(corrected_parts)
comparison["diff_raw"] = comparison["model_cf"] - comparison["smard_cf"]
comparison["diff_corrected"] = comparison["corrected_cf"] - comparison["smard_cf"]

tested = comparison.loc[TEST_YEARS[0]:TEST_YEARS[-1]].dropna(subset=["corrected_cf"])
print(f"Hours corrected (test years {TEST_YEARS[0]}-{TEST_YEARS[-1]}): {len(tested):,}")
print(f"Raw       -- bias: {tested['diff_raw'].mean():.4f}, MAE: {tested['diff_raw'].abs().mean():.4f}")
print(f"Corrected -- bias: {tested['diff_corrected'].mean():.4f}, MAE: {tested['diff_corrected'].abs().mean():.4f}")

# %% [markdown]
# ## Does correction reduce bias/MAE in every test year, out of sample?

# %%
yearly = pd.DataFrame({
    "raw_bias": tested.groupby(tested.index.year)["diff_raw"].mean(),
    "raw_mae": tested.groupby(tested.index.year)["diff_raw"].apply(lambda s: s.abs().mean()),
    "corrected_bias": tested.groupby(tested.index.year)["diff_corrected"].mean(),
    "corrected_mae": tested.groupby(tested.index.year)["diff_corrected"].apply(lambda s: s.abs().mean()),
})

fig, axes = plt.subplots(1, 2, figsize=(13, 5))
x = yearly.index.to_numpy()
width = 0.35
for ax, raw_col, corrected_col, ylabel, title in [
    (axes[0], "raw_bias", "corrected_bias", "Mean bias (model - SMARD)", "Bias, raw vs. corrected"),
    (axes[1], "raw_mae", "corrected_mae", "MAE", "MAE, raw vs. corrected"),
]:
    ax.bar(x - width / 2, yearly[raw_col], width=width, label="Raw", color="#4C72B0")
    ax.bar(x + width / 2, yearly[corrected_col], width=width, label="Corrected", color="#55A868")
    ax.axhline(0, color="k", linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xlabel("Test year")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "23_bias_correction_by_year.png", dpi=150, bbox_inches="tight")
plt.show()

yearly

# %% [markdown]
# ```{figure} ../../output/images/23_bias_correction_by_year.png
# :name: fig-23-bias-correction-by-year
# Bias and MAE, raw vs. walk-forward-corrected, per out-of-sample test year (2020-2025).
# ```

# %% [markdown]
# ## Before / after, pooled across all test years

# %%
fig, axes = plt.subplots(1, 2, figsize=(11, 5.5))
for ax, col, label in [(axes[0], "model_cf", "Raw modeled CF"), (axes[1], "corrected_cf", "Corrected CF")]:
    diff_col = "diff_raw" if col == "model_cf" else "diff_corrected"
    mae = tested[diff_col].abs().mean()
    corr = tested[col].corr(tested["smard_cf"])
    ax.scatter(tested["smard_cf"], tested[col], s=2, alpha=0.05)
    lims = [0, max(tested["smard_cf"].max(), tested[col].max())]
    ax.plot(lims, lims, "k--", alpha=0.5, label="1:1")
    ax.set_xlabel("SMARD-implied CF")
    ax.set_ylabel(label)
    ax.set_title(f"{label}\nMAE={mae:.3f}, corr={corr:.3f}")
    ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "23_raw_vs_corrected_scatter.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/23_raw_vs_corrected_scatter.png
# :name: fig-23-raw-vs-corrected-scatter
# Raw vs. walk-forward-corrected modeled CF against SMARD, pooled across all out-of-sample test years (2020-2025).
# ```

# %% [markdown]
# ## Takeaways
#
# The correction is fit blind to the year it's applied to (strictly
# walk-forward, never fit-and-evaluate-on-the-same-year), so any
# improvement reflects the bias's known CF-conditional structure actually
# generalizing one year ahead, not overfitting. Whether it does, and by how
# much, is the print-out and the bias-by-year panel above -- read those
# together with `22_analyse_bias_drivers`' finding that the bias itself
# stepped up after 2022 rather than staying constant: a correction trained
# on the year immediately before should adapt to that kind of slow drift
# reasonably well (each year's training data reflects last year's
# curtailment regime), but would lag a sudden, sharp regime change within
# a single year.
