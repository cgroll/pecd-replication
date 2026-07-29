"""Second step of PECD's documented two-step temporal downscaling (PUG,
"Temporal downscaling"): hourly GHI/TA -> 15-minute resolution, so that PV
capacity factor can be computed at the finer step and then averaged back
to hourly -- intended to better capture diurnal (sunrise/sunset) solar
variability than computing CF once per hour.

The PUG's *first* downscaling step (3-hourly -> hourly, via a clearness-
index conversion for GHI and a cubic spline for TA) only applies to the
climate-projections stream; this project's ERA5 source is already
hourly, so that step doesn't apply here. This module replicates the
*second* step only, which the PUG says applies to "both historical and
projected datasets".

The PUG doesn't restate the Kt mechanics verbatim for this second step
(only for the first), but motivates it identically ("removes the
influence of solar geometry"), so GHI is downscaled the same way here:
converted to a clearness index Kt = GHI / GHI_extraterrestrial, linearly
interpolated, then reconverted to GHI at the finer resolution. TA uses a
cubic spline, as the PUG documents explicitly for both steps.
"""

import numpy as np
import pandas as pd
import pvlib
from scipy.interpolate import CubicSpline

SUBHOURLY_FREQ = "15min"


def _extraterrestrial_horizontal_wm2(time_index: pd.DatetimeIndex, lat: float, lon: float) -> np.ndarray:
    """Top-of-atmosphere irradiance on a horizontal plane at each
    timestamp -- the Kt denominator for the clearness-index conversion.
    """
    location = pvlib.location.Location(lat, lon, tz="UTC")
    solpos = location.get_solarposition(time_index)
    dni_extra = pvlib.irradiance.get_extra_radiation(time_index)
    cos_zenith = np.cos(np.radians(solpos["apparent_zenith"].to_numpy()))
    return np.clip(np.asarray(dni_extra) * cos_zenith, 0, None)


def downscale_to_subhourly(ghi_wm2: pd.Series, temp_air_c: pd.Series, lat: float, lon: float) -> tuple[pd.Series, pd.Series]:
    """Hourly GHI/TA `Series` (regular hourly `DatetimeIndex`) -> 15-minute
    series spanning the same start/end timestamps.

    Callers that need a full day of downscaled, hourly-averaged-back
    output should include one leading "anchor" hour before the day of
    interest in `ghi_wm2`/`temp_air_c` -- see
    `solar_config_physics.solar_capacity_factor_for_config_downscaled`,
    which resamples back with right-closed, right-labeled hourly bins and
    so needs data from *before* its first output hour.
    """
    hourly_index = ghi_wm2.index
    subhourly_index = pd.date_range(hourly_index[0], hourly_index[-1], freq=SUBHOURLY_FREQ)
    hourly_sec = hourly_index.asi8 / 1e9
    subhourly_sec = subhourly_index.asi8 / 1e9

    toa_subhourly = _extraterrestrial_horizontal_wm2(subhourly_index, lat, lon)

    # ERA5's hourly GHI is a *mean* over (t-1h, t], so the Kt denominator
    # must be a mean over that same window -- not TOA sampled only at the
    # instant t. Using the instant alone is 0 whenever apparent sunset
    # falls inside (t-1h, t) but before t itself, which spuriously zeroes
    # real sub-hourly irradiance for the *entire* hour (verified: DE30,
    # 2020-01-15, the hour ending 16:00 has GHI=1.5 W/m2 but instantaneous
    # TOA=0 exactly at 16:00 -- sun already below the horizon at that
    # instant even though it wasn't for most of the preceding hour).
    toa_hourly = (
        pd.Series(toa_subhourly, index=subhourly_index)
        .resample("1h", closed="right", label="right")
        .mean()
        .reindex(hourly_index)
        .to_numpy()
    )
    kt_hourly = np.divide(ghi_wm2.to_numpy(), toa_hourly, out=np.zeros_like(toa_hourly), where=toa_hourly > 0)
    kt_subhourly = np.interp(subhourly_sec, hourly_sec, kt_hourly)

    ghi_subhourly = pd.Series(np.clip(kt_subhourly * toa_subhourly, 0, None), index=subhourly_index)

    temp_spline = CubicSpline(hourly_sec, temp_air_c.to_numpy())
    temp_subhourly = pd.Series(temp_spline(subhourly_sec), index=subhourly_index)

    return ghi_subhourly, temp_subhourly
