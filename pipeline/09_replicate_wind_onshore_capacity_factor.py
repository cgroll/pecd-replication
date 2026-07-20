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
# # Wind-onshore capacity factor replication: PEON zone comparison
#
# The full chain, end to end, for two snapshot hours: bias-corrected 100m
# wind speed (milestone 1) -> hub-height extrapolation via PECD's own alpha
# grid -> per-plant power curve (matched public OEDB curve, or a generic
# specific-power-parametrized curve for the ~56% of MaStR's onshore fleet
# with no exact match) -> simplified probabilistic storm-shutoff derate ->
# flat 10% "other losses" derate -> capacity-weighted aggregation to PEON
# zone -> compared against PECD's own published PEON zone capacity factor.
#
# Deliberate simplifications vs. PECD's own methodology (see project
# discussion and `pecdr/power_curve.py`/`pecdr/shutdown.py` docstrings):
# no intra-farm wake modeling, no per-turbine storm-cutoff database, no
# turbine-level hysteresis state.

# %%
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr

from pecdr.domain import SNAPSHOT_TIMESTAMPS, SNAPSHOT_YEAR
from pecdr.hub_height import alpha_for_timestamp, extrapolate_to_hub_height
from pecdr.paths import ProjPaths
from pecdr.pecd_io import load_region_timeseries_zip, open_single_zipped_netcdf
from pecdr.plant_model import load_plants_with_curves, plant_capacity_factor
from pecdr.power_curve import OTHER_LOSSES_FRACTION
from pecdr.shutdown import apply_shutdown_derate
from pecdr.wind_bias import apply_delta_correction, delta_correction, raw_wind_speed

paths = ProjPaths()
paths.ensure_directories()
snapshot_times = pd.to_datetime(SNAPSHOT_TIMESTAMPS)

# %% [markdown]
# ## Load the plant panel and build each plant's power curve

# %%
plants, curve_cache = load_plants_with_curves(paths)
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

peon_cf = load_region_timeseries_zip(paths.pecd_peon_capacity_factor_zip(SNAPSHOT_YEAR))

comparison_rows = []
zone_detail_rows = []
for ts in snapshot_times:
    raw_speed_100 = raw_wind_speed(raw_era5["u100"], raw_era5["v100"]).sel(valid_time=ts, method="nearest")
    v100 = apply_delta_correction(raw_speed_100, delta_100)
    alpha = alpha_for_timestamp(alpha_ds, ts).reindex_like(v100, method="nearest", tolerance=0.01)

    v100_at_plant = v100.sel(latitude=plant_lat, longitude=plant_lon, method="nearest").to_numpy()
    alpha_at_plant = alpha.sel(latitude=plant_lat, longitude=plant_lon, method="nearest").to_numpy()
    v_hub = v100_at_plant * (plant_hub_height / 100) ** alpha_at_plant

    cf = plant_capacity_factor(v_hub, plants["matched_type"], plants["rated_wind_speed_ms"], curve_cache)
    cf = apply_shutdown_derate(cf, v_hub)
    cf = cf * (1 - OTHER_LOSSES_FRACTION)

    plants_ts = plants.assign(wind_speed_hub_ms=v_hub, capacity_factor=cf, power_output_mw=cf * plants["capacity_mw"])
    zone_agg = plants_ts.groupby("peon_zone").apply(
        lambda g: pd.Series({"modeled_cf": g["power_output_mw"].sum() / g["capacity_mw"].sum(), "capacity_mw": g["capacity_mw"].sum()}),
        include_groups=False,
    )
    zone_agg["pecd_cf"] = peon_cf.loc[peon_cf.index.asof(ts), zone_agg.index]
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
# ## Modeled vs. PECD's own PEON zone capacity factor

# %%
fig, axes = plt.subplots(1, len(snapshot_times), figsize=(6 * len(snapshot_times), 5))
for ax, ts in zip(np.atleast_1d(axes), snapshot_times):
    sub = zone_detail[zone_detail["timestamp"] == ts]
    ax.scatter(sub["pecd_cf"], sub["modeled_cf"])
    for _, row in sub.iterrows():
        ax.annotate(row["peon_zone"], (row["pecd_cf"], row["modeled_cf"]))
    lims = [0, 1]
    ax.plot(lims, lims, "k--", alpha=0.5, label="1:1")
    ax.set_xlabel("PECD PEON zone CF")
    ax.set_ylabel("Our modeled PEON zone CF")
    ax.set_title(f"{ts:%Y-%m-%d %H:%M} UTC")
    ax.set_xlim(lims)
    ax.set_ylim(lims)
    ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "09_peon_zone_comparison.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/09_peon_zone_comparison.png
# :name: fig-09-peon-zone-comparison
# Modeled vs. PECD's own PEON zone wind-onshore capacity factor, both snapshot hours.
# ```

# %% [markdown]
# ## National (Germany-wide) aggregate
#
# PECD publishes no NUTS0/country-level series for wind onshore (confirmed
# via the CDS API constraints: `technology=30`/`resource_grade_b` only ever
# offers `spatial_resolution` `peon`/`p2on`) and never publishes absolute
# output (MW), only capacity factor -- so there is no ready-made "PECD
# national number" to compare against. Both sides of this comparison are
# therefore built the same way, from the already-computed zone-level table:
# a capacity-weighted average of the 7 PEON zones, using **our own MaStR
# zone capacities as the weights on both sides** (`dhf.pecd.national_capacity_weighted_cf`'s
# pattern in ~/research/delu-headline-forecast). Using identical weights on
# both sides isolates "how good are the modeled capacity factors" from "how
# good is the capacity weighting" -- only the CF values differ between the
# two.
#
# This is Germany-only, not DE-LU: both PECD's PEON zones and MaStR exclude
# Luxembourg. Only matters if this is later compared against a DE-LU-labeled
# series (e.g. SMARD), not for this PECD-vs-our-model comparison.

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
ax.set_ylabel("Germany-wide onshore wind capacity factor")
ax.set_title("National aggregate: our model vs. PECD-zone-implied")
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "09_national_aggregate_comparison.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/09_national_aggregate_comparison.png
# :name: fig-09-national-aggregate-comparison
# Germany-wide onshore wind capacity factor: our modeled aggregate vs. PECD-zone-implied aggregate, both using the same MaStR capacity weights.
# ```
