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
# # Offshore wind: does curtailment explain the potential-observed gap?
#
# [The previous chapter](../notebooks/46_attribute_ambiguous_redispatch_entities.ipynb)
# showed that netztransparenz's per-measure export and SMARD's monthly
# series agree almost exactly (100%) on offshore-wind curtailment volume --
# unusually clean confirmation for a technology whose entities are named
# individually in the per-measure file. With both curtailment sources
# trusted, this chapter asks the next question:
# [the residual-load walkthrough](../markdown/residual_load_walkthrough.md)
# shows offshore wind's raw potential-minus-observed gap and calls it
# "(almost) entirely loss" -- there's no behind-the-meter term to blur it,
# unlike PV. Does real (redispatch) curtailment actually explain that raw
# gap? And for whatever's left over, do negative day-ahead prices -- which
# can drive plant operators to curtail voluntarily, entirely outside of any
# grid-congestion redispatch instruction -- explain the rest?

# %%
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from pecdr.paths import ProjPaths
from pecdr.redispatch_measures import load_redispatch_measures

paths = ProjPaths()
paths.ensure_directories()

measures = load_redispatch_measures(paths.redispatch_measures_file)
reduction = measures.loc[measures["direction"] == "reduction"]

inputs = pd.read_parquet(paths.residual_load_inputs_file)
target_panel = pd.read_parquet(paths.target_panel_file).reindex(inputs.index)

# %% [markdown]
# ## Does real curtailment explain the potential-vs-observed gap?

# %%
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
fig.savefig(paths.images_path / "48_offshore_gap_vs_curtailment.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/48_offshore_gap_vs_curtailment.png
# :name: fig-48-offshore-gap-vs-curtailment
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
fig.savefig(paths.images_path / "48_offshore_gap_vs_curtailment_daily.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/48_offshore_gap_vs_curtailment_daily.png
# :name: fig-48-offshore-gap-vs-curtailment-daily
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
fig.savefig(paths.images_path / "48_offshore_potential_observed_curtailment.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/48_offshore_potential_observed_curtailment.png
# :name: fig-48-offshore-potential-observed-curtailment
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
fig.savefig(paths.images_path / "48_offshore_potential_observed_curtailment_daily.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/48_offshore_potential_observed_curtailment_daily.png
# :name: fig-48-offshore-potential-observed-curtailment-daily
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
fig.savefig(paths.images_path / "48_offshore_potential_observed_curtailment_daily_window.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/48_offshore_potential_observed_curtailment_daily_window.png
# :name: fig-48-offshore-potential-observed-curtailment-daily-window
# Same comparison, zoomed to Nov-Dec 2023. Observed + curtailment (green) sits between observed (orange) and potential (blue) on almost every day, closing part of the gap but rarely all of it -- especially visible on the high-potential plateau days where potential flatlines near its ceiling.
# ```
#
# It doesn't. Real curtailment explains only **~40% on average** of the
# raw gap (median ~44%), and never all of it -- the explained share
# ranges from essentially 0% (October 2021 - January 2022, before
# Redispatch 2.0 covered renewable curtailment as a distinct, separately
# reported category -- [chapter 1](../notebooks/44_analyse_congestion_curtailment.ipynb))
# up to ~82% in a single best month.

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
fig.savefig(paths.images_path / "48_offshore_scatter_potential_vs_reconstructed_daily.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/48_offshore_scatter_potential_vs_reconstructed_daily.png
# :name: fig-48-offshore-scatter-potential-vs-reconstructed-daily
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
fig.savefig(paths.images_path / "48_offshore_scatter_potential_vs_observed_daily.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/48_offshore_scatter_potential_vs_observed_daily.png
# :name: fig-48-offshore-scatter-potential-vs-observed-daily
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
# the clearest evidence of that) -- it just doesn't close all of it. The
# more likely explanation for the rest is bias in this project's own
# "potential" replication (notebooks 31-36's offshore bias-correction
# chain): `P_wind_off_mw` is itself an estimate built from bias-corrected
# wind speed and a power curve, not a direct measurement, so a systematic
# overestimate there would show up here as apparent "gap" that no amount of
# real curtailment data could ever close. **The "(almost) entirely loss"
# framing in the residual-load walkthrough is too strong for offshore
# wind** -- a substantial share of that gap is more likely replication bias
# than real curtailment. Before accepting that conclusion, though, there's
# one more real-world source of loss this chapter hasn't touched yet:
# curtailment a plant chooses voluntarily, without any redispatch
# instruction at all, when the day-ahead price goes negative.

# %% [markdown]
# ## Do negative prices explain the rest?
#
# Redispatch is a TSO-instructed measure, issued for grid-congestion
# reasons. But a wind-offshore operator facing a negative day-ahead price
# has its own incentive to produce less regardless of congestion -- selling
# into a negative price means paying to feed in. That kind of
# price-driven throttling would never show up in either curtailment source
# used above (both are congestion/redispatch specific), yet it would still
# open up a gap between potential and observed.

# %%
price = pd.read_parquet(paths.smard_raw_file("price_de_lu"))["price_de_lu"].reindex(inputs.index)
negative_price_share = (price < 0).mean()
print(f"Negative-price hours: {(price < 0).sum():,} of {len(price):,} ({negative_price_share:.1%})")

# %% [markdown]
# ### A simple first test: does the curtailment-only fit improve once negative-price days are set aside?
#
# The scatter and metrics table from the section above (`observed + actual
# curtailment` vs. `potential`) are the model being tested. If negative
# prices are part of what that model is missing, its fit should be
# noticeably worse specifically on days that had a negative price, and
# noticeably better on days that didn't -- no new equation needed, just
# the same comparison split into two groups.

# %%
has_negative_price_daily = (price < 0).resample("D").max().reindex(daily_range).fillna(False)

fig, ax = plt.subplots(figsize=(6.5, 6.5))
for flag, color, label in [
    (False, "C0", "No negative-price hour that day"),
    (True, "C3", "At least one negative-price hour"),
]:
    mask = has_negative_price_daily == flag
    ax.scatter(potential_daily[mask], reconstructed_daily[mask], s=10, alpha=0.4, linewidth=0, color=color, label=label)
axis_max_split = max(potential_daily.max(), reconstructed_daily.max())
ax.plot([0, axis_max_split], [0, axis_max_split], color="black", linewidth=1, linestyle="--", label="y = x")
ax.set_xlabel("Potential, MWh/day (this project's replication)")
ax.set_ylabel("Observed + actual curtailment, MWh/day")
ax.set_title("Observed + curtailment vs. potential, split by whether the day had a negative price")
ax.set_xlim(0, axis_max_split)
ax.set_ylim(0, axis_max_split)
ax.set_aspect("equal")
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "48_reconstructed_vs_potential_by_price_group.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/48_reconstructed_vs_potential_by_price_group.png
# :name: fig-48-reconstructed-vs-potential-by-price-group
# The same "observed + curtailment vs. potential" scatter from the curtailment-only section above, colour-coded by whether that day had at least one negative-price hour. Negative-price days (red) sit visibly further below `y = x` than ordinary days (blue) -- a first, model-free signal that negative prices carry real information the curtailment-only model is missing.
# ```

# %%
metrics_by_price_group = pd.DataFrame({
    "no_negative_price_day": scatter_metrics(potential_daily[~has_negative_price_daily], reconstructed_daily[~has_negative_price_daily]),
    "has_negative_price_day": scatter_metrics(potential_daily[has_negative_price_daily], reconstructed_daily[has_negative_price_daily]),
})
metrics_by_price_group

# %% [markdown]
# Confirmed numerically: the curtailment-only model's R² against `y = x`
# is 0.89 on the ~83% of days with no negative-price hour, but drops to
# 0.60 on the ~17% of days that had one -- RMSE roughly doubles too
# (~16,800 to ~30,900 MWh/day). Exactly the pattern that would be expected
# if negative prices are a real, separate source of the gap curtailment
# alone doesn't capture, not just noise.

# %% [markdown]
# ## Quantifying the impact
#
# The split above shows *that* negative prices matter; it doesn't say how
# much of a day's gap they typically account for. Rather than bolting on
# another hand-built formula, the natural way to quantify a relationship
# like this is a plain regression: pick an outcome and an explanatory
# variable, and see how strongly, and by how much, one moves with the
# other.
#
# - **Outcome** -- `residual_after_curtailment`: `potential - observed -
#   actual curtailment`, clipped at 0. Whatever's left of the raw gap once
#   real redispatch curtailment is subtracted out. This is the same
#   quantity the curtailment-only section above already plots; it just
#   hasn't been isolated as its own series until now.
# - **Explanatory variable** -- `negative-price exposure`: that day's
#   potential (MWh) summed over just the hours when the price was
#   negative. This measures *opportunity*, not what actually happened --
#   how much production a fully price-responsive operator could have
#   chosen to forgo that day, independent of what was separately curtailed
#   for congestion reasons.
#
# If price-driven curtailment is a real, sizeable effect, days with more
# exposure should have a larger unexplained residual, and a line fit
# through the scatter should have a positive, non-trivial slope: each
# extra MWh of potential exposed to a negative price should show up, at
# least partially, as extra unexplained gap. The slope itself has a direct
# reading -- it's the fraction of "at-risk" potential that typically ends
# up unrealized, on top of whatever curtailment already covers.
#
# One honest caveat before looking at the numbers: negative prices and
# high wind output tend to occur together (oversupply is what drives
# prices negative in the first place), and this project's own offshore
# potential replication was already flagged, in the curtailment-only
# section above, as least trustworthy on exactly those high-output days.
# So a positive slope here is consistent with a real price effect, but it
# can't fully rule out that some of it is the same replication-bias effect
# resurfacing, correlated with the same high-wind days that also happen to
# have negative prices.

# %%
residual_after_curtailment_daily = (implied_loss_daily - offshore_curtailment_daily).clip(lower=0)
negative_price_exposure_daily = inputs["P_wind_off_mw"].where(price < 0, 0.0).resample("D").sum().reindex(daily_range)

slope, intercept = np.polyfit(negative_price_exposure_daily, residual_after_curtailment_daily, 1)
corr = negative_price_exposure_daily.corr(residual_after_curtailment_daily)

fig, ax = plt.subplots(figsize=(7, 6))
ax.scatter(negative_price_exposure_daily, residual_after_curtailment_daily, s=10, alpha=0.35, linewidth=0, color="C2")
fit_x = np.array([0, negative_price_exposure_daily.max()])
ax.plot(fit_x, slope * fit_x + intercept, color="black", linewidth=1.3, label=f"OLS fit: slope = {slope:.2f}")
ax.set_xlabel("Potential during negative-price hours that day, MWh/day (exposure)")
ax.set_ylabel("Gap left unexplained by real curtailment, MWh/day")
ax.set_title(f"Offshore wind, daily: unexplained residual vs. negative-price exposure (r = {corr:.2f}, R² = {corr**2:.2f})")
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "48_residual_vs_negative_price_exposure.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/48_residual_vs_negative_price_exposure.png
# :name: fig-48-residual-vs-negative-price-exposure
# Offshore wind, daily: the curtailment-unexplained residual against negative-price exposure. Each point is one day; days with no negative-price hour at all cluster at x = 0.
# ```

# %% [markdown]
# ## Does a joint model beat curtailment alone?
#
# The two pieces above were checked one at a time. The direct test of
# whether negative-price exposure earns its place *alongside* curtailment,
# rather than as a separate add-on, is a single regression with both as
# predictors -- comparing that regression's fit to the curtailment-only
# version isolates exactly what exposure contributes once curtailment is
# already in the model.

# %%
regression_daily = pd.DataFrame({
    "gap": implied_loss_daily,
    "curtailment": offshore_curtailment_daily,
    "exposure": negative_price_exposure_daily,
}).reindex(daily_range)

model_curtailment_only = smf.ols("gap ~ curtailment", data=regression_daily).fit()
model_curtailment_and_price = smf.ols("gap ~ curtailment + exposure", data=regression_daily).fit()

print(f"gap ~ curtailment                : R² = {model_curtailment_only.rsquared:.3f}")
print(f"gap ~ curtailment + exposure      : R² = {model_curtailment_and_price.rsquared:.3f}")
print(model_curtailment_and_price.params.round(3))

# %% [markdown]
# Adding exposure to the regression raises the gap model's own R² from
# 0.68 to 0.76 -- a real jump, not a rounding difference, from a single
# extra variable. Its coefficient (~0.44) is close to the ~0.43 slope found
# fitting exposure on its own further up, and it's estimated much more
# precisely than chance (p < 0.001) even with curtailment already in the
# model -- exposure isn't just standing in for curtailment.

# %% [markdown]
# ### From the regression back to potential: three models, side by side
#
# Turning this into a reconstructed series takes one more decision: the
# regression above has an intercept (~12,900 MWh/day), representing the
# average gap left over even at zero curtailment and zero exposure. That
# intercept isn't attributable to price -- by definition it's whatever's
# left when exposure is zero -- so folding it into "observed + curtailment
# + price" would credit negative prices with a lift that has nothing to do
# with negative prices, and would add that same lift to *every* day,
# exposed or not. To keep the price contribution honestly isolated, only
# the exposure slope is added back on top of `observed + curtailment`, and
# it's re-fit through the origin (no intercept) so that a day with zero
# exposure gets exactly zero adjustment:
#
# ```
# reconstructed = observed + curtailment + slope * exposure   (slope fit with no intercept)
# ```
#
# Comparing all three reconstructions against potential with the same
# metrics used throughout this chapter shows the same progression from a
# different angle -- the closer this table's numbers get to a perfect
# match (`r = 1`, `R² = 1`, `MAE`/`RMSE = 0`, `sum ratio = 1`), the better.

# %%
exposure_slope_through_origin = (negative_price_exposure_daily * residual_after_curtailment_daily).sum() / (negative_price_exposure_daily**2).sum()
print(f"Exposure slope (through origin): {exposure_slope_through_origin:.3f}")

reconstructed_regression_daily = reconstructed_daily + exposure_slope_through_origin * negative_price_exposure_daily

metrics_comparison["observed_plus_curtailment_plus_price_regression"] = pd.Series(scatter_metrics(potential_daily, reconstructed_regression_daily))
metrics_comparison

# %% [markdown]
# Every metric keeps improving from left to right: R² against `y = x`
# rises from 0.21 (observed alone) to 0.85 (adding curtailment) to 0.90
# (adding the price-exposure term); RMSE drops from ~35,200 to ~19,900 to
# ~16,700 MWh/day; `sum_ratio` climbs from 0.74 to 0.87 to 0.90, closer to
# 1.0 without crossing it in aggregate -- unlike folding in the intercept
# would have produced. On individual high-exposure days the reconstruction
# can still land above potential (nothing forces it not to), but it no
# longer does so systematically across the whole sample the way an
# intercept-based version would.

# %% [markdown]
# ### Zooming in on where the joint model actually helps
#
# Because the price term is now zero whenever that day had no
# negative-price exposure, the two reconstructions only diverge on days
# that actually had one -- late December 2023 is one of the clearest
# stretches of those in the sample.

# %%
fig, ax = plt.subplots(figsize=(13, 4.5))
ax.plot(potential_daily.loc[window_2023].index, potential_daily.loc[window_2023], label="Potential (this project's replication)", linewidth=1.3)
ax.plot(observed_daily.loc[window_2023].index, observed_daily.loc[window_2023], label="Observed (SMARD)", linewidth=1.3)
ax.plot(reconstructed_daily.loc[window_2023].index, reconstructed_daily.loc[window_2023], label="Observed + curtailment", linewidth=1.3)
ax.plot(reconstructed_regression_daily.loc[window_2023].index, reconstructed_regression_daily.loc[window_2023], label="Observed + curtailment + price exposure", linewidth=1.3, linestyle=":")
ax.set_ylabel("MWh / day")
ax.set_title("Offshore wind: potential vs. observed vs. two reconstructions, Nov-Dec 2023")
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "48_joint_model_daily_window.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/48_joint_model_daily_window.png
# :name: fig-48-joint-model-daily-window
# Same Nov-Dec 2023 window used earlier in this chapter. For most of the window the two reconstructions sit exactly on top of each other -- those days had no negative-price hour, so the price term is exactly zero. Around Dec 22-29, which did have real negative-price exposure, the dotted line visibly separates from "observed + curtailment" and moves closer to potential.
# ```

# %% [markdown]
# ## Takeaways
#
# - **Negative prices do carry real signal.** Splitting the curtailment-only
#   model's own fit by whether a day had a negative-price hour shows a
#   materially worse fit on negative-price days (R² against `y = x`: 0.89
#   vs. 0.60; RMSE roughly doubles) -- a model-free result, not dependent
#   on any equation for how price-driven curtailment should work.
# - **The regression puts a number on the effect.** Regressing the
#   curtailment-unexplained residual on negative-price exposure gives a
#   slope of ~0.43 (r = 0.51, R² = 0.26): each extra MWh of potential
#   exposed to a negative price is associated with roughly 0.43 MWh of
#   additional unexplained gap. The fit line's intercept (~12,600 MWh/day)
#   is also informative -- it's the average unexplained residual even on
#   days with *zero* negative-price exposure, i.e. the part of the gap this
#   variable can't touch at all. Both the moderate R² and the sizeable
#   intercept say the same thing as the split test above from a different
#   angle: negative prices are a real, non-trivial piece of the story, not
#   the dominant one.
# - **Exposure earns its place alongside curtailment, not just on its own.**
#   Putting both into one regression raises the gap model's R² from 0.68 to
#   0.76, with exposure's coefficient precisely estimated even after
#   curtailment is already in the model. Turned back into a reconstruction
#   -- adding only the exposure slope, fit through the origin, so days
#   with no exposure get no adjustment -- the three progressively richer
#   models (observed alone, + curtailment, + curtailment and price
#   exposure) improve on every metric in turn (R² against `y = x`: 0.21 ->
#   0.85 -> 0.90; RMSE: ~35,200 -> ~19,900 -> ~16,700 MWh/day; sum_ratio:
#   0.74 -> 0.87 -> 0.90). Unlike a naive intercept-based version, this
#   reconstruction only moves on days that actually had negative-price
#   exposure -- visible directly in the Dec 2023 zoom above.
# - **This isn't the final word.** The exposure variable is deliberately
#   simple (potential during negative-price hours, not accounting for how
#   negative, or interacting with curtailment) and the confounding caveat
#   above still applies -- some of this relationship could be the offshore
#   potential replication's own high-wind bias showing up a second time,
#   not a pure price effect. Both curtailment and negative prices are real,
#   measurable contributors to the gap; what's left over after both is more
#   likely a mix of that replication bias and this simplified model's own
#   blind spots than a further unmeasured real-world loss mechanism.
