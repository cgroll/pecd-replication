"""CF-conditional bias correction via isotonic regression.

Fits a monotonic calibration curve mapping a modeled capacity factor to a
corrected one, using the empirical relationship between the model and
ground truth over some training period. Monotonic (not, say, a free
regression) because the bias this project has found is itself monotonic in
CF level (see `pipeline/22_analyse_bias_drivers.py`) -- a calibration curve
that could non-monotonically re-order CF values would fit noise, not the
underlying effect.
"""

import numpy as np
import pandas as pd
from scipy.optimize import isotonic_regression


def fit_isotonic_correction(model_cf: pd.Series, truth_cf: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """Fit `truth_cf ~ model_cf` as a monotonic step function.

    Returns `(x, fitted_y)`, both sorted by `model_cf` -- feed to
    `apply_correction` to map new model CF values through the same curve.
    """
    order = np.argsort(model_cf.to_numpy())
    x_sorted = model_cf.to_numpy()[order]
    y_sorted = truth_cf.to_numpy()[order]
    fitted_y = isotonic_regression(y_sorted).x
    return x_sorted, fitted_y


def apply_correction(x_sorted: np.ndarray, fitted_y: np.ndarray, new_model_cf: pd.Series) -> pd.Series:
    """Map `new_model_cf` through a fitted calibration curve (see
    `fit_isotonic_correction`), clamping to the fitted range outside it --
    the standard quantile-mapping convention for out-of-training values.
    """
    corrected = np.interp(new_model_cf.to_numpy(), x_sorted, fitted_y)
    return pd.Series(corrected, index=new_model_cf.index)
