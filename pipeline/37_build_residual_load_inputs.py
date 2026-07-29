"""Build the consolidated hourly input panel for the residual-load workstream.

Pure data processing -- no charts. Converts every modeled capacity-factor
series this project already has into absolute MW potential, joins in
SMARD's grid-metered load, Germany's area-average temperature, and
calendar features -- one row per hour, everything the gross-demand
regression (pipeline/38) and the curtailment estimation (pipeline/39) need.

See `book/markdown/curtailment_system_equations.md` for the full system of
equations this feeds into.
"""

import pandas as pd

from pecdr.capacity_weighting import capacity_weighted_cf, hourly_capacity_by_zone, total_hourly_capacity
from pecdr.domain import FULL_YEAR_BACKTEST_YEARS
from pecdr.paths import ProjPaths
from pecdr.residual_load import calendar_features, degree_days, potential_mw, wind_potential_mw

paths = ProjPaths()
paths.ensure_directories()

period_start, period_end = FULL_YEAR_BACKTEST_YEARS[0], FULL_YEAR_BACKTEST_YEARS[-1]

# %% Grid-metered load (D_grid)
target_panel = pd.read_parquet(paths.target_panel_file)
d_grid = target_panel.loc[period_start:period_end, "load"].rename("D_grid_mw")

# %% Wind potential (P_wind_on, P_wind_off), MW -- each year's own plant-panel capacity
wind_onshore_capacity_by_year = {
    year: pd.read_parquet(paths.wind_onshore_plant_panel_by_year_file(year))["capacity_mw"].sum() for year in FULL_YEAR_BACKTEST_YEARS
}
wind_offshore_capacity_by_year = {
    year: pd.read_parquet(paths.wind_offshore_plant_panel_by_year_file(year))["capacity_mw"].sum() for year in FULL_YEAR_BACKTEST_YEARS
}
wind_onshore_cf = pd.read_parquet(paths.wind_onshore_full_year_cf_file)["national"]
wind_offshore_cf = pd.read_parquet(paths.wind_offshore_full_year_cf_file)["national"]
p_wind_on = wind_potential_mw(wind_onshore_cf, wind_onshore_capacity_by_year).rename("P_wind_on_mw")
p_wind_off = wind_potential_mw(wind_offshore_cf, wind_offshore_capacity_by_year).rename("P_wind_off_mw")

# Installed capacity, hourly (step function per year) -- exposed separately
# from the MW potential above so downstream models can use capacity factor
# (P_i(t)/Capacity_i(t)) instead of absolute MW where a trend-free feature
# matters (e.g. tree-based models, which can't extrapolate a growing-
# capacity trend the way a linear term does -- see pipeline/42).
capacity_wind_on = pd.Series(
    wind_onshore_cf.index.year.astype(str).map(wind_onshore_capacity_by_year), index=wind_onshore_cf.index, dtype=float, name="Capacity_wind_on_mw"
)
capacity_wind_off = pd.Series(
    wind_offshore_cf.index.year.astype(str).map(wind_offshore_capacity_by_year), index=wind_offshore_cf.index, dtype=float, name="Capacity_wind_off_mw"
)

# %% Solar potential (P_pv), MW, national -- capacity-weighted across (technology, NUTS2) cells
own_solar_cf = pd.read_parquet(paths.own_solar_full_year_cf_file)
own_solar_cf.columns = [f"{technology}_{nuts2}" for technology, nuts2 in own_solar_cf.columns]
solar_capacity_by_nuts2_month = pd.read_parquet(paths.solar_capacity_by_nuts2_month_file)
solar_capacity_by_nuts2_month["zone"] = solar_capacity_by_nuts2_month["pecd_technology"].astype(str) + "_" + solar_capacity_by_nuts2_month["nuts2_region"]
p_pv = potential_mw(own_solar_cf, solar_capacity_by_nuts2_month, zone_col="zone").rename("P_pv_mw")
capacity_pv = total_hourly_capacity(solar_capacity_by_nuts2_month, own_solar_cf.index, zone_col="zone").rename("Capacity_pv_mw")

# %% Solar potential split by MaStR feed-in category -- full_feed_in has zero
# self-consumption by regulatory construction; the rest (self-consumption
# with/without storage, plus "unknown", conservatively not assumed
# self-consumption-free) is the category that should show a real effect.
solar_capacity_by_category = pd.read_parquet(paths.solar_capacity_by_pv_category_month_file)
national_solar_cf = capacity_weighted_cf(own_solar_cf, solar_capacity_by_nuts2_month, zone_col="zone")
category_capacity_hourly = hourly_capacity_by_zone(solar_capacity_by_category, own_solar_cf.index, zone_col="pv_category")
full_feed_in_capacity = category_capacity_hourly["full_feed_in"]
self_consumption_capacity = category_capacity_hourly.drop(columns="full_feed_in").sum(axis=1)
p_pv_full_feed_in = (national_solar_cf * full_feed_in_capacity).rename("P_pv_full_feed_in_mw")
p_pv_self_consumption = (national_solar_cf * self_consumption_capacity).rename("P_pv_self_consumption_mw")

# %% Temperature (T) and calendar features
temperature = pd.read_parquet(paths.pecd_temperature_file).loc[period_start:period_end, "DE"].rename("temperature_c")
heating_degree, cooling_degree = degree_days(temperature)
heating_degree, cooling_degree = heating_degree.rename("heating_degree"), cooling_degree.rename("cooling_degree")

# %% Combine, restrict to the common backtest period, save
panel = pd.concat(
    [
        d_grid,
        p_wind_on,
        p_wind_off,
        p_pv,
        p_pv_full_feed_in,
        p_pv_self_consumption,
        capacity_wind_on,
        capacity_wind_off,
        capacity_pv,
        temperature,
        heating_degree,
        cooling_degree,
    ],
    axis=1,
).loc[period_start:period_end]
panel = panel.join(calendar_features(panel.index))
panel = panel.dropna()

panel.to_parquet(paths.residual_load_inputs_file)
print(f"Saved {len(panel):,} hourly rows, {panel.shape[1]} columns -> {paths.residual_load_inputs_file}")
print(panel.describe())
