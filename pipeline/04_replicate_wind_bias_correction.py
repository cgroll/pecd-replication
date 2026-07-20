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
# # Wind bias-correction replication: milestone 1
#
# The first checkpoint in replicating PECD v4.2's wind methodology: can we
# reproduce PECD's Global Wind Atlas "Delta Adjustment" bias correction on
# raw ERA5 wind speed, at two snapshot hours over Germany's PEON extent?
#
# No plant locations, power curves, or alpha extrapolation are involved yet
# -- purely the bias-correction step in isolation, checked against ground
# truth PECD itself publishes:
#
# - **Inputs**: our own raw ERA5 10m/100m wind speed
#   (`pipeline/03_download_era5_wind_snapshots.py`) and PECD's own
#   ERA5/GWA2 climatology grids (`pipeline/01_download_pecd_wind_bias_reference.py`),
#   from which we recompute PECD's Delta Adjustment factor ourselves
#   (`pecdr/wind_bias.py`).
# - **Ground truth**: PECD's own published bias-corrected 10m/100m wind
#   speed grid (`pipeline/02_download_pecd_wind_speed_snapshots.py`) --
#   confirmed by inspection to genuinely be the post-correction product (its
#   own NetCDF `history` attribute records "Bias adjustment with mean delta
#   method" and "Removed drop at 10 UTC" as already-applied steps).
#
# Not yet replicated (out of scope for this milestone -- see
# `pecdr/wind_bias.py`): capping outliers above 70 m/s, and PECD's ERA5
# 10:00 UTC dip interpolation. Neither snapshot hour is 10:00 UTC or a
# storm event, so this shouldn't matter yet.
#
# **Domain note**: PECD's ERA5/GWA2 climatology grids (used to derive the
# Delta Adjustment factor) are NaN over sea cells -- they're part of the
# onshore-wind-specific bundle, so GWA2 coverage only exists over land.
# PECD's own published wind-speed product has no such gap (it's a general
# climate variable, valid over sea too). Comparisons below are restricted to
# our own field's non-NaN (onshore) footprint on both sides
# (`pecdr.wind_bias.restrict_to_onshore`) so the two are compared over the
# same domain.

# %%
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import xarray as xr

from pecdr.domain import SNAPSHOT_TIMESTAMPS
from pecdr.paths import ProjPaths
from pecdr.pecd_io import open_single_zipped_netcdf
from pecdr.wind_bias import apply_delta_correction, delta_correction, raw_wind_speed, restrict_to_onshore, single_data_var

paths = ProjPaths()
paths.ensure_directories()

HEIGHTS_M = [10, 100]
SNAPSHOT_YEAR = "2020"
snapshot_times = pd.to_datetime(SNAPSHOT_TIMESTAMPS)

# %% [markdown]
# ## Load inputs and compute our own bias-corrected wind speed

# %%
raw_era5 = xr.open_dataset(paths.era5_wind_snapshots_file)

per_height = {}
for height_m in HEIGHTS_M:
    era5_clim = open_single_zipped_netcdf(paths.wind_bias_reference_zip(f"climatology_era5_{height_m}m"))
    gwa2_clim = open_single_zipped_netcdf(paths.wind_bias_reference_zip(f"climatology_gwa2_{height_m}m"))
    delta = delta_correction(era5_clim, gwa2_clim)

    raw_speed = raw_wind_speed(raw_era5[f"u{height_m}"], raw_era5[f"v{height_m}"])
    own_corrected = apply_delta_correction(raw_speed, delta)
    own_corrected.attrs.update(long_name=f"{height_m} metre wind speed (our replication)", units="m s**-1")

    pecd_ds = open_single_zipped_netcdf(paths.pecd_wind_speed_zip(height_m, SNAPSHOT_YEAR))
    pecd_speed = single_data_var(pecd_ds)

    per_height[height_m] = {"delta": delta, "own_corrected": own_corrected, "pecd": pecd_speed}

print("Delta Adjustment factor summary (should be close to 1.0, i.e. a modest correction):")
for height_m, d in per_height.items():
    delta = d["delta"]
    print(f"  {height_m}m: mean={float(delta.mean()):.3f}, min={float(delta.min()):.3f}, max={float(delta.max()):.3f}")

# %% [markdown]
# ## Compare against PECD's own bias-corrected grid, per snapshot hour
#
# Each panel: our replicated correction, PECD's published correction, and
# their difference, at one (height, hour) combination.

# %%
summary_rows = []
for height_m, d in per_height.items():
    for ts in snapshot_times:
        own = d["own_corrected"].sel(valid_time=ts, method="nearest")
        pecd_snap = d["pecd"].sel(time=ts, method="nearest")
        pecd_snap = pecd_snap.reindex_like(own, method="nearest", tolerance=0.01)
        own, pecd_snap = restrict_to_onshore(own, pecd_snap, reference=own)

        diff = own - pecd_snap
        mae = float(np.abs(diff).mean())
        bias = float(diff.mean())
        corr = float(xr.corr(own, pecd_snap))
        summary_rows.append({"height_m": height_m, "timestamp": ts, "own_mean": float(own.mean()), "pecd_mean": float(pecd_snap.mean()), "mae": mae, "bias": bias, "corr": corr})

        fig, axes = plt.subplots(1, 3, figsize=(15, 4))
        own.plot(ax=axes[0], cmap="viridis", vmin=float(min(own.min(), pecd_snap.min())), vmax=float(max(own.max(), pecd_snap.max())))
        axes[0].set_title(f"Our replication ({height_m}m)")
        pecd_snap.plot(ax=axes[1], cmap="viridis", vmin=float(min(own.min(), pecd_snap.min())), vmax=float(max(own.max(), pecd_snap.max())))
        axes[1].set_title(f"PECD ground truth ({height_m}m)")
        diff.plot(ax=axes[2], cmap="RdBu_r", center=0)
        axes[2].set_title(f"Difference (ours - PECD)\nMAE={mae:.3f} m/s, corr={corr:.4f}")
        fig.suptitle(f"{ts:%Y-%m-%d %H:%M} UTC, {height_m}m wind speed")
        fig.tight_layout()
        fname = f"04_bias_correction_{height_m}m_{ts:%Y%m%dT%H%M}.png"
        fig.savefig(paths.images_path / fname, dpi=150, bbox_inches="tight")
        plt.show()

summary = pd.DataFrame(summary_rows)
summary

# %% [markdown]
# ```{figure} ../../output/images/04_bias_correction_10m_20200115T0000.png
# :name: fig-04-bias-correction-10m-jan
# 10m wind speed, our replication vs. PECD ground truth, 2020-01-15 00:00 UTC.
# ```
#
# ```{figure} ../../output/images/04_bias_correction_100m_20200615T1200.png
# :name: fig-04-bias-correction-100m-jun
# 100m wind speed, our replication vs. PECD ground truth, 2020-06-15 12:00 UTC.
# ```

# %% [markdown]
# ## Summary
#
# If MAE is small relative to typical wind speeds (a few m/s) and
# correlation is close to 1, the Delta Adjustment replication is working as
# intended -- the remaining gap would be attributable to the two
# not-yet-replicated preprocessing steps (70 m/s capping, 10 UTC drop fix)
# plus any reference-period/regridding differences in how the climatology
# grids were produced upstream of what we downloaded.
