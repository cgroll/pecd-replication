---
title: Introduction
---

# Replicating PECD: physically-motivated features for forecasting Germany's power market

## The goal

The wider goal behind this project is forecasting the DE-LU bidding zone's
headline variables: wind generation, PV generation, and load (demand). This
project itself is one building block toward that goal, not the end in
itself — see [How this project fits the wider goal](#project-fit) below.

## Current status: how well does each replication work?

All three workstreams are checked the same way in the end: weight a modeled
capacity factor up to a national figure using MaStR's own time-varying
installed capacity, then compare against SMARD's actual net generation
over the full 2019-2025 backtest (61,368 hours). Three points of
comparison throughout: PECD's own official product (reweighted by MaStR
capacity, not a replication at all — the best available anchor for "how
good can this possibly get"), the simplest from-scratch physics baseline
this project started from, and this project's own best replication.

| Workstream | PECD official × MaStR | Naive physics baseline | This project's own replication |
|---|---|---|---|
| **Wind onshore** | MAE 0.029, corr 0.985 | MAE 0.089, corr 0.931 | **MAE 0.065, corr 0.983** |
| **Wind offshore** | MAE 0.094, corr 0.902 | MAE 0.133, corr 0.882 | **MAE 0.128, corr 0.916** |
| **Solar PV** | MAE 0.016, corr 0.981 | MAE 0.057, corr 0.926 | **MAE 0.046, corr 0.937** |

**Wind is essentially converged**: this project's full replication
(GWA bias-adjusted wind speed, alpha hub-height extrapolation, per-plant
power curves) reaches corr 0.983 against real SMARD generation — a hair
under PECD's own 0.985, and far past the naive baseline's 0.931. The
remaining open item is a systematic high-wind over-estimate, most likely
from the wake-effect/farm-layout modeling this project deliberately
doesn't attempt (see the roadmap below).

**Wind offshore reaches the best correlation of the three (0.916), but a
larger bias than either other approach**: the same per-plant chain as
onshore, adapted for two offshore-specific findings (GWA2's
bias-correction reference barely reaches past ~20km offshore; the shared
storm-shutdown model over-derates in wind speeds offshore sees regularly
but onshore rarely does — see the section below). The replication's
correlation edges out even PECD's own official product (0.916 vs. 0.902),
but its bias (+0.108) is about 50% larger than PECD's own (+0.073) and the
naive baseline's (+0.071), which now come out statistically close to each
other — against real SMARD generation, most likely unmodeled offshore
curtailment from delayed grid
connections, a well-documented real-world issue neither model attempts.

**Solar has closed much of the gap but not all of it**: swapping in
PECD's fully documented PV conversion chain (Skartveit-Olseth
decomposition, Klucher transposition, Martin-Ruiz optical losses, a Beyer
et al. efficiency polynomial, Ross cell temperature, real per-plant
orientation from MaStR) took correlation against SMARD from 0.926 to
0.937 and MAE from 0.057 to 0.046 — a real, year-over-year-consistent
improvement over the naive baseline. But PECD's own product is still
roughly 3x closer to reality (MAE 0.016 vs. 0.046) than this project's
best replication gets. Open candidates, none conclusively resolved yet:

- **PECD's documented inverter-loss polynomial** (Schmidt & Sauer, 1994):
  applying it exactly as written makes the match against PECD's *own*
  product worse, not better, so it's currently omitted — but that may
  just trade one bias for another when checked against real generation
  instead ([27](../notebooks/27_verify_solar_technology_physics.ipynb)).
- **The overestimate grows sharply with output level**, plateauing
  around +0.08-0.09 capacity-factor bias above ~30% output — consistent
  with either missing inverter clipping or unmodeled self-consumption
  (rooftop generation used behind the meter, disproportionately during
  high-output hours) ([29](../notebooks/29_analyse_solar_full_year.ipynb)).
- **All three solar approaches — including PECD's own official
  product — get measurably worse year over year**, 2019 through 2025.
  Since that includes PECD's own product, it isn't a flaw in either
  physics chain specifically; more likely a growing self-consumption
  share, unmodeled panel degradation, or a shifting technology mix
  ([29](../notebooks/29_analyse_solar_full_year.ipynb)).
- PECD's documented 15-minute **temporal downscaling** step was
  implemented and tested — it makes no measurable difference, so it's
  ruled out as an explanation for the remaining gap
  ([27](../notebooks/27_verify_solar_technology_physics.ipynb)).

## Why physical modeling helps: residual load

If we know the weather and which power plants exist, we can, in principle,
compute power output directly from physical equations — no statistical
model needed. Suppose demand were fully price-inelastic (fixed regardless
of price). Then total generation must equal demand at every instant. If
renewables generate less than is demanded, the gap — the **residual
load** — has to be met by something else: coal or gas plants domestically,
or imports (nuclear power from a neighboring country, for instance).

Residual load is, by definition, just demand minus renewable generation. So
if we can forecast renewable generation well, we get residual load for free
— which is arguably the more economically interesting quantity, since it's
residual load that drives prices, dispatch, and import/export flows.

## Why it's hard in practice

Even where the physical equations themselves are well understood (wind is
the clearest example), several things stand between "we know the weather"
and "we know the exact power injected into the grid":

1. **High-wind shutdown.** Turbines cut out above some wind speed for
   safety. Modelable in principle from wind speed alone, but PECD's own
   methodology treats it as a per-turbine hysteresis process (shutdown and
   restart at different thresholds), which needs state we don't have.
2. **Wind farm layout and wake effects.** Where exactly a turbine sits
   inside its farm, and which direction the wind is blowing from, changes
   what wind speed it actually experiences — a front-row turbine sees
   different wind than one further back, whose approaching wind has
   already been slowed and turbulized by the rows ahead of it.
3. **Outages.** Wind farms are sometimes offline entirely for maintenance
   or repair, independent of weather.
4. **Curtailment.** When the grid is congested, some turbines aren't
   allowed to feed in at all, regardless of how much wind is available.
   This is expected to become more common, not less, as renewable
   penetration grows.
5. **No ground truth for any of the above, individually.** There is no
   published time series that isolates "generation lost to curtailment" or
   "generation lost to an outage" — only the net result reaches public
   data.
6. **The behind-the-meter blind spot.** Grid statistics (SMARD, in this
   project's case) only observe power **in front of the meter** — what
   actually crosses into the public grid. Anything happening **behind the
   meter** is invisible: if someone generates electricity and consumes it
   themselves, it shows up in neither the published generation figure nor
   the published demand figure. What we actually have access to is net
   generation and net demand, both already reduced by whatever
   self-consumption happened behind meters we can't see.

   This has a subtle consequence for residual load specifically: since
   self-consumption is missing from *both* sides of the residual-load
   calculation in equal measure (the self-consumed MWh is absent from
   published generation, but also absent from published demand, since it
   was never drawn from the grid), the two omissions cancel and residual
   load itself stays largely correct. What breaks is any direct comparison
   of our own **gross** physical generation estimate against SMARD's
   **net** generation figure — that comparison is not apples-to-apples
   unless self-consumption is explicitly accounted for.

## What would a full replication need?

To compute gross wind production for a given weather situation, we need to
know, precisely: (1) what the wind is, everywhere, and (2) exactly where
which wind turbines stand, and which model they are.

- For historical wind, the **ERA5** reanalysis is the standard choice.
- For plant location and turbine type, the
  **Marktstammdatenregister (MaStR)** is Germany's own public register.
- Alternatively, **PECD** (the Pan-European Climate Database) already does
  a version of this, at a European scale, with more elaborate methodology
  and proprietary inputs we don't have access to.

## PECD's own methodology

PECD v4.2's wind capacity factor pipeline, in order:

1. Take ERA5 wind speed at 10m and 100m.
2. Apply a **bias adjustment** using Global Wind Atlas (GWA) data — ERA5's
   reanalysis wind speed is systematically off from observations in a
   way that varies by location; GWA's higher-resolution product corrects
   this.
3. Extrapolate to each turbine's actual **hub height**, using a
   precomputed shear exponent (**alpha**) — wind speed doesn't scale
   linearly with height, alpha captures how steeply it changes.
4. Look up each location's installed turbine type and compute a
   **capacity factor** from that turbine's power curve.
5. Correct for the wind farm's actual **layout** — which turbines are in
   the first row versus further back, since row position changes the wind
   a turbine actually sees (wake effects).
6. Apply **high-wind shutdown** assumptions, per turbine.

## Our replication strategy

We rebuild this methodology with the means available to us: **ERA5** for
weather (same source PECD itself uses), and **MaStR** for plant location
and turbine type (PECD uses a different, proprietary database —
WindPowerNet — that we don't have access to).

The hard part is that there is no single ground-truth time series against
which to check whether the full replication is correct end to end. So
instead of one validation, we built a **ladder** of checks, each isolating
one step, each checked against whatever partial ground truth PECD itself
publishes:

1. **Bias-adjusted wind speed** vs. PECD's own published bias-adjusted
   wind speed grid — a genuine, direct ground truth, since PECD publishes
   this as a gridded product in its own right.
2. **Hub-height extrapolation** — no direct ground truth exists (PECD
   never publishes wind speed at arbitrary hub heights), so this is
   instead checked for **internal consistency**: since alpha was itself
   derived from the 10m/100m ratio, extrapolating our validated 100m field
   back down to 10m via alpha should closely reproduce our validated 10m
   field.
3. **Zone-level capacity factor** (PEON zones, the only spatial
   aggregation PECD publishes for wind) vs. PECD's own zone capacity
   factors — comparable either as relative capacity factors, or, weighted
   by MaStR's installed capacity per zone, as absolute MW.
4. **National aggregate** — MaStR's zone-level installed capacity lets us
   weight the 7 PEON zones up to one Germany-wide number, comparable
   against the same aggregation applied to PECD's own zone figures (since
   PECD itself publishes no ready-made national number for wind).
5. **SMARD's actual net wind generation** — the one point of comparison
   against real-world data, not just PECD's own numbers. A deviation here
   can come from two different sources that are easy to conflate: our
   physical replication being imperfect, *or* curtailment/self-consumption
   creating a genuine gap between gross physical generation and what
   actually reaches the grid. Neither PECD's product nor ours attempts to
   model curtailment, so some gap here is expected even from a perfect
   physical replication.

(project-fit)=
## How this project fits the wider goal

Three different ways of turning weather + MaStR capacity into a physically-
motivated wind feature have been built (see
[Comparing all three approaches](../notebooks/12_compare_all_approaches.ipynb)):

1. **PECD's own capacity factor, reweighted by MaStR capacity** — trusts
   PECD's official numbers wholesale.
2. **A simple from-scratch physics model** (one generic turbine curve, raw
   ERA5, no bias correction) — the simplest possible replication.
3. **This project's full replication** — GWA-bias-adjusted wind speed,
   alpha-based hub-height extrapolation, per-plant power curves matched to
   real turbine models where possible.

None of these three is "the answer" in isolation — the actual target is
forecasting headline variables well, and any feature that helps with that
is worth keeping even where it deviates from PECD's own methodology.
Replicating PECD as closely as possible is the validation exercise that
tells us *how good* a candidate feature is, not the end goal itself.

## Roadmap: where each notebook fits

| Notebook | Validation-ladder step | What it shows |
|---|---|---|
| [04: Wind bias-correction replication](../notebooks/04_replicate_wind_bias_correction.ipynb) | Step 1 | Our GWA delta-adjustment vs. PECD's own bias-corrected wind speed grid — near-exact match (MAE ~0.0005 m/s) |
| [05: Hub-height extrapolation](../notebooks/05_extrapolate_wind_to_hub_height.ipynb) | Step 2 | Internal-consistency check via PECD's precomputed alpha grid, since no direct ground truth exists |
| [09: Wind-onshore capacity factor replication](../notebooks/09_replicate_wind_onshore_capacity_factor.ipynb) | Steps 3-4 (deliberately skipping step 5, simplifying step 6) | Per-plant power curves from MaStR + PECD's alpha, aggregated to PEON zone and compared against PECD's own zone capacity factors; surfaces a systematic high-wind over-estimate, most likely from the wake effects we deliberately don't model |
| [11: Full-year validation](../notebooks/11_analyse_wind_onshore_full_year.ipynb) | Steps 3-4, extended | Same comparison across all 61,368 hours of 2019-2025 rather than two snapshots — confirms the high-wind bias is systematic, not a fluke of which hours were picked |
| [12: Comparing all three approaches](../notebooks/12_compare_all_approaches.ipynb) | Step 5 | Brings in SMARD's actual net generation as real-world ground truth; shows this project's replication tracks the true temporal pattern much better than the simple-physics approach (corr 0.983 vs. 0.931), while still carrying the same high-wind over-estimate — now confirmed against reality, not just against PECD's own numbers |

What isn't built yet, and is deliberately visible as a gap rather than
papered over: wake-effect/layout correction (step 5 of PECD's own
methodology), curtailment, outages, and behind-the-meter self-consumption
— none of these have a ground-truth series to check against, which is
exactly why they're absent from every approach compared here, not only
this project's.

## Wind offshore replication

Same ladder as onshore (per-plant power curves from MaStR, PECD's alpha
grid for hub-height extrapolation, checked against PECD's own zone product
then against SMARD's actual `wind_offshore` generation), but two of
onshore's steps needed a genuine methodology change rather than a
copy-paste, both found by checking intermediate results against real
numbers rather than assumed to transfer directly from onshore:

- **GWA2 barely covers the German offshore fleet.** GWA's own downscaling
  (WAsP) explicitly excludes "offshore areas beyond 20 km" (per the PUG).
  Checked against MaStR's actual offshore turbine coordinates: **91% of
  installed German offshore capacity** sits at grid cells with no GWA2
  delta-correction factor at all. Cross-checked against PECD's own
  downloaded bias-adjusted wind-speed product vs. raw ERA5 at those same
  deep-sea cells: the ratio is ~1.0000 beyond ~20km from shore (real
  correction only applies near-shore) — PECD's own product evidently
  leaves deep-offshore wind speed uncorrected too. The replication matches
  that: apply the GWA delta where available, leave raw ERA5 speed
  unmodified elsewhere.
- **The shared storm-shutdown model over-derates offshore.** Its linear
  ramp (20→25 m/s) is tuned against onshore, where hub-height wind speed
  rarely exceeds 20 m/s; offshore it regularly does (checked: ~3.8% of
  hours at a representative North Sea cell across 2022 fall in that 20-25
  m/s band, vs. essentially never onshore). Applied as written it derated
  a January storm snapshot to a third of PECD's own product's output at
  that hour, even though the *pre*-shutdown power curve alone already
  tracked PECD's product closely (0.91 vs. 0.86) — same pattern as solar's
  inverter-loss polynomial: implemented elsewhere
  (`pecdr/shutdown.py`), demonstrably doing net harm here, so left out of
  the offshore chain with the discrepancy documented rather than patched
  with an unvalidated offshore-specific threshold.

Offshore turbine technical detail in MaStR is markedly more complete than
onshore's — 100% of active offshore capacity has a known turbine model
(vs. ~44-56% onshore) and 97.6% a known hub height — though only ~2.5% of
that capacity matches an exact public OEDB power curve (vs. ~44% onshore,
most offshore models being larger/newer than the library covers), so the
generic specific-power-parametrized fallback curve carries most of the
offshore fleet.

Against SMARD's actual generation, this project's replication reaches the
**best correlation of the three** (0.916, edging out even PECD's own
official product's 0.902) but with a larger absolute bias (+0.108 vs.
PECD's +0.073 and the naive baseline's +0.071) — it tracks the true
up-and-down weather pattern slightly better than PECD's own product does,
but systematically overestimates the level more. Plausible drivers, none
isolated yet: German offshore wind has
well-documented real-world curtailment from delayed grid connections
(farms commissioned before their export cable is ready), which neither
this replication nor PECD's own product attempts to model — the same
"no ground truth for curtailment" gap flagged for onshore above, likely
larger here since offshore grid-connection delays are a well-known,
material issue in the German market.

**Is the bias just our own capacity accounting being wrong, rather than
curtailment?** The "PECD official x MaStR" comparison above leans on this
project's own MaStR-derived monthly PEOF-zone capacity panel for weighting
on *both* sides — so a wrong capacity vector could manufacture that same
bias with no real curtailment involved. Checked directly: solving for the
per-zone capacity vector that best reconstructs SMARD's actual generation
from PECD's own zone capacity-factor shapes (non-negative, monotonically
non-decreasing, via NNLS on a reparametrized design matrix — see notebook
35) drives the bias to roughly zero (-0.03 vs. MaStR weights' +0.16 in MW
terms, same 3-zone basis), confirming a real chunk of the bias *is*
attributable to our own capacity numbers, not to PECD or curtailment.
But correlation barely moves (0.909 vs. 0.898) — reweighting capacity
fixes the *level*, not the *shape*. Since the fitted vector is by
construction the best any monotonic capacity story can do, that remaining
gap can't be closed by better fleet data — it needs something the capacity
vector structurally can't represent: curtailment or another dynamic
effect. The fitted national capacity trajectory is also strikingly
different in *shape* from MaStR's: essentially flat 2020-2024 while
MaStR's nameplate figure climbs steadily, only converging in 2025 — the
same window Germany's offshore grid connections
(BorWin5/DolWin6-era converter platforms) were catching up with the
capacity build-out, consistent with, though not proof of, a growing
grid-bottleneck story.

One more data-quality finding along the way, worth flagging on its own:
**3 of PECD's 6 PEOF zones (`DE013_OFF`/`DE014_OFF`/`DE015_OFF`) are 100%
`NaN`** in PECD's own product across the entire 2015-2025 file — PECD
apparently never modeled them. `DE013_OFF` still carries real MaStR
capacity (up to ~300 MW), which was silently diluting the "PECD official x
MaStR" capacity-weighted denominator above with dead-weight capacity that
contributes nothing to the numerator — a small (~1.5-3% of national
capacity) but real effect, separate from the capacity-vector question
above. Fixed in notebook 34 by restricting that comparison to the zones
PECD actually has data for; the numbers already quoted throughout this
page reflect the fix. Removing the dilution moved "PECD official x MaStR"
bias *up* (+0.060 → +0.073), not down — the dilution had been partially
masking, not inflating, the true bias.

## Roadmap: wind offshore notebooks

| Notebook | What it shows |
|---|---|
| [31: PEOF zone replication](../notebooks/31_replicate_wind_offshore_capacity_factor.ipynb) | Two-snapshot check against PECD's own PEOF zone product; surfaces and resolves the GWA2 coverage gap and storm-shutdown over-derate above (MAE 0.046 / corr 0.989 on the storm snapshot once resolved, vs. 0.28 / 0.71 before) |
| [33: Full-year validation](../notebooks/33_analyse_wind_offshore_full_year.ipynb) | Same comparison across all 61,368 hours of 2019-2025 — MAE 0.059, corr 0.986 vs. PECD's own PEOF product, with a persistent +0.043 mean bias |
| [34: Comparing all approaches](../notebooks/34_compare_wind_offshore_approaches.ipynb) | Brings in SMARD's actual net generation; this project's replication reaches the best correlation of the three (0.916) but the largest absolute bias, likely reflecting unmodeled offshore curtailment. Also fixes a data-quality issue: 3 of PECD's 6 PEOF zones are 100% unmodeled by PECD, which was silently diluting approach 1's capacity-weighted denominator |
| [35: Fitting optimal capacity weights](../notebooks/35_fit_wind_offshore_capacity_weights.ipynb) | Tests whether the bias is just wrong fleet numbers: an NNLS-fit optimal capacity vector zeroes out the bias but barely improves correlation — capacity accounting explains the *level* gap, not the *shape* gap, pointing at curtailment (or another dynamic effect) for what's left |
| [36: What drives the bias?](../notebooks/36_analyse_wind_offshore_bias_drivers.ipynb) | Offshore mirror of onshore's bias-driver analysis (bias vs. CF level/month/hour/oversupply/year) — bias climbs cleanly and monotonically with system-wide renewable oversupply all the way to the highest bin (unlike onshore, where that panel mostly restates the CF-level result), and roughly doubles from a 2019-2021 baseline to a 2023-2024 peak before easing in 2025, corroborating notebook 35's capacity-fitting timeline independently. Two genuinely offshore-specific, unresolved departures from onshore's pattern: bias reverses at the very highest CF bins instead of growing monotonically, and peaks at midday instead of overnight |

Bias-driver analysis is now built for offshore (notebook 36 above); still
deliberately out of scope for this pass, same incremental spirit as
solar's own build-out: walk-forward bias correction, onshore's step 23.

## Solar PV replication

Same goal as wind — a physically-motivated PV generation feature, checked
against PECD's own product and then against SMARD's real generation — but
starting from a harder position: MaStR mostly lacks per-plant coordinates
for solar (~95% missing), so weather has to stay at NUTS2 region
resolution rather than per-plant grid cells, and PV physics has more
conversion steps than a wind turbine's power curve (irradiance
decomposition, plane-of-array transposition, optical losses, module
efficiency, cell temperature, inverter losses).

### PECD's own methodology (v4.2 Product User Guide)

1. Decompose horizontal irradiance (GHI) into beam and diffuse components
   (Skartveit-Olseth, 1987).
2. Transpose onto the panel's actual plane of array — Klucher's (1979)
   anisotropic sky model for diffuse sky radiation, plus a fixed-albedo
   ground-reflected term.
3. Apply optical (reflection) losses at the panel surface (Martin-Ruiz).
4. Convert plane-of-array irradiance to module efficiency at 25°C via a
   5-coefficient polynomial (Beyer et al., 2004), fit by PECD against real
   German/French generation data.
5. Correct for cell temperature (Ross, 1976) and a linear thermal
   derating coefficient.
6. Apply inverter losses via a 3-coefficient polynomial (Schmidt & Sauer,
   1994).
7. A two-step temporal downscaling (hourly GHI/TA interpolated to
   15-minute resolution, capacity factor computed at that finer step,
   then averaged back to hourly) to better capture sunrise/sunset
   variability.

### Our replication strategy

Two versions have been built, in sequence:

1. **A simple baseline** (`pecdr/physics.py`) — Erbs decomposition, one
   fixed tilt/azimuth for all of Germany, Faiman cell temperature, a
   generic PVWatts DC model. No technology split.
2. **The full PECD-documented chain** (`pecdr/solar_config_physics.py`) —
   every step above except inverter losses (see below), using each MaStR
   unit's *actual* reported orientation and tilt bucket
   (`pecdr/solar_orientation.py`) split across PECD's 4 technology
   classes (industrial/residential rooftop, utility fixed/tracking).

The documented inverter-loss polynomial (step 6) is implemented
(`INVERTER_COEFS` in `pecdr/solar_config_physics.py`) but not applied: taken
exactly as written and checked against the raw LaTeX source of the PUG
(not a lossy prose extraction), it behaves like roughly capacity-factor
squared across the operating range — a ~50% loss at half load, far more
than any real inverter — and makes the match against PECD's own product
markedly worse rather than better. Left out, with the discrepancy flagged
in the code rather than silently resolved. The temporal-downscaling step
(step 7) is implemented (`pecdr/temporal_downscaling.py`) and tested, and
makes no measurable difference once an initial phase-mismatch bug (an
hourly-average GHI value divided by an *instantaneous* clear-sky
irradiance sample near sunset) was found and fixed.

Prerequisite step, no notebook of its own: `pipeline/24` crosswalks MaStR
units to PECD's 4 PV technology codes (industrial/residential rooftop,
utility fixed/tracking — MaStR has no such labels natively) and builds a
monthly (NUTS2 zone × technology) installed-capacity panel used
throughout everything below.

## Roadmap: solar notebooks

| Notebook | What it shows |
|---|---|
| [25: First comparison against SMARD](../notebooks/25_compare_solar_approaches.ipynb) | PECD's own product vs. the simple baseline vs. SMARD's actual generation, full available period |
| [26: Bias drivers](../notebooks/26_analyse_solar_bias_drivers.ipynb) | Explores whether the simple baseline's bias tracks capacity-factor level, month, year, or self-consumption share |
| [27: Technology- and orientation-aware physics](../notebooks/27_verify_solar_technology_physics.ipynb) | Builds and verifies the full PECD-documented chain against PECD's own NUTS2 × technology product (corr 0.934, up from 0.921 with a simpler chain); tests and rules out temporal downscaling as a fix for the remaining gap |
| [29: Full-period validation](../notebooks/29_analyse_solar_full_year.ipynb) | Extends 27 to the full 2019-2025 backtest and brings in SMARD as real-world ground truth — confirms the new chain is a consistent improvement over the simple baseline (corr 0.926 → 0.937, every year), while PECD's own product remains substantially closer to reality |

What isn't resolved yet, same spirit as wind's open items: the
inverter-loss discrepancy above, the sharp bias growth with output level,
and the year-over-year bias drift shared by *all three* approaches
(see [Current status](#current-status-how-well-does-each-replication-work)
above) — none of these have an isolated ground-truth series to check
against either.

## Congestion & curtailment: what the data shows

Before trusting any *estimated* curtailment model, it's worth looking at
real ground truth — from two sources with very different tradeoffs,
described and then reconciled across four notebooks.

[The first notebook](../notebooks/44_analyse_congestion_curtailment.ipynb)
covers SMARD's monthly series: TSO+DSO combined, folds in countertrading
and grid-reserve volume (not redispatch-only), and reflects a settled,
ex-post counterfactual ("Ausfallarbeit") calculation rather than a live
instructed-power reading — real, but coarse (monthly, national-only). Wind
dominates curtailment volume, offshore wind is curtailed roughly 8-9x more
heavily *per MW installed* than onshore, and PV's smaller curtailment
tracks its own generation season.

[The second notebook](../notebooks/45_explore_redispatch_measures.ipynb)
covers a much richer, per-measure source netztransparenz.de also publishes
(real timestamps, per-plant/cluster names) — TSO-issued, per-measure
frequency, but only comprehensively technology-labeled for offshore wind;
onshore wind and PV are almost never named individually.

[The third notebook](../notebooks/46_attribute_ambiguous_redispatch_entities.ipynb)
reconciles the two:
the aggregate gap is concentrated in the countertrading/unknown category
(only ~13% of SMARD's figure is captured), not spread evenly; offshore
wind matches almost exactly (100%) at the technology level; and most of
the per-measure file's unlabeled majority can be attributed statistically
(a seasonal-fingerprint fit per grid-connection entity — geographically
sensible, wind-dominated in the north and PV-dominated in Bavaria, without
ever being told any geography) after a MaStR-based join attempt turned out
to be a clean dead end. An important caveat carries through: this
attribution's absolute levels still run about a third below SMARD's, so
it's a better source for *shape* than for absolute levels.

That shortfall can be seen directly, before any wind/PV attribution ever
runs: summing onshore wind and PV together (everything in `Erneuerbar`
that isn't offshore) against SMARD's own combined `Wind_Onshore +
Photovoltaik` total needs no attribution guessing at all, and still only
captures 38.7% of SMARD's figure over the full period — confirming the
under-coverage is a real volume problem, not an artifact of splitting wind
from PV. The monthly ratio between the two is also far from a stable
scale factor: over 100x in mid-2022, settling to a calmer ~1.5-8x only
from late 2023 onward, tracking Redispatch 2.0's renewable reporting as it
matured rather than a fixed measurement bias.

[The fourth notebook](../notebooks/48_analyse_offshore_gap_vs_curtailment.ipynb)
uses offshore wind's now-trusted curtailment numbers to check a claim made
earlier, in the residual-load walkthrough: that offshore wind's raw
potential-observed gap is "(almost) entirely loss." Real curtailment
explains only ~40% of that gap on average. For what's left, negative
day-ahead prices — a second, price-driven form of voluntary curtailment
that never shows up in either redispatch source — turn out to carry real
signal: splitting days by whether they had a negative-price hour drops the
curtailment-only model's fit from R² = 0.89 to R² = 0.60, and a simple
regression of the curtailment-unexplained residual on negative-price
exposure comes back with a positive slope (~0.43) but a modest R² (0.26).
Negative prices are a real, measurable contributor — not the dominant one.
What's left after both mechanisms points at bias in this project's own
offshore "potential" replication as the more likely explanation for the
remainder.

[The fifth notebook](../notebooks/49_analyse_onshore_gap_vs_curtailment.ipynb)
asks the analogous question for onshore wind, whose reconstruction (unlike
offshore's) sits well below SMARD's reported total — only 45.1%, once
offshore's perfect match is excluded from chapter three's blended 67.5%
renewables figure. Rather than accept that shortfall, it tests whether a
pure monthly level correction (rescaling the reconstruction so its monthly
total matches SMARD's exactly) closes the potential-observed gap as well as
offshore's real curtailment did. It doesn't: R² against `y = x` only rises
from ~0.65 to ~0.75 (offshore went from 0.21 to 0.90), even though the
monthly *level* now matches SMARD by construction. The recalibration
factor itself is revealing — implausibly large (up to ~80x) in 2022,
settling to a plausible ~1.2-6x only from late 2023 onward — meaning the
early shortfall isn't a stable scale problem so much as a sign that
Redispatch 2.0's renewable reporting was still ramping up. The conclusion:
onshore's problem isn't just missing volume, it's that the *timing* of
what's currently captured is itself an imperfect proxy — pointing back at
the entity-level attribution problem (chapter 46) rather than a simple
correction factor.

### Roadmap: congestion data notebooks

| Notebook | What it shows |
|---|---|
| [44: SMARD's monthly series](../notebooks/44_analyse_congestion_curtailment.ipynb) | Attributes, verification against SMARD's own page, curtailment by source and season |
| [45: The per-measure series](../notebooks/45_explore_redispatch_measures.ipynb) | Attributes, the naming-convention bug, time trend, seasonality, TSO-based spatial proxy |
| [46: Comparing the two sources](../notebooks/46_attribute_ambiguous_redispatch_entities.ipynb) | Aggregate and per-technology reconciliation, the MaStR dead end, seasonal-fingerprint NNLS attribution |
| [48: Offshore gap vs. curtailment](../notebooks/48_analyse_offshore_gap_vs_curtailment.ipynb) | How much of offshore wind's raw potential-observed gap real curtailment and negative prices actually explain |
| [49: Onshore gap vs. curtailment](../notebooks/49_analyse_onshore_gap_vs_curtailment.ipynb) | Whether a pure monthly level correction to the onshore reconstruction closes the gap as well as offshore's real curtailment did — it doesn't |

## Residual load: demand and curtailment estimation

The wind and solar workstreams above check *generation* against SMARD.
The wider project goal, stated at the top of this page, is a **day-ahead
residual-load forecast** — which needs two things that are never directly
observed: gross power demand (grid-metered load plus invisible
behind-the-meter self-consumption) and renewable generation net of
curtailment. [A walkthrough page](residual_load_walkthrough.md) teaches
this model start to finish — the problem, the mental model, the
equations, and the evidence, in that order — and a
[dedicated reference page](curtailment_system_equations.md) writes down
the full system of equations relating these hidden variables to what
this project can actually observe. This section summarizes what came out
of estimating them.

**The gross-demand regression** (notebook 38) fits grid-metered load as a
calendar/temperature demand model minus PV self-consumption, identified
by a simple structural fact: behind-the-meter self-consumption can only
exist when PV is producing, so nighttime and heavily overcast hours pin
down the demand-model coefficients with zero interference, while daytime
hours (where PV output varies a lot day to day from cloud cover, at fixed
calendar/weather conditions) pin down the self-consumption effect — one
regression, not two sequential models. Both of its built-in falsification
checks (a feed-in category that structurally cannot self-consume; wind
potential, which has no behind-the-meter channel at all) came back
significant rather than the expected zero — investigated rather than
brushed aside: the PV category split turned out to be a genuine
non-identification problem (the two candidate regressors correlate at
0.95), while wind's effect survived a direct test of the obvious
alternative explanation (a richer temperature spline barely changed it)
and is more likely a real, different phenomenon — price-responsive
industrial demand rising during cheap, high-wind hours — that the test's
own premise didn't anticipate. The aggregate specification's self-consumption
estimate (~12% of national PV potential, net of the ~40% of the fleet
that's registered full-feed-in and structurally can't self-consume at
all) is this notebook's trustworthy headline number.

**Curtailment estimation** (notebook 39) calibrates a curtailment-rate-vs-
oversupply curve on wind's own gap — clean because wind has no
behind-the-meter term to confound it — using a **potential-based**
oversupply proxy (`P_total/D_true_hat`, not the observed-generation-based
proxy from the wind-offshore workstream's own bias-driver notebook, which
understates true oversupply exactly when curtailment is largest) and
transfers that curve to PV. The result reframes what's driving PV's gap
against SMARD: of its ~2177 MW average gap, ~1653 MW (76%) is predicted
curtailment — more than self-consumption, which wasn't obvious going in.
The residual left over correlates with the self-consumption-registered
capacity share at 0.643, though both series simply trend upward together
over 2019-2025, so that number is suggestive rather than a tight
validated match.

**The residual-load backtest** (notebook 40), trained on 2019-2023 and
evaluated out-of-time on 2024-2025 against realized residual load
(computable directly from SMARD, no new data needed), shows the full
chain roughly **halves the MAE** of the naive baseline that skips all of
this hidden-variable estimation (4,856 MW vs. 10,560 MW) and cuts the bias
by roughly 5x (-1,936 MW vs. -9,750 MW), with a real but smaller
correlation improvement (0.915 vs. 0.905) — consistent with the demand and
curtailment corrections fixing the *level* more than the *day-to-day
pattern*, which both approaches already capture reasonably well from
shared weather inputs. (Caught and fixed while building this comparison:
the curtailment curve originally returned `NaN` for any out-of-time hour
whose oversupply proxy fell outside the training period's own range —
4.1% of the test period — silently dropped rather than handled; fixed in
`pecdr/residual_load.py` by clipping into the fitted range, the same
graceful-degradation behavior a tree-based model gives for free.)

**Does the structure actually earn its keep, though?** (notebook 42)
splits "does weather information help" from "does explicitly modeling
unobserved quantities help *on top of* that," with four more points on
the same out-of-time backtest: a calendar-only floor with no weather at
all, the same features as the full model fed into one flat linear
regression with no structural decomposition, the same features again fit
with LightGBM, and a capacity-factor-rescaled version of the LightGBM
model. The answers are not what a reader might expect: adding
raw weather-derived potential without correcting it for curtailment
(the naive baseline) is *no better than no weather information at all* in
absolute-error terms (10,560 MW MAE vs. 10,284 MW for calendar-only) —
correlation improves a lot (0.905 vs. 0.486) but the uncorrected bias
overwhelms that benefit. More surprisingly, a plain linear regression
given the *same inputs* as the full structural model, with none of the
hand-built equations, does *better* than the structural model on this
backtest (MAE 4,177 MW, corr 0.941, vs. the structural model's 4,856 MW
/ 0.915) — in this setting, most of the benefit comes from having the
right features at all, not from the specific structural machinery used to
extract them. The LightGBM version underperforms the linear one, for a
concrete, checked reason rather than a mystery: installed capacity grew
throughout 2019-2025, so `years_since_start` has 100% of test-period rows
beyond the training range and `P_wind_off_mw` has 20% — tree-based models
cannot extrapolate a trend past what they were trained on, while a linear
trend term does so by construction.

**Does capacity-factor rescaling fix LightGBM's handicap, as expected?**
Partially, not fully. A sixth model swaps `P_i(t)` for capacity factor
(`P_i(t)/Capacity_i(t)`, bounded regardless of fleet size) as LightGBM's
features and predicts `ResidualLoad(t)/TotalCapacity(t)` instead of MW
directly, reconstructing the final MW prediction by multiplying back by
the actual (looked-up, not modeled) capacity at the test time. This
narrows the gap substantially (MAE 6,714 → 5,294 MW) — confirming the
extrapolation story really was the mechanism — but doesn't reach M3 or
even M2. Checked directly rather than left unexplained: the model's error
*in the normalized domain* is tiny and essentially unbiased in-sample
(~0.000), but picks up a small out-of-sample bias (~0.006) on the test
period, and that small bias gets **amplified** when multiplied back by
`TotalCapacity_mw` to reconstruct MW — confirmed by a 0.44 correlation
between the signed MW error and total capacity at test time. Rescaling
fixes the tree's *input*-side extrapolation problem; it trades in a
smaller, different amplification effect on the *output*-reconstruction
side instead.

### Roadmap: residual-load notebooks

| Notebook | What it shows |
|---|---|
| [Walkthrough](residual_load_walkthrough.md) | Start here: the problem, the mental model, the equations, and the evidence, taught in order |
| [Equations](curtailment_system_equations.md) | The full notation and system of equations this section implements |
| [38: Estimating gross demand](../notebooks/38_estimate_gross_demand.ipynb) | The demand regression, both falsification checks (and why neither passed cleanly), the temperature-response shape, and the summer/winter intraday profile showing the self-consumption dip being filled in |
| [39: Estimating curtailment](../notebooks/39_estimate_curtailment.ipynb) | The wind-calibrated curtailment curve, the onshore-vs-offshore shape robustness check, and the PV gap decomposition into curtailment vs. self-consumption |
| [40: Forecasting residual load](../notebooks/40_forecast_residual_load.ipynb) | Out-of-time backtest against realized residual load, full model vs. naive baseline |
| [41: Illustrating the model](../notebooks/41_illustrate_residual_load_model.ipynb) | Ground-truth potential-vs-observed charts and the PV gap decomposition, in representative time windows |
| [42: Does structure earn its keep?](../notebooks/42_compare_model_flexibility.ipynb) | Six models on the same backtest — calendar-only, naive, full structural, plain linear on the same features, LightGBM, and capacity-factor-rescaled LightGBM — isolating whether the improvement comes from having weather-derived features at all, from the structural extraction of unobserved quantities, or from how a flexible model's inputs are scaled |

What isn't resolved yet: the price-responsive-demand confound flagged in
notebook 38, the un-detrended self-consumption cross-check in notebook 39,
and validating the curtailment estimate against real Redispatch 2.0 data
(available from October 2021, deliberately deferred — see the equations
page's discussion of why real congestion data can only validate an
already-estimated model, never serve as a live forecasting input).
