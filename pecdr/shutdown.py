"""Simplified storm-shutdown model: probability-of-shutoff near the cutout
threshold, instead of PECD's per-turbine hysteresis state machine.

PECD's own model (Murcia et al. 2021, per the PUG) tracks each turbine's
individual shutdown/restart state as 10-minute wind speeds cross different
thresholds, with hysteresis so a restart only happens once wind speed drops
well below the shutdown threshold. Replicating that needs per-turbine
storm-cutoff data (WindPowerNet-specific, not available here) and
per-timestep state carried across the whole simulation -- both
intentionally out of scope (see project discussion: "assign a certain
probability of being shut off... if the wind is close enough to the
threshold").

This applies a deterministic *expected-value* derate rather than a
stochastic per-plant draw: multiplying capacity factor by
(1 - shutdown_probability) approximates, in aggregate, what a
random-draw-per-plant simulation would average to over many plants --
appropriate since the target here is capacity-factor comparison against
PECD's own long-run-average product, not a single-realization forecast.
"""

import numpy as np

RAMP_START_MS = 20.0  # wind speed at which shutdown probability starts rising above 0
CUTOUT_MS = 25.0  # wind speed at which shutdown probability reaches 1 (matches the generic power curve's own cut-out)


def shutdown_probability(wind_speed_ms: np.ndarray, ramp_start: float = RAMP_START_MS, cutout: float = CUTOUT_MS) -> np.ndarray:
    """Linear ramp from 0 (at `ramp_start`) to 1 (at `cutout`), 0 below and 1 above."""
    p = (wind_speed_ms - ramp_start) / (cutout - ramp_start)
    return np.clip(p, 0.0, 1.0)


def apply_shutdown_derate(capacity_factor: np.ndarray, wind_speed_ms: np.ndarray, ramp_start: float = RAMP_START_MS, cutout: float = CUTOUT_MS) -> np.ndarray:
    """Derate capacity factor by (1 - shutdown probability)."""
    return capacity_factor * (1 - shutdown_probability(wind_speed_ms, ramp_start, cutout))
