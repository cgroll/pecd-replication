"""Per-(region, orientation-config) solar capacity factor.

Parametrized sibling of `pecdr.physics.solar_capacity_factor` -- that
function applies one fixed tilt/azimuth to an entire (time, lat, lon) ERA5
grid, appropriate for a first, deliberately simple baseline. This one
takes a single region's already-aggregated (time,) weather series plus an
explicit tilt/azimuth/tracking configuration, for `pipeline/27`'s
technology- and orientation-aware verification: since MaStR mostly lacks
per-plant coordinates (see `pecdr.solar_orientation`), weather has to stay
at NUTS2 region resolution, but panel geometry can now vary by
(region, technology, orientation) instead of being the same everywhere.

This implements PECD v4.2's own documented PV conversion chain, taken
directly from its Product User Guide (the version hosted on ECMWF's
Confluence truncates before this section for automated fetching; read
from a locally available full copy instead):

1. Decomposition: Skartveit-Olseth (1987) -- `pecdr.skartveit_olseth`.
2. Transposition: `GTI = Rb*BHI + Rd*DHI + Rr*GHI`, with Rb the standard
   geometric beam projection, Rd the **Klucher (1979)** anisotropic sky
   model ("specifically its [PECD's] implementation in the pvlib Python
   package" -- `pvlib.irradiance.klucher`), and Rr a fixed-albedo
   (rho=0.2) ground-reflected term, `rho*(1-cos(surface_tilt/2))` --
   PECD's own documented form, which differs from pvlib's default
   ground-diffuse term, so computed by hand rather than left to
   `get_total_irradiance`'s default.
3. Optical (reflection) losses: **Martin-Ruiz** (`pvlib.iam.martin_ruiz` /
   `martin_ruiz_diffuse`), applied separately to each of the three
   transposed components before summing to GTI_eff -- a component the
   original simple baseline has none of at all.
4. Module efficiency at 25C: a 5-coefficient polynomial in GTI_eff
   (Beyer et al., 2004, extending Williams et al., 2003), fit by PECD
   against real German/French PV generation data -- replaces the
   original baseline's generic PVWatts DC model entirely.
5. Cell temperature: Ross (1976), `T_cell = T_air + k*GTI_eff`, with
   PECD's documented k=0.34 (traditional mW/cm^2-based Ross/Skoplaki
   convention -- /10 for pvlib's W/m^2-based convention) -- and,
   confirmed directly from PECD's text, the *same* coefficient for
   rooftop and utility-scale alike (utility tracking explicitly
   "assumed to share the same assumptions as the utility-scale fixed
   case"), not a per-technology fit as this project first assumed
   before finding the primary documentation.
6. Thermal derating: linear, -0.45%/C (PECD's documented value; the
   original baseline used a generic -0.4%/C PVWatts default).
7. Inverter losses: PECD documents a 3-coefficient quadratic polynomial
   in the CF itself (Schmidt & Sauer, 1994, `INVERTER_COEFS`), applied
   as `CF = CF* * (b1 + b2*CF* + b3*CF*^2)` -- **not applied here**.
   Verified byte-for-byte against the raw LaTeX source (not a lossy
   prose reproduction), so this isn't an extraction error, but applying
   it exactly as documented behaves roughly like CF*^2 over the
   operating range (b2 dominates and is close to 1) -- a ~50% loss at
   half load, far more than any real inverter -- and empirically makes
   the match against PECD's own product markedly worse (corr 0.921 ->
   0.884; omitting it gives the best result found, corr 0.934). The
   reverse reading (dividing instead of multiplying) is far worse
   still. Left out, with the discrepancy flagged rather than silently
   resolved -- see the comment at its call site for the numbers.

Each region's own mask-weighted centroid (rather than one shared
domain-centroid point) is still used for solar position, a real, if
modest, precision gain over the original baseline given Germany's ~9
degree longitude span.
"""

import numpy as np
import pandas as pd
import pvlib

from pecdr.skartveit_olseth import skartveit_olseth
from pecdr.temporal_downscaling import downscale_to_subhourly

# Ross (1976)/Skoplaki et al. (2009) coefficient -- PECD documents 0.34 in
# the traditional mW/cm^2 convention for *both* rooftop and utility-scale
# (not a per-technology value), equivalent to 0.034 in pvlib's W/m^2-based
# convention.
ROSS_K = 0.034

GROUND_ALBEDO = 0.2  # PECD's rho (Gueymard et al., 2019)

MARTIN_RUIZ_AR = 0.17  # PECD's a_r (monocrystalline silicon)
MARTIN_RUIZ_C1 = 4 / 3 / np.pi
MARTIN_RUIZ_C2 = -0.069

EFFICIENCY_COEFS = (1.4306, -1.0084, 1.0121, -0.4401, 0.1979)  # a1..a5, Beyer et al. (2004)

TEMP_COEFF_PER_C = -0.0045  # -0.45%/C

INVERTER_COEFS = (-0.0005, 1.0269, -0.002217)  # b1..b3, Schmidt & Sauer (1994)

# Horizontal single-axis tracker, north-south axis -- PECD's own documented
# configuration (HSAT, backtracking, ground-coverage ratio 0.35) for the
# utility-scale tracking typology, also the only one MaStR's "nachgeführt"
# units are assumed to use (no further detail available).
TRACKER_AXIS_TILT_DEG = 0.0
TRACKER_AXIS_AZIMUTH_DEG = 0.0
TRACKER_GCR = 0.35


def solar_capacity_factor_for_config(
    ghi_wm2: pd.Series,
    temp_air_c: pd.Series,
    lat: float,
    lon: float,
    tilt_deg: float,
    azimuth_deg: float,
    is_tracked: bool,
) -> pd.Series:
    """Capacity factor (already a 0..~1 fraction) for one region's weather
    run through one fixed (or, if `is_tracked`, dynamically tracked) panel
    configuration, via PECD's documented conversion chain (see module
    docstring).
    """
    time_index = ghi_wm2.index
    ghi = np.clip(ghi_wm2.to_numpy(), 0, None)
    temp_air = temp_air_c.to_numpy()

    location = pvlib.location.Location(lat, lon, tz="UTC")
    solpos = location.get_solarposition(time_index)
    zenith = solpos["apparent_zenith"].to_numpy()
    azimuth = solpos["azimuth"].to_numpy()
    altitude = solpos["apparent_elevation"].to_numpy()

    decomposed = skartveit_olseth(ghi, zenith, altitude)
    dni, dhi = decomposed["dni"], decomposed["dhi"]

    if is_tracked:
        tracker = pvlib.tracking.singleaxis(
            apparent_zenith=zenith,
            solar_azimuth=azimuth,
            axis_tilt=TRACKER_AXIS_TILT_DEG,
            axis_azimuth=TRACKER_AXIS_AZIMUTH_DEG,
            backtrack=True,
            gcr=TRACKER_GCR,
        )
        # NaN surface_tilt/azimuth mean "sun below horizon, tracker angle
        # undefined" -- GHI is ~0 there too, so any fill value gives ~0 POA.
        surface_tilt = np.nan_to_num(tracker["surface_tilt"], nan=0.0)
        surface_azimuth = np.nan_to_num(tracker["surface_azimuth"], nan=180.0)
    else:
        surface_tilt = np.full_like(ghi, tilt_deg)
        surface_azimuth = np.full_like(ghi, azimuth_deg)

    # Transposition: GTI = Rb*BHI + Rd*DHI + Rr*GHI.
    bti = pvlib.irradiance.beam_component(surface_tilt, surface_azimuth, zenith, azimuth, dni)
    dti = pvlib.irradiance.klucher(surface_tilt, surface_azimuth, dhi, ghi, zenith, azimuth)
    rti = GROUND_ALBEDO * ghi * (1 - np.cos(np.radians(surface_tilt) / 2))

    # Optical (reflection) losses: Martin-Ruiz, applied per component.
    aoi = pvlib.irradiance.aoi(surface_tilt, surface_azimuth, zenith, azimuth)
    iam_beam = pvlib.iam.martin_ruiz(aoi, a_r=MARTIN_RUIZ_AR)
    iam_sky, iam_ground = pvlib.iam.martin_ruiz_diffuse(surface_tilt, a_r=MARTIN_RUIZ_AR, c1=MARTIN_RUIZ_C1, c2=MARTIN_RUIZ_C2)

    gti_eff_wm2 = np.clip(bti * iam_beam + dti * iam_sky + rti * iam_ground, 0, None)
    gti_eff_kwm2 = gti_eff_wm2 / 1000.0

    # Module efficiency at 25C (Beyer et al., 2004), fit against real
    # German/French PV generation data -- captures reduced efficiency at
    # low irradiance via the G*log(G) term.
    a1, a2, a3, a4, a5 = EFFICIENCY_COEFS
    with np.errstate(divide="ignore", invalid="ignore"):
        log_term = np.where(gti_eff_kwm2 > 0, gti_eff_kwm2 * np.log(gti_eff_kwm2), 0.0)
    cf_25c = a1 * gti_eff_kwm2 + a2 * gti_eff_kwm2**2 + a3 * gti_eff_kwm2**3 + a4 * gti_eff_kwm2**4 + a5 * log_term

    # Module temperature (Ross, 1976) and linear thermal derating.
    cell_temp = temp_air + ROSS_K * gti_eff_wm2
    cf_thermal = cf_25c * (1 + TEMP_COEFF_PER_C * (cell_temp - 25))

    # Inverter losses (Schmidt & Sauer, 1994) -- NOT applied. Taken exactly
    # as documented (verified against the raw LaTeX source, not just a
    # prose reproduction), `cf_thermal * (b1 + b2*cf_thermal + b3*cf_thermal**2)`
    # behaves roughly like cf_thermal**2 over the operating range (b2
    # dominates and is close to 1), which would mean a ~50% loss at half
    # load -- far more than any real inverter, and it empirically makes
    # the match against PECD's own product significantly worse (bias
    # +0.008 -> -0.049, corr 0.921 -> 0.884), not better. The reverse
    # (dividing instead of multiplying) is far worse still (bias +0.39).
    # Omitting this step entirely gives the best result of everything
    # tried (bias 0.026, corr 0.934) -- so it's left out, with this
    # discrepancy flagged rather than silently resolved.
    cf = np.clip(cf_thermal, 0, 1.0)
    return pd.Series(cf, index=time_index)


def solar_capacity_factor_for_config_downscaled(
    ghi_wm2: pd.Series,
    temp_air_c: pd.Series,
    lat: float,
    lon: float,
    tilt_deg: float,
    azimuth_deg: float,
    is_tracked: bool,
) -> pd.Series:
    """Same as `solar_capacity_factor_for_config`, but replicating PECD's
    documented second temporal-downscaling step: GHI/TA are interpolated
    to 15-minute resolution (`pecdr.temporal_downscaling`), CF is
    computed at that finer step, then averaged back to hourly.

    `ghi_wm2`/`temp_air_c` must include one leading hour *before* the
    first hour to be returned -- ERA5's hourly GHI is a backward-looking
    average (the value at timestamp t covers (t-1h, t]), so reproducing
    an hourly CF for t requires sub-hourly samples starting at t-1h, not
    just at t. That leading hour is used only as an interpolation anchor
    and is dropped from the returned Series by the right-closed,
    right-labeled resample below.
    """
    ghi_subhourly, temp_subhourly = downscale_to_subhourly(ghi_wm2, temp_air_c, lat, lon)
    cf_subhourly = solar_capacity_factor_for_config(ghi_subhourly, temp_subhourly, lat, lon, tilt_deg, azimuth_deg, is_tracked)
    return cf_subhourly.resample("1h", closed="right", label="right").mean().iloc[1:]
