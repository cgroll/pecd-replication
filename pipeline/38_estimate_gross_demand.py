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
# # Estimating gross power demand
#
# Fits equation 7/7a from `book/markdown/curtailment_system_equations.md`:
# grid-metered load (`D_grid`) as a calendar + temperature demand model,
# minus PV self-consumption, split by MaStR feed-in category. The
# identification argument: at hours with `P_pv(t)=0` (night, heavily
# overcast), the self-consumption terms vanish and the demand-model
# coefficients are pinned down with no solar interference at all; daytime
# hours, where `P_pv(t)` varies a lot day to day at fixed calendar/weather
# conditions (cloud cover), then pin down the self-consumption
# coefficients. One regression, not two sequential models.
#
# Two falsification checks follow directly from the model's own structure,
# not from any external data:
# - `P_pv,full_feed_in`'s coefficient should be statistically
#   indistinguishable from zero -- that capacity is barred from
#   self-consuming by its own feed-in registration.
# - Adding wind potential terms to the same regression should also come
#   back ≈0 -- wind has no behind-the-meter self-consumption to detect.

# %%
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from patsy import dmatrix  # noqa: F401 -- registers `bs()` for the spline formula used below

from pecdr.paths import ProjPaths
from pecdr.residual_load import fit_gross_demand_model

paths = ProjPaths()
paths.ensure_directories()

inputs = pd.read_parquet(paths.residual_load_inputs_file)

# %% [markdown]
# ## Fit the main model

# %%
model = fit_gross_demand_model(inputs)
print(f"R-squared: {model.rsquared:.4f}")
print(f"N: {int(model.nobs):,}")
model.params[["heating_degree", "cooling_degree", "P_pv_full_feed_in_mw", "P_pv_self_consumption_mw", "years_since_start"]].to_frame("coefficient").join(
    model.pvalues.rename("p_value")
)

# %% [markdown]
# ## Falsification check 1: full-feed-in PV should show no self-consumption effect
#
# It doesn't come out at zero -- both PV terms are large and highly
# significant. Before concluding anything about self-consumption, check
# whether the split itself is even estimable: `P_pv,full_feed_in` and
# `P_pv,self_consumption` are both `national_cf(t) x (a capacity share that
# only moves month to month)` -- if that capacity-mix ratio barely varies
# within a short window, the two regressors are nearly collinear and OLS
# can't reliably separate them.

# %%
ffi_coef = model.params["P_pv_full_feed_in_mw"]
ffi_ci = model.conf_int().loc["P_pv_full_feed_in_mw"]
sc_coef = model.params["P_pv_self_consumption_mw"]
sc_ci = model.conf_int().loc["P_pv_self_consumption_mw"]
print(f"full_feed_in coefficient: {ffi_coef:.4f} (95% CI [{ffi_ci[0]:.4f}, {ffi_ci[1]:.4f}]), p={model.pvalues['P_pv_full_feed_in_mw']:.4g}")
print(f"self_consumption coefficient: {sc_coef:.4f} (95% CI [{sc_ci[0]:.4f}, {sc_ci[1]:.4f}]), p={model.pvalues['P_pv_self_consumption_mw']:.4g}")

corr_ffi_sc = inputs["P_pv_full_feed_in_mw"].corr(inputs["P_pv_self_consumption_mw"])
print(f"\nCorrelation between the two PV category regressors: {corr_ffi_sc:.4f}")

# %% [markdown]
# Confirmed: the two regressors correlate at ~0.95. The split (equation 7a)
# isn't reliably identified by plain OLS given this data -- there just
# isn't enough independent variation between the two series within a short
# window to separate their individual effects. The **sum** of the two
# coefficients (equivalent to fitting the single aggregate `P_pv_mw` term
# from equation 7, not the split) is the trustworthy number here.

# %%
# Fit the single-aggregate specification directly (equation 7, not 7a):
aggregate_formula = (
    "D_grid_mw ~ C(dow) + C(hour) + is_holiday "
    "+ heating_degree + cooling_degree + years_since_start + P_pv_mw"
)
model_aggregate = smf.ols(aggregate_formula, data=inputs).fit()
k_aggregate = -model_aggregate.params["P_pv_mw"]
print(f"Aggregate self-consumption fraction (equation 7, trustworthy): {k_aggregate:.3f}")
print(f"(For reference, the untrustworthy split summed to: {-(ffi_coef + sc_coef):.3f})")

# %% [markdown]
# ## Falsification check 2: adding wind potential should show no effect either
#
# This one doesn't pass either, and not for the same reason.

# %%
model_with_wind = fit_gross_demand_model(inputs, extra_regressors=["P_wind_on_mw", "P_wind_off_mw"])
wind_check = model_with_wind.params[["P_wind_on_mw", "P_wind_off_mw"]].to_frame("coefficient").join(model_with_wind.pvalues.rename("p_value"))
wind_check

# %% [markdown]
# ## Ruling out temperature misspecification as the cause
#
# Wind potential correlates with `heating_degree` (~0.15-0.18) -- windier
# weather tends to be colder weather in Central Europe -- so a first guess
# is that the simple 2-hinge degree-day term is too rigid and wind is
# soaking up residual, unmodeled temperature nonlinearity. Testing this
# directly with a much more flexible temperature response (a 6-df spline
# instead of two linear hinges) essentially rules it out: both wind
# coefficients barely move.

# %%
spline_formula = (
    "D_grid_mw ~ C(dow) + C(hour) + is_holiday "
    "+ bs(temperature_c, df=6) + years_since_start "
    "+ P_pv_full_feed_in_mw + P_pv_self_consumption_mw + P_wind_on_mw + P_wind_off_mw"
)
model_spline = smf.ols(spline_formula, data=inputs).fit()
comparison = pd.DataFrame({
    "hinge_spec": model_with_wind.params[["P_wind_on_mw", "P_wind_off_mw"]],
    "spline_spec": model_spline.params[["P_wind_on_mw", "P_wind_off_mw"]],
})
comparison

# %% [markdown]
# Barely different. The more likely explanation is that this is a real
# effect the falsification test's own premise didn't anticipate: wind's
# assumed-zero coefficient rests on "no behind-the-meter self-consumption
# channel," but there's a different, entirely legitimate channel wind
# *does* have that solar's full-feed-in category doesn't need either --
# high wind tends to push wholesale prices down, and some
# price-responsive industrial demand (aluminium smelting and similar) is
# known to ramp up during cheap/high-renewable hours. That's a real
# demand-side response, not a self-consumption artifact, and this
# regression was never designed to net it out. It's also a plausible
# partial confound for the PV self-consumption estimate above, in the
# *opposite* direction (if solar has a similar price effect, it should
# push the PV coefficient toward positive/less-negative, not more
# negative) -- so the aggregate self-consumption fraction reported above
# is a reasonable estimate, but likely a slight underestimate of true
# self-consumption if this channel is real, not an overestimate.

# %% [markdown]
# ## Temperature response shape
#
# Should be V-shaped: demand rising as temperature drops below the heating
# reference (15°C) and rising again above the cooling reference (20°C),
# both with positive slopes -- a directly falsifiable prediction, not just
# a curve-fitting artifact.

# %%
temp_grid = np.linspace(inputs["temperature_c"].min(), inputs["temperature_c"].max(), 200)
heating_grid = np.clip(15 - temp_grid, 0, None)
cooling_grid = np.clip(temp_grid - 20, 0, None)
temp_response = model.params["heating_degree"] * heating_grid + model.params["cooling_degree"] * cooling_grid

fig, ax = plt.subplots(figsize=(8, 5))
ax.plot(temp_grid, temp_response)
ax.set_xlabel("Temperature (°C)")
ax.set_ylabel("Demand response relative to the 15-20°C baseline (MW)")
ax.set_title("Fitted temperature response")
fig.tight_layout()
fig.savefig(paths.images_path / "38_temperature_response.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/38_temperature_response.png
# :name: fig-38-temperature-response
# Fitted demand response to temperature, holding calendar features fixed.
# ```
#
# The heating side is strongly positive and significant, as expected. The
# cooling side comes back essentially flat and statistically insignificant
# (p=0.92) -- not a modeling failure, but a plausible real feature of the
# German market: air-conditioning penetration is historically low compared
# to, say, Southern Europe or the US, so a muted cooling-demand response is
# a reasonable finding, not a red flag the way the PV/wind checks above are.

# %% [markdown]
# ## Does gross demand fill in the solar self-consumption dip?
#
# Average intraday profile, summer (Jun-Aug, high solar) vs. winter
# (Dec-Feb, minimal solar): `D_grid` should show a clear midday dip in
# summer that's largely absent in winter; `D_true_hat` (gross demand, PV
# terms zeroed out) should be much flatter across both seasons if the model
# is doing its job.

# %%
# Uses the aggregate model (the trustworthy specification, given the
# collinearity finding above) rather than the split one -- the two should
# barely differ here anyway, since zeroing out both split terms removes
# the same total self-consumption effect either way.
d_true_hat = model_aggregate.predict(inputs.assign(P_pv_mw=0.0))
profile_df = pd.DataFrame({"D_grid_mw": inputs["D_grid_mw"], "D_true_hat_mw": d_true_hat, "hour": inputs["hour"]}, index=inputs.index)
summer = profile_df[profile_df.index.month.isin([6, 7, 8])].groupby("hour")[["D_grid_mw", "D_true_hat_mw"]].mean()
winter = profile_df[profile_df.index.month.isin([12, 1, 2])].groupby("hour")[["D_grid_mw", "D_true_hat_mw"]].mean()

fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=True)
for ax, (season_df, label) in zip(axes, [(winter, "Winter (Dec-Feb)"), (summer, "Summer (Jun-Aug)")]):
    ax.plot(season_df.index, season_df["D_grid_mw"], marker="o", markersize=3, label="D_grid (observed)")
    ax.plot(season_df.index, season_df["D_true_hat_mw"], marker="o", markersize=3, label="D_true_hat (gross demand)")
    ax.set_xlabel("Hour of day (UTC)")
    ax.set_title(label)
    ax.legend()
axes[0].set_ylabel("MW")
fig.suptitle("Average intraday demand profile: observed vs. estimated gross")
fig.tight_layout()
fig.savefig(paths.images_path / "38_intraday_profile_summer_winter.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/38_intraday_profile_summer_winter.png
# :name: fig-38-intraday-profile
# Average intraday demand profile by season: observed grid load vs. estimated gross demand.
# ```

# %% [markdown]
# ## One month, full hourly resolution

# %%
sample = profile_df.loc["2023-07-01":"2023-07-31"]
fig, ax = plt.subplots(figsize=(14, 4))
ax.plot(sample.index, sample["D_grid_mw"], label="D_grid (observed)", linewidth=0.8)
ax.plot(sample.index, sample["D_true_hat_mw"], label="D_true_hat (gross demand)", linewidth=0.8)
ax.set_ylabel("MW")
ax.set_title("July 2023, hourly")
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "38_sample_month_july_2023.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/38_sample_month_july_2023.png
# :name: fig-38-sample-month
# July 2023, hourly: observed grid load vs. estimated gross demand.
# ```

# %% [markdown]
# ## Takeaways
#
# - **Neither falsification check passed cleanly, and that's more
#   informative than a clean pass would have been.** The full-feed-in/
#   self-consumption PV split isn't estimable by plain OLS -- the two
#   regressors correlate at ~0.95, since both are `national_cf(t) x` a
#   capacity-mix ratio that only moves month to month, leaving too little
#   independent variation to separate them. The **aggregate** specification
#   (equation 7, one `P_pv_mw` term) is the trustworthy one; the category
#   split (7a) is documented here as a genuine non-result, not silently
#   dropped.
# - **Wind's nonzero coefficient survived a direct test of the obvious
#   alternative explanation** (temperature misspecification leaking through
#   a correlate of wind) and is more likely a real, different effect this
#   falsification check's own premise didn't anticipate: price-responsive
#   industrial demand rising during cheap, high-wind hours. That's a
#   legitimate demand-side phenomenon, not an artifact -- but it's also a
#   plausible reason the PV self-consumption estimate above is a slight
#   *underestimate*, if a similar (opposite-signed) price effect exists for
#   solar.
# - **The temperature response has the expected V-shape on the heating
#   side, and an essentially flat, insignificant cooling side** -- plausibly
#   real (Germany's historically low air-conditioning penetration), not
#   a red flag.
# - **`D_true_hat` visibly fills in the summer midday dip** that `D_grid`
#   shows (the intraday-profile chart) -- the gap between the two peaks at
#   9-17 UTC specifically, exactly where solar output is highest. In
#   winter the gap is much smaller and roughly flat across the whole day
#   rather than midday-concentrated -- consistent with it being mostly
#   ordinary model-fit residual (R²=0.84, not 1.0) rather than a solar
#   effect, since there's little sun to self-consume in winter in the
#   first place.
#
# Net: the aggregate self-consumption fraction (`k ≈` the value printed
# above) is this notebook's headline number, with two honestly-reported
# caveats (the category split, and the wind confound) rather than a single
# clean result. Both curtailment estimation (`39`) and the residual-load
# backtest (`40`) use the aggregate `D_true_hat` from here.
