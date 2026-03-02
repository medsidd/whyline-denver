# Adapting WhyLine Denver to Another City

WhyLine Denver is built on open standards (GTFS, Census APIs, public open data portals) and can be adapted to analyze transit in any U.S. city with GTFS feeds and a public data portal.

---

## What Transfers Automatically

- The entire dbt transformation pipeline
- All intermediate and mart logic
- The FastAPI service
- The Next.js dashboard
- The DuckDB sync pipeline
- All equity and safety analytics

The only parts that need updating are the data sources and the configuration values that point to them.

---

## Changes Required

### 1. GTFS Static (`src/whyline/ingest/gtfs_static.py`)

Change `DEFAULT_GTFS_URL` to your transit agency's GTFS static feed URL:

```python
DEFAULT_GTFS_URL = "https://your-transit-agency.com/gtfs/google_transit.zip"
```

Most U.S. transit agencies publish GTFS feeds. Find yours at [transitfeeds.com](https://transitfeeds.com) or your agency's developer portal.

### 2. GTFS-RT (`src/whyline/ingest/gtfs_realtime.py`)

Change the two realtime feed URLs:

```python
DEFAULT_TRIP_UPDATES_URL = "https://your-agency.com/gtfs-rt/TripUpdates.pb"
DEFAULT_VEHICLE_POSITIONS_URL = "https://your-agency.com/gtfs-rt/VehiclePositions.pb"
```

Also update the Denver bounding box to your city's coordinates:

```python
CITY_LON_MIN = -122.6   # Example: Portland, OR
CITY_LON_MAX = -122.3
CITY_LAT_MIN = 45.4
CITY_LAT_MAX = 45.7
```

### 3. Denver-specific open data (`src/whyline/ingest/denver_crashes.py`, `denver_sidewalks.py`)

Replace the ArcGIS FeatureServer URLs with your city's open data equivalents. Most cities with ArcGIS-based portals will have similar endpoint structures — you may need to browse your city's open data catalog to find the right layer IDs.

If your city uses a different format (CSV download, API, etc.), you'll need to write a new ingestor following [ADDING_A_DATA_SOURCE.md](ADDING_A_DATA_SOURCE.md).

### 4. NOAA station (`src/whyline/ingest/noaa_daily.py`, `dbt/dbt_project.yml`)

Find your closest NOAA weather station at [ncdc.noaa.gov/cdo-web/datasets](https://www.ncdc.noaa.gov/cdo-web/datasets).

Update in two places:

**`noaa_daily.py`**:
```python
DEFAULT_STATION = "USW00024229"   # Your city's station
```

**`dbt/dbt_project.yml`**:
```yaml
vars:
  weather_station: "USW00024229"
```

### 5. Census geography (`src/whyline/ingest/acs.py`, `denver_tracts.py`)

Update the state and county FIPS codes:

**`acs.py`**:
```python
# Default: state 08 (Colorado), county 031 (Denver County)
# Example: King County, WA
DEFAULT_STATE_FIPS = "53"    # Washington
DEFAULT_COUNTY_FIPS = "033"  # King County
```

**`denver_tracts.py`**:
```python
DEFAULT_STATE_FIPS = "53"
DEFAULT_COUNTY_FIPS = "033"
```

Find state and county FIPS codes at [census.gov/library/reference/code-lists](https://www.census.gov/library/reference/code-lists.html).

---

## Optional: Rename the Project

If you're building a city-specific fork (e.g., "WhyLine Seattle"), you'll want to:

1. Rename the GCP project, GCS bucket, and BigQuery datasets
2. Update `GCP_PROJECT_ID`, `GCS_BUCKET`, `BQ_DATASET_*` in `.env` and Cloud Run configs
3. Update app branding in `.env.example`: `APP_BRAND_NAME`, colors

The Python package name (`whyline`) and dbt project name (`whyline_denver_dbt`) can remain or be renamed — just update `pyproject.toml` and `dbt/dbt_project.yml`.

---

## Verifying the Adaptation

After making the changes:

```bash
# 1. Test the GTFS static ingestor
make ingest-gtfs-static

# 2. Check that the expected files were created
ls data/raw/rtd_gtfs/

# 3. Run the GTFS-RT ingestor for one snapshot
make ingest-gtfs-rt

# 4. Load to BigQuery
make bq-load-local

# 5. Run the full dbt DAG
make dbt-run-staging
make dbt-run-intermediate
make dbt-run-marts

# 6. Check mart row counts in BigQuery
# mart_reliability_by_route_day should have rows if realtime data was captured
```

---

## What Might Need Additional Work

**Timezone**: Denver uses Mountain Time (`America/Denver`). The dbt models convert all timestamps from UTC using this timezone. If your city is in a different timezone, update the timezone string in the intermediate models:

```sql
-- Find all occurrences of America/Denver in dbt/models/ and replace
DATETIME(TIMESTAMP_SECONDS(CAST(...)), 'America/Denver')
```

**Address format for crashes**: The `denver_crashes.py` ingestor parses addresses in `Street1 / Street2` or `Street1 & Street2` format. Your city's crash data may format addresses differently.

**Sidewalk schema**: Denver's sidewalk data uses `SIDEWALKTYPE`, `SIDEWALKSTATUS`, etc. Other cities' GIS layers use different field names. Inspect your city's layer metadata and update the `outFields` parameter and column mapping in `denver_sidewalks.py`.

**Spatial reference system**: All geometry in the pipeline uses EPSG:4326 (WGS84 lat/lon). If your city's data is in a local projection, the ingestor needs a reprojection step (the sidewalk ingestor already does this using pyproj).

---

## Multi-City Architecture

If you want to run multiple cities from one instance, consider:

- Separate GCS path prefixes per city (`raw/{city}/...`)
- Separate BigQuery datasets (`raw_seattle`, `raw_portland`)
- Parameterized dbt models using `{{ var('city') }}`
- A city selector in the frontend filter sidebar

This is not currently implemented but the medallion architecture makes it achievable without major restructuring.
