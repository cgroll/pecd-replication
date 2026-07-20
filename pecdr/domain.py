"""Shared spatial/temporal constants for the wind bias-correction replication.

Germany's PEON (onshore wind zone) bounding box was computed from
~/research/mastr-power-capacities-germany's peon_region_mask.nc (DE01-DE07
zones): lat 47.25-55.0, lon 6.0-15.0, vs. the full PECD domain's lat 18-75,
lon -31-45 -- restricting every CDS request to this box (via the `area`
parameter) cuts data volume to ~1.7% of a full-domain request.
"""

# CDS `area` parameter order is [North, West, South, East].
GERMANY_PEON_AREA = [55.0, 6.0, 47.25, 15.0]

# Two snapshot hours for the first bias-correction replication pass, both in
# 2020 so the PECD gridded wind-speed download (whole-year-only for
# historical years -- the CDS API offers no month-level subsetting there,
# unlike the current year) covers both with a single request. Deliberately
# not 10:00 UTC: ERA5 has a documented spurious wind-speed dip at that hour,
# which PECD corrects via interpolation as a separate preprocessing step not
# yet replicated here.
SNAPSHOT_TIMESTAMPS = ["2020-01-15T00:00", "2020-06-15T12:00"]
SNAPSHOT_YEAR = "2020"
