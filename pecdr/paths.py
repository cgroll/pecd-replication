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

    def pecd_peon_capacity_factor_zip(self, year: str) -> Path:
        """PECD's own wind-onshore capacity factor at PEON zones (ground truth), one file per year.

        `technology=30` ("Existing technologies"), `energy_scenario=resource_grade_b`
        (the only scenario "Existing" is offered under) -- see
        pipeline/07_download_pecd_peon_capacity_factor.py.
        """
        return self.pecd_downloads_path / f"pecd_peon_capacity_factor_{year}.zip"

    @property
    def era5_wind_snapshots_file(self) -> Path:
        """Raw (not bias-corrected) ERA5 10m/100m u/v wind components for the chosen snapshot hours.

        See pipeline/03_download_era5_wind_snapshots.py and pecdr/domain.py
        for the exact timestamps.
        """
        return self.era5_downloads_path / "era5_wind_snapshots.nc"

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

    # ------------------------------------------------------------------ #
    # Processed data files                                                 #
    # ------------------------------------------------------------------ #

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
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
