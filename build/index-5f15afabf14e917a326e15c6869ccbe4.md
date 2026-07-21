---
title: Introduction
---

# Replicating PECD: physically-motivated features for forecasting Germany's power market

## The goal

The wider goal behind this project is forecasting the DE-LU bidding zone's
headline variables: wind generation, PV generation, and load (demand). This
project itself is one building block toward that goal, not the end in
itself — see [How this project fits the wider goal](#project-fit) below.

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
| [11: Full-year validation](../notebooks/11_analyse_wind_onshore_full_year.ipynb) | Steps 3-4, extended | Same comparison across all 8,784 hours of 2020 rather than two snapshots — confirms the high-wind bias is systematic, not a fluke of which hours were picked |
| [12: Comparing all three approaches](../notebooks/12_compare_all_approaches.ipynb) | Step 5 | Brings in SMARD's actual net generation as real-world ground truth; shows this project's replication tracks the true temporal pattern much better than the simple-physics approach (corr 0.981 vs. 0.930), while still carrying the same high-wind over-estimate — now confirmed against reality, not just against PECD's own numbers |

What isn't built yet, and is deliberately visible as a gap rather than
papered over: wake-effect/layout correction (step 5 of PECD's own
methodology), curtailment, outages, and behind-the-meter self-consumption
— none of these have a ground-truth series to check against, which is
exactly why they're absent from every approach compared here, not only
this project's.
