"""PECD/ERA5 0.25-degree grid geometry helpers.

Same logic as ~/research/mastr-power-capacities-germany's `mpg/grid.py`,
duplicated here rather than imported cross-repo per the template's
per-project self-containment convention (see pecdr/paths.py's
`mastr_project_path` docstring for the one place this project does read
another repo's files directly -- its already-processed data outputs, not
its code).
"""

import numpy as np


def nearest_grid_index(values: np.ndarray, grid: np.ndarray) -> np.ndarray:
    """Index of the nearest point in a regularly-spaced 1-D `grid` for each of `values`."""
    step = grid[1] - grid[0]
    idx = np.rint((values - grid[0]) / step).astype(int)
    return np.clip(idx, 0, len(grid) - 1)
