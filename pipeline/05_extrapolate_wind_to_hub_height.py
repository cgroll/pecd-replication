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
# # Hub-height wind extrapolation
#
# Extends milestone 1 (bias-corrected 10m/100m wind speed, validated against
# PECD's own published grid) with PECD v4.2's precomputed power-law (alpha)
# grid, to extrapolate to arbitrary turbine hub heights.
#
# No PECD ground truth exists for wind speed at heights other than 10m/100m,
# so this can't be checked against a third independent source the way the
# bias correction was. Instead: **internal consistency**. Per the PUG,
# alpha was itself derived from the 10m/100m ratio -- so extrapolating our
# already-validated 100m field back down to 10m via alpha should closely
# reproduce our already-validated 10m field. That's the quantitative check
# here; extrapolation to typical modern turbine hub heights (80-160m) is
# shown for plausibility only (smooth, monotonically-increasing-with-height
# profile, no numeric ground truth).

# %%
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr

from pecdr.domain import SNAPSHOT_TIMESTAMPS
from pecdr.hub_height import alpha_for_timestamp, extrapolate_to_hub_height
from pecdr.paths import ProjPaths
from pecdr.pecd_io import open_single_zipped_netcdf
from pecdr.wind_bias import apply_delta_correction, delta_correction, raw_wind_speed, restrict_to_onshore

paths = ProjPaths()
paths.ensure_directories()

snapshot_times = pd.to_datetime(SNAPSHOT_TIMESTAMPS)
HUB_HEIGHTS_M = [80, 100, 120, 140, 160]  # typical modern onshore turbine range

# %% [markdown]
# ## Rebuild milestone 1's bias-corrected 10m/100m fields

# %%
raw_era5 = xr.open_dataset(paths.era5_wind_snapshots_file)

corrected = {}
for height_m in [10, 100]:
    era5_clim = open_single_zipped_netcdf(paths.wind_bias_reference_zip(f"climatology_era5_{height_m}m"))
    gwa2_clim = open_single_zipped_netcdf(paths.wind_bias_reference_zip(f"climatology_gwa2_{height_m}m"))
    delta = delta_correction(era5_clim, gwa2_clim)
    raw_speed = raw_wind_speed(raw_era5[f"u{height_m}"], raw_era5[f"v{height_m}"])
    corrected[height_m] = apply_delta_correction(raw_speed, delta)

alpha_ds = open_single_zipped_netcdf(paths.wind_bias_reference_zip("power_law_coefficient"))

# %% [markdown]
# ## Internal consistency: 100m -> 10m via alpha vs. our validated 10m field

# %%
consistency_rows = []
for ts in snapshot_times:
    v100 = corrected[100].sel(valid_time=ts, method="nearest")
    v10_actual = corrected[10].sel(valid_time=ts, method="nearest")
    alpha = alpha_for_timestamp(alpha_ds, ts)

    v10_reconstructed = extrapolate_to_hub_height(v100, alpha, ref_height_m=100, hub_height_m=10)
    v10_reconstructed, v10_actual_masked = restrict_to_onshore(v10_reconstructed, v10_actual, reference=v10_reconstructed)

    diff = v10_reconstructed - v10_actual_masked
    mae = float(np.abs(diff).mean())
    corr = float(xr.corr(v10_reconstructed, v10_actual_masked))
    consistency_rows.append({"timestamp": ts, "reconstructed_10m_mean": float(v10_reconstructed.mean()), "actual_10m_mean": float(v10_actual_masked.mean()), "mae": mae, "corr": corr})

    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    v10_reconstructed.plot(ax=axes[0], cmap="viridis")
    axes[0].set_title("100m -> 10m via alpha")
    v10_actual_masked.plot(ax=axes[1], cmap="viridis")
    axes[1].set_title("Our validated 10m field")
    diff.plot(ax=axes[2], cmap="RdBu_r", center=0)
    axes[2].set_title(f"Difference\nMAE={mae:.3f} m/s, corr={corr:.4f}")
    fig.suptitle(f"Alpha internal-consistency check, {ts:%Y-%m-%d %H:%M} UTC")
    fig.tight_layout()
    fname = f"05_alpha_consistency_{ts:%Y%m%dT%H%M}.png"
    fig.savefig(paths.images_path / fname, dpi=150, bbox_inches="tight")
    plt.show()

consistency = pd.DataFrame(consistency_rows)
consistency

# %% [markdown]
# ```{figure} ../../output/images/05_alpha_consistency_20200115T0000.png
# :name: fig-05-alpha-consistency-jan
# Alpha internal-consistency check, 2020-01-15 00:00 UTC.
# ```

# %% [markdown]
# ## Extrapolation to typical turbine hub heights (plausibility only)
#
# Domain-mean wind speed vs. height, for each snapshot hour -- expected to
# be smooth and monotonically increasing (typical daytime/summer boundary
# layer) or occasionally near-flat/decreasing under a stable nocturnal
# inversion, per the PUG's description of alpha's diurnal/seasonal range.

# %%
fig, ax = plt.subplots(figsize=(8, 5))
for ts in snapshot_times:
    v100 = corrected[100].sel(valid_time=ts, method="nearest")
    alpha = alpha_for_timestamp(alpha_ds, ts)
    v100_masked, alpha_masked = restrict_to_onshore(v100, alpha.reindex_like(v100, method="nearest", tolerance=0.01), reference=v100)

    means = []
    for h in HUB_HEIGHTS_M:
        v_h = extrapolate_to_hub_height(v100_masked, alpha_masked, ref_height_m=100, hub_height_m=h)
        means.append(float(v_h.mean()))
    ax.plot(HUB_HEIGHTS_M, means, marker="o", label=f"{ts:%Y-%m-%d %H:%M} UTC (alpha={float(alpha_masked.mean()):.3f})")

ax.set_xlabel("Hub height [m]")
ax.set_ylabel("Domain-mean onshore wind speed [m/s]")
ax.set_title("Wind speed vs. hub height, extrapolated from our validated 100m field")
ax.legend()
fig.tight_layout()
fig.savefig(paths.images_path / "05_hub_height_profile.png", dpi=150, bbox_inches="tight")
plt.show()

# %% [markdown]
# ```{figure} ../../output/images/05_hub_height_profile.png
# :name: fig-05-hub-height-profile
# Domain-mean wind speed vs. hub height, extrapolated from the validated 100m field.
# ```
