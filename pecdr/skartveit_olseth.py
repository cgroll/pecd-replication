"""Skartveit & Olseth (1987) GHI decomposition (diffuse fraction) model.

PECD's own v4.2 documentation confirms this exact model: "The diffuse
horizontal irradiance (DHI) is first estimated using the Skartveit-Olseth
model (Skartveit et al., 1987), which estimates the diffuse fraction...
This model accounts for three distinct sky conditions -- overcast,
partially cloudy, and clear -- and uses the clearness index (Kt) and
solar elevation angle." Only the 1987 paper is cited (not the 1998
Skartveit/Olseth/Tuft variability-and-albedo extension), so this
implements the plain 1987 model, no hour-to-hour variability correction.

Ported from a verified, working R implementation (`difprop()`'s
non-variability code path, ilyamaclean/microctools,
https://raw.githubusercontent.com/ilyamaclean/microctools/master/R/solar.R)
rather than the original paper directly -- several independent attempts to
extract the exact published equations from PDFs and web summaries produced
inconsistent, likely-transcription-error results (e.g. a coefficient of
0.87 in one extraction vs. 0.83 in the verified source), and equations
this precise, with nested piecewise branches and trig-of-ratio terms, are
too easy to get subtly wrong from a lossy prose reproduction.

Solar altitude comes from pvlib's own (SPA-based) solar position, not the
source package's simpler approximation, since this project already
computes it that way elsewhere.
"""

import numpy as np
import pandas as pd
import pvlib


def skartveit_olseth(ghi_wm2: np.ndarray, zenith_deg: np.ndarray, altitude_deg: np.ndarray) -> dict:
    """DNI and DHI for one hourly time series, via the Skartveit-Olseth
    (1987) diffuse-fraction model. Returns a dict with "dni" and "dhi"
    (W/m^2), matching `pvlib.irradiance.erbs`'s interface.
    """
    rad = ghi_wm2 * 0.0036  # W/m^2 -> MJ/m^2/hr, matching the model's own calibration
    sa = altitude_deg
    alt = np.radians(sa)

    k1 = 0.83 - 0.56 * np.exp(-0.06 * sa)
    si = np.clip(np.sin(alt), 0, None)
    with np.errstate(divide="ignore", invalid="ignore"):
        k = rad / (4.87 * si)
    k = np.where(np.isfinite(k), k, 0.0)
    k = np.clip(k, 0, k1)

    k2 = 0.95 * k1
    d1 = np.where(sa > 1.4, 0.07 + 0.046 * (90 - sa) / (sa + 3), 1.0)
    K = 0.5 * (1 + np.sin(np.pi * (k - 0.22) / (k1 - 0.22) - np.pi / 2))
    d2 = 1 - ((1 - d1) * (0.11 * np.sqrt(K) + 0.15 * K + 0.74 * K**2))

    with np.errstate(divide="ignore", invalid="ignore"):
        d3 = (d2 * k2) * (1 - k) / (k * (1 - k2))
        alpha = (1 / np.sin(alt)) ** 0.6
        kbmax = 0.81**alpha
        kmax = (kbmax + d2 * k2 / (1 - k2)) / (1 + d2 * k2 / (1 - k2))
        dmax = (d2 * k2) * (1 - kmax) / (kmax * (1 - k2))
        d4 = 1 - kmax * (1 - dmax) / k

    d = np.where(k <= kmax, d3, d4)
    d = np.where(k <= k2, d2, d)
    d = np.where(k <= 0.22, 1.0, d)

    d = np.where(ghi_wm2 <= 0, 0.5, d)
    d = np.where(sa < 0, 1.0, d)
    d = np.clip(d, 0, 1)
    d = np.where(np.isfinite(d), d, 0.5)

    dhi = d * ghi_wm2
    dni = pvlib.irradiance.dni(pd.Series(ghi_wm2), pd.Series(dhi), pd.Series(zenith_deg)).fillna(0.0).to_numpy()
    return {"dni": dni, "dhi": dhi}
