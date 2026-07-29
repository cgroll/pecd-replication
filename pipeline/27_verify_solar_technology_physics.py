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
# # Verifying technology- and orientation-aware solar physics
#
# This project's own solar physics baseline (`pecdr/physics.py`'s
# `solar_capacity_factor`, "approach 2") applies one fixed tilt (35 deg)
# and azimuth (south) to every PV installation in Germany, regardless of
# technology, with a generic PVWatts conversion chain. This notebook
# builds and spot-checks a technology- and orientation-aware version
# instead, using each MaStR unit's *actual* reported orientation/tilt
# (`pecdr/solar_orientation.py`) -- finer information than PECD's own
# approach, which only assumes a per-technology distribution rather than
# using real per-plant values -- combined with **PECD v4.2's own
# documented PV conversion chain** end to end (`pecdr/solar_config_physics.py`):
# Skartveit-Olseth (1987) decomposition, Klucher (1979) transposition,
# Martin-Ruiz optical losses, a Beyer et al. (2004) efficiency polynomial,
# Ross (1976) cell temperature, and a Schmidt & Sauer (1994) inverter-loss
# polynomial. Read from PECD's PUG directly (the hosted Confluence version
# truncates before this section for automated fetching).
#
# It also tests PECD's documented **second temporal-downscaling step**
# (hourly GHI/TA -> 15-minute resolution, CF computed at that finer step
# then averaged back to hourly -- `pecdr/temporal_downscaling.py`), run
# alongside the plain-hourly chain for a direct comparison.
#
# Progression against PECD's own NUTS2 x technology CF, each fix on top
# of the last:
#
# | chain | bias | MAE | corr |
# |---|---|---|---|
# | Faiman + Erbs (first pass) | 0.034 | 0.063 | 0.910 |
# | + Ross cell temperature | 0.010 | 0.050 | 0.910 |
# | + PVWatts inverter (self-consumption hypothesis, rejected) | 0.0085 | 0.049 | 0.910 |
# | + Skartveit-Olseth decomposition | 0.0083 | 0.048 | 0.921 |
# | + full PECD-documented chain, inverter polynomial omitted | 0.026 | 0.053 | 0.934 |
# | **+ 15-min temporal downscaling (this pass, tested, not adopted)** | see below | | |
#
# Following the same sequencing wind used (two snapshot hours checked
# against PECD's own product in `09_replicate_wind_onshore_capacity_factor`,
# *before* committing to a full year in `10`), this still only covers 3
# representative full days, not the full backtest period.

# %%
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr

from pecdr.era5 import mask_weighted_regional_mean, region_centroids
from pecdr.paths import ProjPaths
from pecdr.pecd_io import open_single_zipped_netcdf
from pecdr.solar_config_physics import solar_capacity_factor_for_config, solar_capacity_factor_for_config_downscaled
from pecdr.solar_orientation import expand_orientation

paths = ProjPaths()
paths.ensure_directories()

SELECTED_DAYS = ["2020-01-15", "2020-04-15", "2020-06-15"]

# %% [markdown]
# ## NUTS2 region centroids (mask-weighted), for per-region solar position

# %%
mask = open_single_zipped_netcdf(paths.nuts2_mask_zip)["mask"]
de_regions = sorted(r for r in mask.region.values.tolist() if str(r).startswith("DE"))
mask_de = mask.sel(region=de_regions)
centroids = region_centroids(mask_de)

# %% [markdown]
# ## For each selected day: region weather, active-fleet configs, and modeled CF
#
# Each region's fleet is filtered to units active *as of that specific
# day* (not today's fleet), same vintage-correctness principle as wind's
# per-year plant panels.

# %%
unit_panel = pd.read_parquet(paths.solar_unit_technology_file)

modeled_parts = []
for day in SELECTED_DAYS:
    day_ts = pd.Timestamp(day)
    month_str = f"{day_ts.year}-{day_ts.month:02d}"
    era5 = xr.open_dataset(paths.era5_month_file(month_str))
    day_era5 = era5.sel(time=slice(f"{day}T00:00", f"{day}T23:00"))
    # One extra leading hour, needed as an interpolation anchor by the
    # downscaled chain -- see solar_capacity_factor_for_config_downscaled.
    anchor_era5 = era5.sel(time=slice(f"{day_ts - pd.Timedelta(hours=1):%Y-%m-%dT%H:%M}", f"{day}T23:00"))

    ghi_grid = day_era5["surface_solar_radiation_downwards"] / 3600
    temp_grid = day_era5["2m_temperature"] - 273.15
    ghi_region = mask_weighted_regional_mean(ghi_grid, mask_de)
    temp_region = mask_weighted_regional_mean(temp_grid, mask_de)

    ghi_grid_anchor = anchor_era5["surface_solar_radiation_downwards"] / 3600
    temp_grid_anchor = anchor_era5["2m_temperature"] - 273.15
    ghi_region_anchor = mask_weighted_regional_mean(ghi_grid_anchor, mask_de)
    temp_region_anchor = mask_weighted_regional_mean(temp_grid_anchor, mask_de)
    era5.close()

    is_active = (unit_panel["commissioning_date"] <= day_ts) & (unit_panel["final_shutdown_date"].isna() | (unit_panel["final_shutdown_date"] > day_ts))
    configs = expand_orientation(unit_panel.loc[is_active])
    configs = configs[configs["capacity_mw"] > 0]
    print(f"{day}: {len(configs):,} (region, technology, orientation) configs, {configs['capacity_mw'].sum():,.0f} MW total")

    for (region, tech), group in configs.groupby(["nuts2_region", "pecd_technology"], observed=True):
        if region not in ghi_region.columns:
            continue
        total_capacity = group["capacity_mw"].sum()
        weighted_cf = pd.Series(0.0, index=ghi_region.index)
        weighted_cf_downscaled = pd.Series(0.0, index=ghi_region.index)
        lat, lon = centroids.loc[region, "lat"], centroids.loc[region, "lon"]
        for row in group.itertuples():
            cf = solar_capacity_factor_for_config(
                ghi_region[region], temp_region[region],
                lat=lat, lon=lon,
                tilt_deg=row.tilt_deg, azimuth_deg=row.azimuth_deg, is_tracked=row.is_tracked,
            )
            cf_downscaled = solar_capacity_factor_for_config_downscaled(
                ghi_region_anchor[region], temp_region_anchor[region],
                lat=lat, lon=lon,
                tilt_deg=row.tilt_deg, azimuth_deg=row.azimuth_deg, is_tracked=row.is_tracked,
            )
            weighted_cf = weighted_cf + cf * row.capacity_mw
            weighted_cf_downscaled = weighted_cf_downscaled + cf_downscaled * row.capacity_mw
        weighted_cf = weighted_cf / total_capacity
        weighted_cf_downscaled = weighted_cf_downscaled / total_capacity
        modeled_parts.append(pd.DataFrame({
            "timestamp": weighted_cf.index,
            "modeled_cf": weighted_cf.to_numpy(),
            "modeled_cf_downscaled": weighted_cf_downscaled.to_numpy(),
            "nuts2_region": region,
            "pecd_technology": tech,
        }))

modeled = pd.concat(modeled_parts, ignore_index=True)
print(f"\nTotal (region, technology, hour) rows modeled: {len(modeled):,}")

# %% [markdown]
# ## Compare against PECD's own NUTS2 x technology capacity factor

# %%
pecd_solar_cf = pd.read_parquet(paths.pecd_solar_capacity_factors_file)
selected_timestamps = modeled["timestamp"].unique()
pecd_selected = pecd_solar_cf.loc[selected_timestamps].copy()
pecd_selected.columns = [f"{tech}||{region}" for tech, region in pecd_selected.columns]
pecd_long = pecd_selected.reset_index().melt(id_vars="timestamp", var_name="tech_region", value_name="pecd_cf")
pecd_long[["pecd_technology", "nuts2_region"]] = pecd_long["tech_region"].str.split("||", n=1, expand=True, regex=False)
pecd_long = pecd_long.drop(columns="tech_region")

comparison = modeled.merge(pecd_long, on=["timestamp", "nuts2_region", "pecd_technology"], how="inner")
comparison["diff"] = comparison["modeled_cf"] - comparison["pecd_cf"]
comparison["diff_downscaled"] = comparison["modeled_cf_downscaled"] - comparison["pecd_cf"]

print(f"Hours compared: {len(comparison):,}")
print(f"Hourly (no downscaling):   bias: {comparison['diff'].mean():.4f}, MAE: {comparison['diff'].abs().mean():.4f}, corr: {comparison['modeled_cf'].corr(comparison['pecd_cf']):.4f}")
print(f"15-min downscaled+averaged: bias: {comparison['diff_downscaled'].mean():.4f}, MAE: {comparison['diff_downscaled'].abs().mean():.4f}, corr: {comparison['modeled_cf_downscaled'].corr(comparison['pecd_cf']):.4f}")
print("(Previous best, no downscaling: bias=0.026, MAE=0.053, corr=0.934)")

stats_by_tech = comparison.groupby("pecd_technology").apply(
    lambda g: pd.Series({
        "bias": g["diff"].mean(), "mae": g["diff"].abs().mean(), "corr": g["modeled_cf"].corr(g["pecd_cf"]),
        "bias_downscaled": g["diff_downscaled"].mean(), "mae_downscaled": g["diff_downscaled"].abs().mean(), "corr_downscaled": g["modeled_cf_downscaled"].corr(g["pecd_cf"]),
        "n": len(g),
    }),
    include_groups=False,
)
stats_by_tech

# %% [markdown]
# ## Pooled scatter, all regions x technologies x hours, 3 selected days

# %%
fig, axes = plt.subplots(1, 2, figsize=(11, 5.5), sharex=True, sharey=True)
lims = [0, max(comparison["pecd_cf"].max(), comparison["modeled_cf"].max(), comparison["modeled_cf_downscaled"].max())]
for ax, col, diff_col, title in zip(
    axes,
    ["modeled_cf", "modeled_cf_downscaled"],
    ["diff", "diff_downscaled"],
    ["Hourly (no downscaling)", "15-min downscaled + averaged"],
):
    ax.scatter(comparison["pecd_cf"], comparison[col], s=4, alpha=0.2)
    ax.plot(lims, lims, "k--", alpha=0.5, label="1:1")
    ax.set_xlabel("PECD NUTS2 x technology CF")
    ax.set_title(f"{title}\nMAE={comparison[diff_col].abs().mean():.3f}, corr={comparison[col].corr(comparison['pecd_cf']):.3f}")
    ax.legend()
axes[0].set_ylabel("Modeled (PECD-documented chain) CF")
fig.suptitle("3 selected days, all regions x technologies")
fig.tight_layout()
fig.savefig(paths.images_path / "27_solar_physics_verification_scatter.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/27_solar_physics_verification_scatter.png
# :name: fig-27-solar-physics-verification-scatter
# Modeled (PECD-documented chain) vs. PECD's own NUTS2 x technology capacity factor, 3 selected days.
# ```

# %% [markdown]
# ## Time series for a few representative (region, technology) combinations

# %%
example_combos = [("DE30", "61"), ("DE30", "60"), ("DE94", "62")]
fig, axes = plt.subplots(len(example_combos), 1, figsize=(11, 3 * len(example_combos)), sharex=False)
for ax, (region, tech) in zip(np.atleast_1d(axes), example_combos):
    sub = comparison[(comparison["nuts2_region"] == region) & (comparison["pecd_technology"] == tech)].sort_values("timestamp")
    if sub.empty:
        ax.set_title(f"{region}, tech {tech}: no data")
        continue
    ax.plot(sub["timestamp"], sub["modeled_cf"], label="Modeled (hourly)", marker="o", markersize=3)
    ax.plot(sub["timestamp"], sub["modeled_cf_downscaled"], label="Modeled (15-min downscaled)", marker="o", markersize=3)
    ax.plot(sub["timestamp"], sub["pecd_cf"], label="PECD", marker="o", markersize=3)
    ax.set_title(f"{region}, technology {tech}")
    ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "27_solar_physics_verification_timeseries.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/27_solar_physics_verification_timeseries.png
# :name: fig-27-solar-physics-verification-timeseries
# Modeled vs. PECD CF, example (region, technology) combinations, 3 selected days.
# ```

# %% [markdown]
# ## Takeaways
#
# Full progression against PECD's own NUTS2 x technology CF, each step
# built on the last:
#
# | chain | bias | MAE | corr |
# |---|---|---|---|
# | Faiman + Erbs (first pass, generic) | 0.034 | 0.063 | 0.910 |
# | + Ross cell temperature (PECD's documented model) | 0.010 | 0.050 | 0.910 |
# | + PVWatts inverter (self-consumption hypothesis, rejected) | 0.0085 | 0.049 | 0.910 |
# | + Skartveit-Olseth decomposition (PECD's documented model) | 0.0083 | 0.048 | 0.921 |
# | + full PECD chain incl. Schmidt inverter polynomial | -0.049 | 0.062 | 0.884 |
# | **+ full PECD chain, inverter polynomial omitted** | **0.026** | **0.053** | **0.934** |
#
# The last row is this project's current best. Getting PECD's own PUG
# (not just the truncated hosted version) unlocked exact, verbatim
# equations and coefficients for the whole chain -- decomposition
# (Skartveit-Olseth 1987), transposition (Klucher 1979 for sky diffuse, a
# specific fixed-albedo ground-reflected term), optical losses
# (Martin-Ruiz, a component this replication had none of before), module
# efficiency (a 5-coefficient Beyer et al. 2004 polynomial, replacing the
# generic PVWatts DC model), and cell temperature (Ross, confirmed as the
# *same* coefficient for rooftop and utility-scale, not the per-technology
# fit this project assumed before finding the documentation).
#
# One piece doesn't work: PECD's documented inverter-loss polynomial
# (Schmidt & Sauer, 1994), applied exactly as written and verified against
# the raw LaTeX source, behaves like roughly CF*^2 across the operating
# range -- a ~50% loss at half load, far more than any real inverter --
# and makes the match against PECD's own product markedly *worse* (corr
# 0.921 -> 0.884). Dividing instead of multiplying is far worse still. Not
# resolved; omitted rather than silently forced to agree, and flagged in
# `pecdr/solar_config_physics.py` for anyone revisiting it.
#
# Correlation (0.934) is meaningfully better than every prior attempt but
# still short of wind's own-physics-vs-PECD validation (0.99+, full year).
# The remaining gap is most visible as the same cluster from every earlier
# pass -- hours where PECD reads near 0 while this replication reads up to
# ~0.2 -- now smaller but not gone.
#
# ## Temporal downscaling: tested, not adopted
#
# PECD's documented "two-step temporal downscaling" was the other open
# candidate for this gap. Its *first* step (3-hourly -> hourly, via a
# clearness-index conversion) only applies to the climate-projections
# stream -- this project's ERA5 source is already hourly, so it's not
# applicable here. Its *second* step -- hourly GHI/TA interpolated to
# 15-minute resolution, CF computed at that finer step, then averaged
# back to hourly, applicable to "both historical and projected datasets"
# per the PUG -- was implemented (`pecdr/temporal_downscaling.py`) and run
# side by side with the plain-hourly chain above.
#
# | chain | bias | MAE | corr |
# |---|---|---|---|
# | Hourly (no downscaling) | 0.026 | 0.053 | 0.934 |
# | **+ 15-min downscaling** | 0.025 | 0.055 | 0.929 |
#
# Essentially no change, and per-technology it's a wash to very slightly
# worse across all four (see `stats_by_tech` above). It also doesn't fix
# the near-0-PECD-CF overshoot cluster that motivated trying it: in that
# specific band (PECD CF < 0.02, hourly-modeled CF > 0.05, n=227), mean
# modeled CF *rises* from 0.110 to 0.121 with downscaling -- moving
# further from, not closer to, PECD's near-zero readings.
#
# One implementation pitfall worth flagging for anyone revisiting this:
# the first version of this downscaling divided GHI by TOA irradiance
# sampled *instantaneously* at each hourly timestamp to build the
# clearness index -- but ERA5's hourly GHI is a backward-looking *mean*
# over the preceding hour. Whenever apparent sunset fell inside that
# hour but before its end (e.g. DE30, 2020-01-15, the hour ending 16:00:
# mean GHI 1.5 W/m2, but instantaneous TOA exactly 0 at 16:00), the
# instantaneous-TOA denominator was 0 and the entire hour's reconstructed
# GHI was spuriously zeroed. That version made the match against PECD
# markedly worse (corr 0.930 -> 0.883). Averaging TOA over the same
# (t-1h, t] window as the GHI value it divides -- matching conventions
# instead of mixing an instantaneous sample with an hourly mean --
# resolved the artifact and produced the neutral result above.
#
# So: this replication's ~0.930 correlation ceiling isn't explained by
# missing temporal downscaling. The inverter-loss discrepancy (previous
# section) remains the one open documented-but-unreconciled piece of the
# chain, and is the more likely place to look next -- alongside anything
# not documented in the PUG at all.
