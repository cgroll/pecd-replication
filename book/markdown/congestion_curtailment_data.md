---
title: "Congestion data: how much curtailment actually happens"
---

# Congestion data: how much curtailment actually happens

Every curtailment number in the residual-load chapter that follows this
one is *estimated* — a curve fit to wind's own potential-vs-observed gap,
transferred to PV under an assumption that's never been checked against
real data. This chapter comes first for a reason: before trusting any
model of curtailment, it's worth looking at real ground truth and building
a feel for how much of it there actually is, and when.

## Where this data comes from

Since July 2022, [SMARD](https://www.smard.de) — the Bundesnetzagentur's
electricity market data platform, already this project's source for
generation and load — publishes monthly volumes of feed-in that was
adjusted under Germany's **Redispatch 2.0** congestion-management regime,
broken down by energy carrier (wind onshore, wind offshore, solar, and the
conventional sources). Two directions are published: **reductions**
(feed-in cut below what a plant could have produced — curtailment) and
**increases** (counter-trading up-regulation, plants asked to produce
*more* to compensate). Both are pulled by `pecdr/smard_redispatch.py` and
saved by `pipeline/43_download_redispatch_by_source.py`.

Unlike the rest of this project's SMARD data, this series has no
documented API — the frontend multiplexes roughly 130 unrelated chart
series into one shared CSV, selected client-side by a `chart_id` column.
The download module re-derives the CSV's current URL from the live
[redispatch topic page](https://www.smard.de/page/en/topic-article/212250/214114/redispatching-by-energy-source)
each run (rather than hardcoding it), since that URL is a CMS resource ID
that can change whenever the site is republished.

## What this data can and can't tell us

**It can**: give real, technology-labeled, monthly curtailment volumes
covering July 2022 onward, at national scale. That's enough to check
relative magnitudes between technologies and broad seasonal patterns.

**It can't**: resolve anything at hourly or regional detail — there's no
way to see *which hour* or *which grid region* drove a given month's
number, so it can't directly recalibrate the hourly oversupply-proxy curve
the residual-load model uses. It also only covers **redispatch**
(grid-operator-ordered curtailment) — market-based curtailment, where a
plant operator voluntarily cuts output because of negative prices, is a
separate mechanism entirely and doesn't appear in this data at all. And it
starts in July 2022, so it can't cover the earlier years of this project's
2019-2025 backtest.

## What the data shows

```{figure} ../../output/images/44_curtailment_by_source_over_time.png
:name: fig-congestion-by-source-over-time
Monthly redispatch curtailment (reduction) volume by energy source, July 2022 onward.
```

Wind — onshore and offshore together — dominates curtailment volume, and
both show a clear seasonal rhythm: more curtailment in the windier
autumn/winter months. PV's curtailment is smaller in absolute terms but
just as clearly seasonal, tracking its own generation season instead.

```{figure} ../../output/images/44_cumulative_curtailment_by_source.png
:name: fig-congestion-cumulative-by-source
Total curtailed energy per source over the full period.
```

The standout finding: **wind offshore's cumulative curtailment (16,108 GWh)
is actually larger than wind onshore's (12,873 GWh)**, despite an
installed offshore fleet only about a seventh the size of onshore's
(~9.2 GW vs. ~63.1 GW in 2025). Per MW installed, that's roughly **8-9x
more curtailment for offshore than onshore** — consistent with known
transmission bottlenecks moving generation from the northern coast to load
centers further south and west. This project's residual-load model
currently pools onshore and offshore wind into a single curtailment curve
(notebooks 39/40/42) — this asymmetry is a real pattern that pooling
discards.

```{figure} ../../output/images/44_seasonal_curtailment_pattern.png
:name: fig-congestion-seasonal-pattern
Average curtailment by calendar month, 2022-2026.
```

As a sanity check on the data's own labeling: renewable sources sit at (or
extremely close to) 100% "reduction" share of their total redispatch
volume, while conventional/flexible sources (hard coal, gas, pumped
storage) split much more evenly between reductions and increases — exactly
what the reduction/increase terminology should imply if it means what it
says.

## What's next

This chapter deliberately stops at description — no tie-back to this
project's own curtailment estimates. The natural next question, left open
here on purpose, is whether this real data actually supports the
wind-to-PV curve-transfer assumption the residual-load model relies on, or
whether it argues for a PV-specific curve instead. See
[the residual-load walkthrough](residual_load_walkthrough.md) and
[the system-of-equations reference](curtailment_system_equations.md) for
where that assumption is used and why it was made in the first place.
