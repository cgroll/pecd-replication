---
title: "Accounting for curtailment, self-consumption, and storage"
---

# Accounting for curtailment, self-consumption, and storage: a system of equations

## Why this page exists

The wind-offshore workstream (see [Wind offshore replication](index.md#wind-offshore-replication))
found a persistent positive bias against SMARD's actual generation that
survives fixing capacity accounting (notebook 35) and correlates cleanly
with system-wide renewable oversupply (notebook 36) — evidence for
curtailment, but not proof, and not yet separated from the other candidate
explanations (outages, model error) or connected to the solar
workstream's own open self-consumption question (`26`'s takeaways: bias
and self-consumption share grow together over time, "can't separate...
from these two panels alone"). The wider project goal is a **day-ahead
residual-load forecast**, which needs two things that are never directly
observed: potential renewable generation net of curtailment, and gross
(not just grid-metered) power demand.

This page fixes notation once, then writes down every equation relating
potential generation, hidden losses, what's actually observed, demand, and
storage — as a single reference for what's being estimated, from what,
and why.

## Notation

### Indices

| Symbol | Meaning |
|---|---|
| `t` | Hour (the project's native resolution throughout) |
| `i` | Technology index, `i ∈ {wind_on, wind_off, pv}` |

### Potential generation (hidden, modeled from weather + capacity)

| Symbol | Meaning |
|---|---|
| `P_i(t)` | This project's own modeled weather-driven technical potential for technology `i`, before any real-world loss |
| `P_total(t)` | `= P_wind_on(t) + P_wind_off(t) + P_pv(t)`, total renewable potential |
| `P_pv,full_feed_in(t)` | PV potential attributable only to MaStR units registered under the `full_feed_in` category (zero self-consumption by regulatory construction) |
| `P_pv,self_consumption(t)` | PV potential from the remaining (self-consumption-registered) units |

### Hidden losses (between potential and what's actually produced)

| Symbol | Meaning |
|---|---|
| `L_repair,i(t)` | Loss from technical unavailability: storm damage, cable faults, scheduled maintenance. Price- and grid-signal-independent |
| `L_price,i(t)` | Voluntary curtailment during negative prices (not a grid-operator order, not in any published redispatch dataset) |
| `L_congestion,i(t)` | Grid-operator-enforced curtailment (Redispatch 2.0 / Einspeisemanagement) — the one loss category with published official data, and only from October 2021 |
| `ε_i(t)` | This project's own model error — `P_i` itself being wrong. Kept separate from the above on principle, even though empirically indistinguishable from real losses without independent validation |
| `BTM_i(t)` | Behind-the-meter self-consumption of technology `i`'s own production. `≈0` for both wind technologies (Germany's wind fleet is ~100% utility-scale, always grid-connected) — essentially a PV-only term |

### The produced-but-not-yet-gridded split (PV only)

| Symbol | Meaning |
|---|---|
| `Produced_i(t)` | What's physically generated after real-world losses, before the grid/behind-the-meter split |
| `SelfUse_pv(t)` | PV output self-consumed in the same hour it's generated |
| `Charge_btm(t)`, `Discharge_btm(t)` | Flows into/out of a behind-the-meter battery paired with rooftop PV |
| `SOC_btm(t)` | Behind-the-meter battery state of charge — genuinely hidden; MaStR's `self_consumption_with_storage` category flags which *capacity* has this arrangement, not its state at any hour |

### Observed (on the grid, from SMARD)

| Symbol | Meaning |
|---|---|
| `G_i(t)` | Grid-injected generation for technology `i` |
| `G_other(t)` | Grid-injected generation from everything dispatch-driven rather than weather-driven (fossil, biomass, hydro, nuclear until 2023, geothermal) — no "potential" modeled for this bucket |
| `G_storage,charge(t)`, `G_storage,discharge(t)` | Grid-scale storage (pumped hydro, increasingly grid batteries). **Not hidden** — SMARD already publishes this; not yet pulled into this project, but straightforward via `pecdr/smard.py`'s existing `Variable` enum |
| `NetImport(t)` | Observed cross-border physical flow |

### Demand

| Symbol | Meaning |
|---|---|
| `D_grid(t)` | SMARD's published load: only what's drawn *from the public grid* |
| `D_btm(t)` | Behind-the-meter demand met by local self-consumption — invisible on both the generation and demand side simultaneously |
| `D_true(t)` | Gross demand, `= D_grid(t) + D_btm(t)` — never directly observed |

### The demand model (estimated)

| Symbol | Meaning |
|---|---|
| `D̂_true(t; θ)` | The fitted estimate of gross demand |
| `dow(t)` | Day-of-week category |
| `Holiday(t)` | Public-holiday indicator |
| `T(t)` | Germany NUTS0 area-average 2m temperature (`pecd_temperature_de.parquet`) — PECD's population-weighted product (`TAW`) exists but only at the pan-European "synchronous zone" level, unusable for isolating Germany, hence area-average here |
| `trend(t)` | A slow-moving term for structural change over 2019-2025 (e.g. 2022's demand destruction from the energy-price crisis) |
| `k` | Self-consumption coefficient: the fraction of `P_pv(t)` self-consumed rather than exported, as fit by the demand regression (or `k_full_feed_in`, `k_self_consumption` if fit separately per feed-in category — `k_full_feed_in` should come out ≈0 as a built-in falsification check) |

### The oversupply proxy and curtailment model

| Symbol | Meaning |
|---|---|
| `Gap_i(t)` | `= P_i(t) - G_i(t)`, the one directly computable quantity from this project's existing outputs |
| `OversupplyProxy_obs(t)` | `= (G_wind_on+G_wind_off+G_pv)(t) / D_grid(t)` — the proxy used in notebooks 22/36. Built from already-curtailed observed values, so it understates true oversupply exactly when curtailment is largest |
| `OversupplyProxy_potential(t)` | `= P_total(t) / D̂_true(t)` — the corrected version, built from potential and gross demand instead, free of that attenuation bias |
| `L̂(·)` | The fitted curtailment-vs-oversupply function, calibrated on wind's own clean gap (no `BTM` term to contaminate it), then applied to PV |

### The forecasting target

| Symbol | Meaning |
|---|---|
| `ResidualLoad(t)` | `= D_grid(t) - Σ_i G_i(t)`, the realized/observed quantity |
| `ResidualLoad_hat(t)` | `= D̂_true(t) - (P_total(t) - L̂(t))`, the forecastable estimate — everything on the right is knowable ahead of a day-ahead forecast from weather and calendar |

## The equations

**1. Per-technology physical balance.** What potential generation decomposes into: real-world losses plus whatever was actually produced, plus this project's own model error.

$$
P_i(t) = L_{repair,i}(t) + L_{price,i}(t) + L_{congestion,i}(t) + Produced_i(t) + \varepsilon_i(t)
$$

**2. The produced/behind-the-meter split.** What's physically produced either reaches the public grid or is used behind the meter.

$$
Produced_i(t) = G_i(t) + BTM_i(t)
$$

For wind, `BTM_i(t) ≈ 0` structurally — this is what made the offshore
bias-driver analysis (notebook 36) a clean read on curtailment specifically,
with no self-consumption confound to separate out.

**3. Behind-the-meter self-consumption, with battery time-shifting (PV only).** Same-hour self-use plus whatever a paired battery discharges, minus whatever it charges.

$$
BTM_{pv}(t) = SelfUse_{pv}(t) + Discharge_{btm}(t) - Charge_{btm}(t)
$$

**4. Behind-the-meter battery state.** The battery's own stock-flow recursion — this is what turns self-consumption from a same-hour cancellation into a time-shifted one.

$$
SOC_{btm}(t) = SOC_{btm}(t-1) + Charge_{btm}(t) - Discharge_{btm}(t) - loss_{btm}(t)
$$

**5. System balance.** An accounting identity, true by construction — not something to estimate. Whatever the grid draws must equal everything injected into it.

$$
D_{grid}(t) = \sum_i G_i(t) + \big(G_{storage,discharge}(t) - G_{storage,charge}(t)\big) + G_{other}(t) + NetImport(t)
$$

**6. Gross demand.** Grid-metered load plus the invisible behind-the-meter piece.

$$
D_{true}(t) = D_{grid}(t) + D_{btm}(t)
$$

`D_btm(t)` is met by `BTM_i(t)` first (mostly PV); any shortfall is drawn
from the grid (already inside `D_grid`); any BTM surplus beyond local
demand is either exported (counted in `G_i`) or wasted.

**7. The gross-demand regression.** This is the estimable link between the hidden demand side and what's observed: grid-metered load equals a calendar/weather-driven demand model minus PV self-consumption, plus noise. Linear in every unknown, solvable with plain OLS — nighttime and heavily overcast hours (`P_pv(t)≈0`) pin down the demand-model coefficients with no self-consumption interference at all, since the `-k·P_pv(t)` term vanishes there; daytime hours (where `P_pv(t)` varies a lot at fixed calendar/weather conditions, due to cloud cover) then pin down `k`.

$$
D_{grid}(t) = \underbrace{\beta_0 + \beta_{dow}(t) + \beta_{holiday}\!\cdot\!Holiday(t) + f_{temp}(T(t)) + trend(t)}_{\hat D_{true}(t;\theta)} \; - \; k \cdot P_{pv}(t) + \varepsilon(t)
$$

**7a. Refinement: split by feed-in category.** `solar_capacity_by_pv_category_month` already tracks which capacity is registered `full_feed_in` (required to export 100%, no self-consumption possible) versus self-consumption categories. Fitting separate coefficients gives a built-in falsification test.

$$
D_{grid}(t) = \hat D_{true}(t;\theta) - k_{full\_feed\_in} \cdot P_{pv,full\_feed\_in}(t) - k_{self\_consumption} \cdot P_{pv,self\_consumption}(t) + \varepsilon(t)
$$

`k_full_feed_in` should come out statistically indistinguishable from zero; if it doesn't, that's a sign of a modeling problem, not a real effect. (A further, not-yet-formalized refinement: self-consumption should *saturate* — a household can't self-consume more than its own local demand — so a piecewise-linear or spline term in `P_pv(t)` is more physically honest than a single linear `k`, and still OLS-solvable.)

**8. The naive oversupply proxy (what notebooks 22/36 actually used), and why it's biased.** Built entirely from observed values — which is exactly the problem, since at the hours with the most curtailment, the observed numerator is already suppressed by that same curtailment.

$$
OversupplyProxy_{obs}(t) = \frac{G_{wind\_on}(t) + G_{wind\_off}(t) + G_{pv}(t)}{D_{grid}(t)}
$$

**9. The corrected, potential-based oversupply proxy.** Curtailment decisions respond to the *true* oversupply situation, not the already-curtailed observed one — so the proxy driving `L̂` should be built from potential and gross demand instead.

$$
OversupplyProxy_{potential}(t) = \frac{P_{total}(t)}{\hat D_{true}(t)}
$$

**10. The curtailment model, calibrated on wind and extrapolated to PV.** Wind's own gap has no `BTM` term to separate out, so it's a clean training signal for how curtailment responds to oversupply; applying that same fitted relationship to PV's own oversupply hours predicts PV's curtailment without needing to observe it directly.

$$
Gap_{wind,i}(t) \approx L_{repair,i}(t) + L_{price,i}(t) + L_{congestion,i}(t) + \varepsilon_i(t), \qquad \hat L(t) = \hat L\big(OversupplyProxy_{potential}(t)\big)
$$

**10a. The residual left over for PV, once curtailment is subtracted out.** Whatever remains of PV's own gap after removing the wind-calibrated curtailment prediction is an estimate of PV's self-consumption plus its own repair losses and model error.

$$
Gap_{pv}(t) - \hat L_{pv}(t) \;\approx\; BTM_{pv}(t) + L_{repair,pv}(t) + \varepsilon_{pv}(t)
$$

Cross-checkable against `solar_capacity_by_pv_category_month`: if this
residual tracks the self-consumption-registered capacity share over time,
that's independent corroboration it's really `BTM`, not `ε` or
`L_repair`. `L_repair` and `ε` stay bundled throughout this whole chain —
genuinely unidentifiable further without real outage data or an
independently validated model, neither of which this project has.

**11. The forecasting target.** Realized residual load is a pure accounting identity from already-observed values — nothing to estimate. The forecastable version substitutes gross demand and potential-minus-estimated-curtailment for the observed quantities, so it can be computed ahead of time from weather and calendar alone.

$$
ResidualLoad(t) = D_{grid}(t) - \sum_i G_i(t)
$$

$$
\widehat{ResidualLoad}(t) = \hat D_{true}(t) - \big(P_{total}(t) - \hat L(t)\big)
$$

Note that `BTM` doesn't appear in the forecast formula at all — it cancels
out of residual load exactly as it does in the realized version (the
self-consumed MWh is absent from both published generation and published
demand equally). It still earned its place in equation 7: without the
`-k·P_pv(t)` term, `D̂_true(t)` itself would be biased by mistaking the
solar self-consumption dip for a real demand pattern. `BTM` matters for
getting the demand model right; it drops out of the final target.

## A dead end worth flagging, not just a live lead

An earlier idea was to use realized fossil generation + net imports as a
third, BTM-free channel to estimate `L_price + L_congestion` for the whole
system independently of the per-technology gaps. Writing the system
balance out at both potential and actual renewable output kills this:

$$
Gap_{total}(t) \equiv \sum_i \big(P_i(t) - G_i(t)\big)
= \big(D_{grid}(t) - \textstyle\sum_i P_i(t)\big) - \big(D_{grid}(t) - \sum_i G_i(t)\big)
$$

which reduces to `Gap_total(t) = Gap_total(t)` — tautological. Without an
actual dispatch/merit-order model, "counterfactual fossil+import" is *defined*
as whatever the residual demands, so it adds no information beyond `P` and
`G` directly. Fossil/import data isn't worthless — it can show whether
must-run constraints are binding (fossil pinned at a floor, forcing
curtailment as the only release valve) — but that's mechanism evidence,
not a new decomposition axis, and shouldn't be oversold as one.

## What real congestion data can and can't add

Checked directly by building a download pipeline against it, not just
assumed: SMARD publishes monthly redispatch-adjusted feed-in volumes by
energy carrier (wind onshore, wind offshore, solar, and the conventional
sources), covering July 2022 onward — see
[notebook 44](../notebooks/44_analyse_congestion_curtailment.ipynb) for the full
walkthrough and `pecdr/smard_redispatch.py`/`pipeline/43_download_redispatch_by_source.py`
for how it's fetched. That's real ground truth for `L_congestion`
specifically, per technology, but with real limits: (1) it starts July
2022, so it can't cover this project's full 2019-2025 backtest; (2) it's
**monthly and national-only** — no hour-of-day or grid-region detail; (3)
checked directly (not assumed), it is **not** a clean redispatch-only
figure — it's TSO+DSO combined and folds in countertrading and grid-reserve
volume alongside redispatch proper (see
[notebook 46](../notebooks/46_attribute_ambiguous_redispatch_entities.ipynb)); it never
captures `L_price` (voluntary, market-based curtailment from negative
prices) or `L_repair` (not a redispatch measure at all). See
[notebook 48](../notebooks/48_analyse_offshore_gap_vs_curtailment.ipynb) for a direct
check of how much of offshore wind's raw potential-observed gap negative
prices explain once real redispatch curtailment is already accounted for
— not much, on top of curtailment's own share.

A second, per-measure source (netztransparenz.de's live Redispatch export)
does give real timestamps and per-plant names, but turned out to carry a
clean technology label only for offshore wind — onshore wind and PV are
almost entirely hidden behind anonymous substation/cluster codes, so it
doesn't supply the clean per-technology, per-hour recalibration input it
initially looked like it would. See
[notebook 45](../notebooks/45_explore_redispatch_measures.ipynb) and
[notebook 46](../notebooks/46_attribute_ambiguous_redispatch_entities.ipynb) for what it
actually offers (mainly: attributable *shape*, not yet reliable absolute
levels) and how the two sources' totals were reconciled.

Because tomorrow's curtailment is never observable at forecast time
regardless, `L̂(t)` in equation 11 has to be an estimated function of
forecastable inputs either way — real congestion data's role is
**validating or recalibrating that estimated function against history**,
not supplying it a live input. The one thing this monthly data already
makes checkable: it shows wind offshore curtailed roughly 8-9x more
heavily per MW installed than onshore (see the congestion data chapter) —
a real technology-specific asymmetry that the pooled onshore+offshore
curtailment curve in notebooks 39/40/42 currently discards.
