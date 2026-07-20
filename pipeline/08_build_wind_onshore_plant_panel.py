"""Build the active onshore wind plant panel: one row per unit, with
capacity, hub height, rotor diameter, turbine model, coordinates, nearest
0.25-degree grid cell, and dominant PEON zone.

Pure data processing script -- no visualizations. Joins
~/research/mastr-power-capacities-germany's unit-level capacity events
against its (this project's) new wind_technical_detail export, restricted to
onshore units (region_code not starting with "DEZZ", MaStR's offshore
pseudo-region prefix) still active as of today (no `final_shutdown_date`) --
this project's replication targets a snapshot fleet, not a full historical
commissioning/decommissioning panel like the source project's own monthly
capacity series.
"""

import pandas as pd

from pecdr.grid import nearest_grid_index
from pecdr.peon_zones import assign_dominant_zone
from pecdr.pecd_io import open_single_zipped_netcdf
from pecdr.paths import ProjPaths

paths = ProjPaths()
paths.ensure_directories()

events = pd.read_parquet(
    paths.mastr_capacity_events_file,
    columns=["unit_id", "technology", "region_code", "capacity_mw", "final_shutdown_date", "longitude", "latitude"],
)
wind = events[events["technology"] == "wind"].copy()
is_offshore = wind["region_code"].astype(str).str.startswith("DEZZ")
is_active = wind["final_shutdown_date"].isna()
has_coords = wind["longitude"].notna() & wind["latitude"].notna()

onshore = wind[~is_offshore & is_active & has_coords].copy()
print(f"Active onshore wind units: {len(onshore):,}, total capacity {onshore['capacity_mw'].sum():,.0f} MW")

detail = pd.read_parquet(paths.mastr_wind_technical_detail_file)
plants = onshore.merge(detail, on="unit_id", how="left")
print(f"  with hub_height_m: {plants['hub_height_m'].notna().sum():,} ({plants.loc[plants['hub_height_m'].notna(), 'capacity_mw'].sum():,.0f} MW)")

mask_ds = open_single_zipped_netcdf(paths.peon_mask_zip)
lats, lons = mask_ds["latitude"].values, mask_ds["longitude"].values

lat_idx = nearest_grid_index(plants["latitude"].to_numpy(), lats)
lon_idx = nearest_grid_index(plants["longitude"].to_numpy(), lons)
plants["grid_lat"] = lats[lat_idx]
plants["grid_lon"] = lons[lon_idx]

plants["peon_zone"] = assign_dominant_zone(plants, mask_ds["mask"], zone_prefix="DE")
print(plants["peon_zone"].value_counts().sort_index())

plants = plants[
    ["unit_id", "capacity_mw", "hub_height_m", "rotor_diameter_m", "manufacturer", "turbine_model", "longitude", "latitude", "grid_lat", "grid_lon", "peon_zone"]
]
plants.to_parquet(paths.wind_onshore_plant_panel_file, index=False)
print(f"Saved {len(plants):,} rows -> {paths.wind_onshore_plant_panel_file}")
