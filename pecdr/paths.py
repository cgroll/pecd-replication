"""Project paths configuration.

All paths are resolved relative to the project root, making scripts runnable
from any working directory. Add a @property for each new data file introduced
in the pipeline.
"""

from pathlib import Path


class ProjPaths:
    """Centralized project paths.

    The root is inferred from the location of this file (pkg/), so scripts
    run correctly regardless of the working directory they are invoked from.
    """

    def __init__(self):
        self._pkg_path = Path(__file__).resolve().parent  # pkg/
        self._project_path = self._pkg_path.parent        # project root

    # ------------------------------------------------------------------ #
    # Top-level directories                                                #
    # ------------------------------------------------------------------ #

    @property
    def project_path(self) -> Path:
        """Root project directory."""
        return self._project_path

    @property
    def pkg_path(self) -> Path:
        """Source package directory (pkg/)."""
        return self._pkg_path

    @property
    def pipeline_path(self) -> Path:
        """Pipeline scripts directory."""
        return self._project_path / "pipeline"

    # ------------------------------------------------------------------ #
    # Data directories                                                     #
    # ------------------------------------------------------------------ #

    @property
    def data_path(self) -> Path:
        """Main data directory."""
        return self._project_path / "data"

    @property
    def downloads_path(self) -> Path:
        """Raw downloaded data."""
        return self.data_path / "downloads"

    @property
    def processed_data_path(self) -> Path:
        """Processed/transformed data."""
        return self.data_path / "processed"

    # ------------------------------------------------------------------ #
    # Output directories                                                   #
    # ------------------------------------------------------------------ #

    @property
    def output_path(self) -> Path:
        """Generated outputs root."""
        return self._project_path / "output"

    @property
    def images_path(self) -> Path:
        """Chart/figure images saved by pipeline scripts."""
        return self.output_path / "images"

    @property
    def reports_path(self) -> Path:
        """Report files."""
        return self.output_path / "reports"

    # ------------------------------------------------------------------ #
    # PECD v4.2 wind bias-correction reference grids (static, no year/month) #
    # ------------------------------------------------------------------ #

    @property
    def pecd_downloads_path(self) -> Path:
        """PECD v4.2 downloads directory."""
        return self.downloads_path / "pecd"

    def wind_bias_reference_zip(self, name: str) -> Path:
        """One static wind bias-correction reference grid, downloaded individually.

        `name` is one of: "climatology_era5_10m", "climatology_era5_100m",
        "climatology_gwa2_10m", "climatology_gwa2_100m", "power_law_coefficient".
        One CDS request per variable (rather than one combined request) --
        empirically, combining all 5 into a single request left the CDS job
        queued with no response for 20+ minutes (vs. ~3-8 min per variable
        individually), so pipeline/01_download_pecd_wind_bias_reference.py
        downloads them one at a time. See pipeline/01_download_pecd_wind_bias_reference.py.
        """
        return self.pecd_downloads_path / f"{name}.zip"

    def pecd_wind_speed_zip(self, height_m: int, year: str) -> Path:
        """PECD's own bias-corrected gridded wind speed (ground truth), one file per height/year.

        One request per height, same reasoning as `wind_bias_reference_zip`
        -- see pipeline/02_download_pecd_wind_speed_snapshots.py.
        """
        return self.pecd_downloads_path / f"pecd_{height_m}m_wind_speed_{year}.zip"

    # ------------------------------------------------------------------ #
    # SMARD downloads (migrated from delu-headline-forecast)               #
    # ------------------------------------------------------------------ #

    @property
    def smard_downloads_path(self) -> Path:
        """Raw SMARD series downloads directory."""
        return self.downloads_path / "smard"

    def smard_raw_file(self, name: str) -> Path:
        """Raw hourly SMARD series parquet.

        `name` is one of: pv, wind_onshore, wind_offshore, load.
        """
        return self.smard_downloads_path / f"{name}.parquet"

    @property
    def target_panel_file(self) -> Path:
        """Combined hourly DE-LU target panel (pv, wind_onshore, wind_offshore, load columns, MW).

        The series delu-headline-forecast's forecasting models predict --
        migrated here as part of centralizing data acquisition. See
        pipeline/14_build_target_panel.py.
        """
        return self.processed_data_path / "target_panel.parquet"

    # ------------------------------------------------------------------ #
    # Raw ERA5 downloads                                                   #
    # ------------------------------------------------------------------ #

    @property
    def era5_downloads_path(self) -> Path:
        """Raw ERA5 downloads directory."""
        return self.downloads_path / "era5"

    @property
    def peon_mask_zip(self) -> Path:
        """PECD v4.2 PEON (pan-European onshore wind zone) region mask, full domain (no `area` subset).

        Fractional (0-1) area coverage of each 0.25-degree grid cell by
        every European PEON zone; Germany intersects 7 (DE01-DE07). Needed
        at full resolution (not restricted to the Germany bbox) so a
        MaStR unit's nearest-grid-cell lookup always has a matching mask
        cell, even for units right at the domain edge. See
        pipeline/06_download_pecd_masks.py.
        """
        return self.pecd_downloads_path / "peon_region_mask.zip"

    @property
    def peof_mask_zip(self) -> Path:
        """PECD v4.2 PEOF (pan-European offshore wind zone) region mask, full domain.

        Germany intersects 6 PEOF zones (5 North Sea sub-zones + 1
        Baltic-wide zone). See `peon_mask_zip` for the shared structure and
        pipeline/06_download_pecd_masks.py.
        """
        return self.pecd_downloads_path / "peof_region_mask.zip"

    @property
    def nuts2_mask_zip(self) -> Path:
        """PECD v4.2 NUTS2 region mask, full domain.

        Needed to aggregate solar capacity factor (PECD's solar product is
        published at NUTS2, unlike wind's PEON/PEOF-only resolution). See
        pipeline/06_download_pecd_masks.py.
        """
        return self.pecd_downloads_path / "nuts_2_region_mask.zip"

    def pecd_peon_capacity_factor_zip(self, year: str) -> Path:
        """PECD's own wind-onshore capacity factor at PEON zones (ground truth), one file per year.

        `technology=30` ("Existing technologies"), `energy_scenario=resource_grade_b`
        (the only scenario "Existing" is offered under) -- see
        pipeline/07_download_pecd_peon_capacity_factor.py.
        """
        return self.pecd_downloads_path / f"pecd_peon_capacity_factor_{year}.zip"

    def pecd_capacity_factor_zip(self, kind: str, technology: str) -> Path:
        """PECD capacity-factor download, all of Europe, multi-year, one file per
        (kind, technology). `kind` is one of "solar", "wind_onshore",
        "wind_offshore"; `technology` is PECD's technology code (e.g. "60" for
        solar industrial rooftop, "30" for existing onshore wind). Broader
        multi-year/multi-technology sibling of `pecd_peon_capacity_factor_zip`
        (which stays as-is, already used by the validated onshore replication
        pipeline) -- migrated from
        ~/research/delu-headline-forecast/pipeline/10_download_pecd_capacity_factors.py.
        See pipeline/16_download_pecd_capacity_factors.py.
        """
        return self.pecd_capacity_factors_downloads_path / f"{kind}_tech{technology}.zip"

    @property
    def pecd_capacity_factors_downloads_path(self) -> Path:
        """Directory for the multi-year PECD capacity-factor downloads (see `pecd_capacity_factor_zip`)."""
        return self.pecd_downloads_path / "capacity_factors"

    @property
    def pecd_solar_capacity_factors_file(self) -> Path:
        """PECD solar PV capacity factor, Germany-only, hourly, 2015-2025.

        MultiIndex columns (technology, region): 4 solar sub-types (60/61/62/63)
        x ~38 DE NUTS2 regions. See pipeline/17_process_pecd_capacity_factors.py.
        """
        return self.processed_data_path / "pecd_solar_capacity_factors.parquet"

    @property
    def pecd_wind_onshore_capacity_factors_file(self) -> Path:
        """PECD wind-onshore capacity factor, Germany-only, hourly, 2015-2025,
        columns = 7 PEON zones (DE01-DE07). See
        pipeline/17_process_pecd_capacity_factors.py.
        """
        return self.processed_data_path / "pecd_wind_onshore_capacity_factors.parquet"

    @property
    def pecd_wind_offshore_capacity_factors_file(self) -> Path:
        """PECD wind-offshore capacity factor, Germany-only, hourly, 2015-2025,
        columns = PEOF zones (DE0xx_OFF) -- codes already match MaStR's
        `region_code` format. See pipeline/17_process_pecd_capacity_factors.py.
        """
        return self.processed_data_path / "pecd_wind_offshore_capacity_factors.parquet"

    def pecd_temperature_zip(self, file_version: str) -> Path:
        """PECD 2m temperature, country level (NUTS0), one file per `file_version`
        ("fv1" -> 2022-2025, "fv2" -> 1950-2021 -- this variable/resolution combo
        splits by file_version at that year boundary). See
        pipeline/18_download_pecd_temperature.py.
        """
        return self.pecd_downloads_path / f"pecd_temperature_{file_version}.zip"

    @property
    def own_wind_onshore_capacity_factors_file(self) -> Path:
        """This project's own physics-based (raw ERA5, no bias correction, one
        generic turbine curve) wind-onshore capacity factor, by PEON zone,
        hourly, full backtest period ("approach 2" -- see
        pipeline/12_compare_all_approaches.py). See
        pipeline/20_process_era5_capacity_factors.py.
        """
        return self.processed_data_path / "own_wind_onshore_capacity_factors.parquet"

    @property
    def own_wind_offshore_capacity_factors_file(self) -> Path:
        """Same as `own_wind_onshore_capacity_factors_file`, by PEOF zone."""
        return self.processed_data_path / "own_wind_offshore_capacity_factors.parquet"

    @property
    def own_solar_capacity_factors_file(self) -> Path:
        """Same as `own_wind_onshore_capacity_factors_file`, solar by NUTS2 zone
        (only the NUTS2 regions PECD's own solar product also covers).
        """
        return self.processed_data_path / "own_solar_capacity_factors.parquet"

    @property
    def own_wind_onshore_gridweighted_features_file(self) -> Path:
        """Grid-cell-capacity-weighted national wind-onshore features (effective_cf,
        capacity_mw) -- a refinement of `own_wind_onshore_capacity_factors_file`
        that skips the PEON zone step entirely, weighting straight from each
        grid cell's own MaStR installed capacity. See
        pipeline/21_process_wind_grid_capacity_weighted.py.
        """
        return self.processed_data_path / "own_wind_onshore_gridweighted_features.parquet"

    @property
    def own_wind_offshore_gridweighted_features_file(self) -> Path:
        """Same as `own_wind_onshore_gridweighted_features_file`, for offshore wind."""
        return self.processed_data_path / "own_wind_offshore_gridweighted_features.parquet"

    @property
    def pecd_temperature_file(self) -> Path:
        """PECD 2m temperature, Germany-only, hourly, 2015-2025 (single "DE" column, deg C).

        See pipeline/19_process_pecd_temperature.py.
        """
        return self.processed_data_path / "pecd_temperature_de.parquet"

    @property
    def era5_wind_snapshots_file(self) -> Path:
        """Raw (not bias-corrected) ERA5 10m/100m u/v wind components for the chosen snapshot hours.

        See pipeline/03_download_era5_wind_snapshots.py and pecdr/domain.py
        for the exact timestamps.
        """
        return self.era5_downloads_path / "era5_wind_snapshots.nc"

    def era5_month_file(self, month: str) -> Path:
        """One month of hourly ERA5 (100m/10m u/v wind, 2m temp, solar radiation),
        56-47N x 3-15E, 0.25 degree. `month` is a "YYYY-MM" string. See
        pipeline/15_download_era5_full_period.py.
        """
        return self.era5_downloads_path / f"era5_{month}.nc"

    # ------------------------------------------------------------------ #
    # External sibling projects                                            #
    # ------------------------------------------------------------------ #

    @property
    def mastr_project_path(self) -> Path:
        """Root of ~/research/mastr-power-capacities-germany, consumed directly
        rather than re-derived from raw MaStR here (same convention as
        ~/research/delu-headline-forecast).
        """
        return Path.home() / "research" / "mastr-power-capacities-germany"

    @property
    def mastr_capacity_events_file(self) -> Path:
        """Unit-level MaStR capacity events (one row per unit), with region,
        capacity, commissioning/shutdown dates, and coordinates. See
        ~/research/mastr-power-capacities-germany/pipeline/03_build_capacity_panel.py.
        """
        return self.mastr_project_path / "data" / "processed" / "capacity_events.parquet"

    @property
    def mastr_wind_technical_detail_file(self) -> Path:
        """Per-wind-unit technical detail (manufacturer, turbine_model,
        hub_height_m, rotor_diameter_m), keyed by unit_id -- joins against
        `mastr_capacity_events_file`. See
        ~/research/mastr-power-capacities-germany/pipeline/01_download_mastr.py.
        """
        return self.mastr_project_path / "data" / "downloads" / "mastr_units_raw" / "wind_technical_detail.parquet"

    @property
    def mastr_capacity_by_peon_month_file(self) -> Path:
        """Monthly (time-varying) onshore wind capacity by PEON zone x month, from
        2015 on -- unlike `wind_onshore_plant_panel_file` (this project's own
        fixed "active today" fleet snapshot), this tracks capacity growth
        over time, needed to weight a historical actuals comparison (e.g.
        against SMARD) fairly rather than applying today's larger fleet
        retroactively. See
        ~/research/mastr-power-capacities-germany/pipeline/07_build_wind_zone_panel.py.
        """
        return self.mastr_project_path / "data" / "processed" / "capacity_by_peon_month.parquet"

    @property
    def mastr_capacity_by_wind_onshore_grid_month_file(self) -> Path:
        """Monthly onshore wind capacity by 0.25-degree ERA5/PECD grid cell x month --
        each MaStR unit assigned to its single nearest grid cell, no PEON zone
        involved. Columns: grid_lat, grid_lon, month, capacity_mw, unit_count,
        series. See
        ~/research/mastr-power-capacities-germany/pipeline/09_build_wind_grid_cell_panel.py.
        """
        return self.mastr_project_path / "data" / "processed" / "capacity_by_wind_onshore_grid_month.parquet"

    @property
    def mastr_capacity_by_wind_offshore_grid_month_file(self) -> Path:
        """Same as `mastr_capacity_by_wind_onshore_grid_month_file`, for offshore wind."""
        return self.mastr_project_path / "data" / "processed" / "capacity_by_wind_offshore_grid_month.parquet"

    @property
    def delu_project_path(self) -> Path:
        """Root of ~/research/delu-headline-forecast, read directly for its
        already-downloaded ERA5 archive (same "consume a sibling project's
        data directly" convention as `mastr_project_path`) -- avoids a
        redundant multi-GB CDS download for periods that project already has.
        """
        return Path.home() / "research" / "delu-headline-forecast"

    @property
    def delu_own_wind_onshore_capacity_factors_file(self) -> Path:
        """delu's own physics-based wind-onshore capacity factor, by PEON zone,
        hourly -- raw ERA5 (no GWA2 bias correction), one generic turbine
        power curve for the whole fleet (no per-plant technology match). See
        ~/research/delu-headline-forecast/dhf/physics.py and
        pipeline/24_process_era5_capacity_factors.py.
        """
        return self.delu_project_path / "data" / "processed" / "own_wind_onshore_capacity_factors.parquet"

    # ------------------------------------------------------------------ #
    # Processed data files                                                 #
    # ------------------------------------------------------------------ #

    @property
    def wind_onshore_full_year_cf_file(self) -> Path:
        """Hourly modeled PEON zone + national capacity factor for all of 2020.

        One row per hour, columns DE01-DE07 + `national`. See
        pipeline/10_compute_wind_onshore_full_year.py.
        """
        return self.processed_data_path / "wind_onshore_full_year_2020_cf.parquet"

    @property
    def wind_onshore_plant_panel_file(self) -> Path:
        """Active onshore wind plants, one row per unit: capacity, hub height,
        rotor diameter, turbine model, coordinates, nearest 0.25-degree grid
        cell, and dominant PEON zone. See
        pipeline/08_build_wind_onshore_plant_panel.py.
        """
        return self.processed_data_path / "wind_onshore_plant_panel.parquet"

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def ensure_directories(self) -> None:
        """Create all standard directories if they do not yet exist."""
        dirs = [
            self.downloads_path,
            self.processed_data_path,
            self.images_path,
            self.reports_path,
            self.pecd_downloads_path,
            self.era5_downloads_path,
            self.smard_downloads_path,
            self.pecd_capacity_factors_downloads_path,
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
