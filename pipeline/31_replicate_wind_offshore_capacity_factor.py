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
# # Wind-offshore capacity factor replication: PEOF zone comparison
#
# Same chain as the onshore replication
# (`09_replicate_wind_onshore_capacity_factor`): bias-corrected 100m wind
# speed -> hub-height extrapolation via PECD's own alpha grid -> per-plant
# power curve -> simplified probabilistic storm-shutoff derate -> flat 10%
# "other losses" derate -> capacity-weighted aggregation to PEOF zone ->
# compared against PECD's own published PEOF zone capacity factor.
#
# One deliberate difference from onshore: GWA2, PECD's own bias-correction
# reference, excludes "offshore areas beyond 20 km" (per the PUG). Checked
# empirically against MaStR's actual offshore turbine coordinates: **91% of
# installed German offshore capacity** sits at grid cells with no GWA2
# delta factor at all. Cross-checked against PECD's own downloaded
# bias-adjusted wind-speed snapshot vs. raw ERA5 at those same deep-sea
# cells: the ratio is ~1.0000 beyond ~20km from shore (real correction only
# applies near-shore) -- i.e. PECD's own product evidently leaves
# deep-offshore wind speed uncorrected. `pecdr.wind_bias.apply_delta_correction`'s
# `fill_value=1.0` replicates that: apply the GWA delta where available,
# leave raw ERA5 speed unmodified elsewhere.
#
# Ground truth comes straight from `pecd_wind_offshore_capacity_factors_file`
# (pipeline/17's multi-year processed PEOF product) rather than a dedicated
# snapshot-only download -- it already covers both snapshot hours (both in
# 2020), unlike onshore's PEON ground truth, which needed its own
# `pipeline/07` download.
#
# Same simplifications as onshore, **except one**: `pecdr.shutdown`'s
# storm-shutdown ramp (linear derate 20->25 m/s) is *not* applied here.
# It's tuned against the onshore fleet, where hub-height wind speed rarely
# exceeds 20 m/s; offshore it regularly does (checked: ~3.8% of hours at a
# representative North Sea cell across 2022 fall in that 20-25 m/s band,
# vs. essentially never onshore). Applied as-is it derates the January
# snapshot below by ~75% at a moment PECD's own product stays near full
# output -- the pre-shutdown power curve alone already tracks PECD's
# product closely there (0.91 vs. PECD's 0.86), so the ramp is doing net
# harm, not good, exactly like the solar inverter-loss polynomial
# (`pecdr/solar_config_physics.py`'s `INVERTER_COEFS`): implemented
# elsewhere, deliberately not applied here, discrepancy left visible rather
# than silently patched with an unvalidated offshore-specific threshold.

# %%
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr

from pecdr.domain import SNAPSHOT_TIMESTAMPS, SNAPSHOT_YEAR
from pecdr.hub_height import alpha_for_timestamp
from pecdr.paths import ProjPaths
from pecdr.pecd_io import open_single_zipped_netcdf
from pecdr.plant_model import load_plants_with_curves, plant_capacity_factor
from pecdr.power_curve import OTHER_LOSSES_FRACTION
from pecdr.wind_bias import apply_delta_correction, delta_correction, raw_wind_speed

paths = ProjPaths()
paths.ensure_directories()
snapshot_times = pd.to_datetime(SNAPSHOT_TIMESTAMPS)

# %% [markdown]
# ## Load the plant panel and build each plant's power curve

# %%
plant_panel = pd.read_parquet(paths.wind_offshore_plant_panel_file)
plants, curve_cache = load_plants_with_curves(paths, plant_panel=plant_panel)
print(f"Plants with complete technical detail: {len(plants):,} ({plants['capacity_mw'].sum():,.0f} MW)")
match_rate = plants.loc[plants["matched_type"].notna(), "capacity_mw"].sum() / plants["capacity_mw"].sum()
print(f"Capacity-weighted OEDB match rate: {match_rate * 100:.1f}%")

# %% [markdown]
# ## Per-plant wind speed at hub height, per snapshot hour

# %%
raw_era5 = xr.open_dataset(paths.era5_wind_snapshots_file)
era5_clim_100 = open_single_zipped_netcdf(paths.wind_bias_reference_zip("climatology_era5_100m"))
gwa2_clim_100 = open_single_zipped_netcdf(paths.wind_bias_reference_zip("climatology_gwa2_100m"))
delta_100 = delta_correction(era5_clim_100, gwa2_clim_100)
alpha_ds = open_single_zipped_netcdf(paths.wind_bias_reference_zip("power_law_coefficient"))

plant_lat = xr.DataArray(plants["grid_lat"].to_numpy(), dims="plant")
plant_lon = xr.DataArray(plants["grid_lon"].to_numpy(), dims="plant")
plant_hub_height = plants["hub_height_m"].to_numpy()

peof_cf = pd.read_parquet(paths.pecd_wind_offshore_capacity_factors_file)

comparison_rows = []
zone_detail_rows = []
for ts in snapshot_times:
    raw_speed_100 = raw_wind_speed(raw_era5["u100"], raw_era5["v100"]).sel(valid_time=ts, method="nearest")
    v100 = apply_delta_correction(raw_speed_100, delta_100, fill_value=1.0)
    alpha = alpha_for_timestamp(alpha_ds, ts).reindex_like(v100, method="nearest", tolerance=0.01)

    v100_at_plant = v100.sel(latitude=plant_lat, longitude=plant_lon, method="nearest").to_numpy()
    alpha_at_plant = alpha.sel(latitude=plant_lat, longitude=plant_lon, method="nearest").to_numpy()
    v_hub = v100_at_plant * (plant_hub_height / 100) ** alpha_at_plant

    cf = plant_capacity_factor(v_hub, plants["matched_type"], plants["rated_wind_speed_ms"], curve_cache)
    cf = cf * (1 - OTHER_LOSSES_FRACTION)

    plants_ts = plants.assign(wind_speed_hub_ms=v_hub, capacity_factor=cf, power_output_mw=cf * plants["capacity_mw"])
    zone_agg = plants_ts.groupby("peof_zone").apply(
        lambda g: pd.Series({"modeled_cf": g["power_output_mw"].sum() / g["capacity_mw"].sum(), "capacity_mw": g["capacity_mw"].sum()}),
        include_groups=False,
    )
    zone_agg["pecd_cf"] = peof_cf.loc[peof_cf.index.asof(ts), zone_agg.index]
    zone_agg["timestamp"] = ts
    zone_detail_rows.append(zone_agg.reset_index())

    diff = zone_agg["modeled_cf"] - zone_agg["pecd_cf"]
    comparison_rows.append({
        "timestamp": ts,
        "mae": float(diff.abs().mean()),
        "bias": float(diff.mean()),
        "corr": float(zone_agg["modeled_cf"].corr(zone_agg["pecd_cf"])),
    })

zone_detail = pd.concat(zone_detail_rows, ignore_index=True)
summary = pd.DataFrame(comparison_rows)
zone_detail

# %%
summary

# %% [markdown]
# ## Modeled vs. PECD's own PEOF zone capacity factor

# %%
fig, axes = plt.subplots(1, len(snapshot_times), figsize=(6 * len(snapshot_times), 5))
for ax, ts in zip(np.atleast_1d(axes), snapshot_times):
    sub = zone_detail[zone_detail["timestamp"] == ts]
    ax.scatter(sub["pecd_cf"], sub["modeled_cf"])
    for _, row in sub.iterrows():
        ax.annotate(row["peof_zone"], (row["pecd_cf"], row["modeled_cf"]))
    lims = [0, 1]
    ax.plot(lims, lims, "k--", alpha=0.5, label="1:1")
    ax.set_xlabel("PECD PEOF zone CF")
    ax.set_ylabel("Our modeled PEOF zone CF")
    ax.set_title(f"{ts:%Y-%m-%d %H:%M} UTC")
    ax.set_xlim(lims)
    ax.set_ylim(lims)
    ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "31_peof_zone_comparison.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/31_peof_zone_comparison.png
# :name: fig-31-peof-zone-comparison
# Modeled vs. PECD's own PEOF zone wind-offshore capacity factor, both snapshot hours.
# ```

# %% [markdown]
# ## National (Germany-wide) aggregate
#
# Same pattern as onshore's step 4: PECD publishes no NUTS0/country-level
# series for wind offshore either, so both sides of this comparison are
# built the same way from the already-computed zone-level table, using
# **our own MaStR zone capacities as the weights on both sides** -- this
# isolates "how good are the modeled capacity factors" from "how good is
# the capacity weighting."

# %%
def capacity_weighted_mean(group: pd.DataFrame, value_col: str) -> float:
    return (group[value_col] * group["capacity_mw"]).sum() / group["capacity_mw"].sum()


national_rows = []
for ts, group in zone_detail.groupby("timestamp"):
    national_rows.append({
        "timestamp": ts,
        "our_national_cf": capacity_weighted_mean(group, "modeled_cf"),
        "pecd_implied_national_cf": capacity_weighted_mean(group, "pecd_cf"),
        "total_capacity_mw": group["capacity_mw"].sum(),
    })
national = pd.DataFrame(national_rows)
national["diff"] = national["our_national_cf"] - national["pecd_implied_national_cf"]
national["rel_diff_pct"] = national["diff"] / national["pecd_implied_national_cf"] * 100
national

# %%
fig, ax = plt.subplots(figsize=(7, 5))
width = 0.35
x = np.arange(len(national))
ax.bar(x - width / 2, national["pecd_implied_national_cf"], width, label="PECD-implied national CF")
ax.bar(x + width / 2, national["our_national_cf"], width, label="Our modeled national CF")
ax.set_xticks(x)
ax.set_xticklabels([f"{ts:%Y-%m-%d %H:%M}" for ts in national["timestamp"]])
ax.set_ylabel("Germany-wide offshore wind capacity factor")
ax.set_title("National aggregate: our model vs. PECD-zone-implied")
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "31_national_aggregate_comparison.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/31_national_aggregate_comparison.png
# :name: fig-31-national-aggregate-comparison
# Germany-wide offshore wind capacity factor: our modeled aggregate vs. PECD-zone-implied aggregate, both using the same MaStR capacity weights.
# ```
