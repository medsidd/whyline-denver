# WhyLine Denver – Data Contracts (v1)

These contracts describe the CSV outputs produced by the ingestion CLIs in `src/whylinedenver/ingest`. Schemas are frozen at **version v1**; removing or renaming a column requires a breaking-change process (see the policy at the end of this document) and must bump the manifest `schema_version` to `v2` and update downstream dbt sources.

## RTD GTFS Static (`data/raw/rtd_gtfs/extract_date=YYYY-MM-DD/gtfs/*.txt`)

| Column | Type | Units | Null? | Description |
| --- | --- | --- | --- | --- |
| (multiple TXT files) | | | | Source feed preserved as-is. Schema defined by GTFS spec. |

> The static feed is stored losslessly; validation only ensures the canonical GTFS tables exist. Downstream loaders reference GTFS documentation for column types.

## RTD GTFS-Realtime Trip Updates (`trip_updates.csv.gz`)

| Column | Type | Units | Null? | Description |
| --- | --- | --- | --- | --- |
| feed_ts_utc | TIMESTAMP | UTC ISO-8601 | NO | Snapshot timestamp truncated to minute. |
| entity_id | STRING | – | YES | Entity identifier from the feed. |
| trip_id | STRING | – | YES | Trip identifier. |
| route_id | STRING | – | YES | Route identifier. |
| stop_id | STRING | – | YES | Stop identifier. |
| stop_sequence | INT64 | – | YES | Stop sequence within the trip. |
| arrival_delay_sec | INT64 | seconds | YES | Arrival delay relative to schedule. |
| departure_delay_sec | INT64 | seconds | YES | Departure delay relative to schedule. |
| schedule_relationship | STRING | – | YES | GTFS schedule relationship enum. |
| event_ts_utc | TIMESTAMP | UTC | NO | Event timestamp resolved from arrival/departure stop-time updates. |
| start_date | STRING | YYYYMMDD | YES | Trip start date. |
| start_time | STRING | HH:MM:SS | YES | Trip start time. |

## RTD GTFS-Realtime Vehicle Positions (`vehicle_positions.csv.gz`)

| Column | Type | Units | Null? | Description |
| --- | --- | --- | --- | --- |
| feed_ts_utc | TIMESTAMP | UTC | NO | Snapshot timestamp. |
| entity_id | STRING | – | YES | Entity identifier. |
| trip_id | STRING | – | YES | Trip identifier. |
| route_id | STRING | – | YES | Route identifier. |
| vehicle_id | STRING | – | YES | Vehicle identifier. |
| vehicle_label | STRING | – | YES | Vehicle label. |
| lon | FLOAT64 | degrees (EPSG:4326) | YES | Vehicle longitude. |
| lat | FLOAT64 | degrees (EPSG:4326) | YES | Vehicle latitude. |
| bearing | FLOAT64 | degrees | YES | Vehicle bearing. |
| speed_mps | FLOAT64 | meters/second | YES | Vehicle speed. |
| event_ts_utc | TIMESTAMP | UTC | NO | Timestamp of vehicle position event. |

## Denver Crashes (`crashes.csv.gz`)

| Column | Type | Units | Null? | Description |
| --- | --- | --- | --- | --- |
| crash_id | STRING | – | YES | Incident identifier. |
| event_ts_utc | TIMESTAMP | UTC | YES | Crash occurrence timestamp. |
| severity | STRING | enum | NO | Canonical severity bucket (`fatal`, `serious_injury`, `injury`, `property_damage`). |
| severity_text | STRING | – | YES | Source severity text. |
| lat | FLOAT64 | degrees (EPSG:4326) | YES | Crash latitude. |
| lon | FLOAT64 | degrees (EPSG:4326) | YES | Crash longitude. |
| roadway_name | STRING | – | YES | Full roadway context. |
| on_route | STRING | – | YES | Primary roadway segment. |
| off_route | STRING | – | YES | Secondary intersecting roadway. |
| bike_involved | INT64 | 0/1 | NO | 1 if incident involves a bicycle. |
| ped_involved | INT64 | 0/1 | NO | 1 if incident involves a pedestrian. |

## Denver Sidewalks (`sidewalks.csv.gz`)

| Column | Type | Units | Null? | Description |
| --- | --- | --- | --- | --- |
| sidewalk_id | STRING | – | NO | Sidewalk segment identifier. |
| class | STRING | – | NO | Normalized sidewalk class/type. |
| status | STRING | – | NO | Normalized segment status. |
| material | STRING | – | NO | Surface material. |
| year_built | STRING | year | YES | Construction year; may include trailing `.0`. |
| lon_start | FLOAT64 | degrees (EPSG:4326) | NO | Start vertex longitude. |
| lat_start | FLOAT64 | degrees (EPSG:4326) | NO | Start vertex latitude. |
| lon_end | FLOAT64 | degrees (EPSG:4326) | NO | End vertex longitude. |
| lat_end | FLOAT64 | degrees (EPSG:4326) | NO | End vertex latitude. |
| length_m | FLOAT64 | meters | NO | Segment length (projected EPSG:26913). |
| centroid_lon | FLOAT64 | degrees | NO | Segment centroid longitude. |
| centroid_lat | FLOAT64 | degrees | NO | Segment centroid latitude. |

## NOAA Daily Weather (`weather.csv.gz`)

| Column | Type | Units | Null? | Description |
| --- | --- | --- | --- | --- |
| date | DATE | YYYY-MM-DD | NO | Observation date. |
| station | STRING | – | NO | NOAA station identifier. |
| snow_mm | FLOAT64 | millimeters | YES | Snowfall depth. |
| precip_mm | FLOAT64 | millimeters | YES | Total precipitation. |
| tmin_c | FLOAT64 | Celsius | YES | Minimum daily temperature. |
| tmax_c | FLOAT64 | Celsius | YES | Maximum daily temperature. |
| tavg_c | FLOAT64 | Celsius | YES | Average daily temperature. |
| snow_day | INT64 | 0/1 | YES | 1 if `snow_mm >= 1`. |
| precip_bin | STRING | enum | YES | Precipitation intensity bucket (`none`, `light`, `mod`, `heavy`). |

## ACS Tracts (`acs_tract.csv.gz`)

| Column | Type | Units | Null? | Description |
| --- | --- | --- | --- | --- |
| geoid | STRING | – | NO | 14000US-prefixed tract GEOID. |
| name | STRING | – | NO | Census NAME field. |
| year | INT64 | year | NO | ACS release year. |
| hh_no_vehicle | INT64 | households | YES | Households with zero vehicles. |
| hh_total | INT64 | households | YES | Total households. |
| workers_transit | INT64 | persons | YES | Workers commuting via public transit. |
| workers_total | INT64 | persons | YES | Total workers 16+. |
| persons_poverty | INT64 | persons | YES | Persons below poverty level. |
| pop_total | INT64 | persons | YES | Total population. |
| pct_hh_no_vehicle | FLOAT64 | ratio (0–1) | YES | `hh_no_vehicle / hh_total`. |
| pct_transit_commute | FLOAT64 | ratio (0–1) | YES | `workers_transit / workers_total`. |
| pct_poverty | FLOAT64 | ratio (0–1) | YES | `persons_poverty / pop_total`. |

## Denver Census Tracts (`tracts.csv.gz`)

| Column | Type | Units | Null? | Description |
| --- | --- | --- | --- | --- |
| geoid | STRING | – | NO | Census tract GEOID (without 14000US prefix). |
| name | STRING | – | YES | Tract name/label from TIGERweb. |
| aland_m2 | NUMERIC | square meters | YES | Land area (ALAND) attribute. |
| awater_m2 | NUMERIC | square meters | YES | Water area (AWATER) attribute. |
| geometry_geojson | STRING | GeoJSON | NO | Polygon or multipolygon geometry serialized as GeoJSON. |

## Breaking Change Policy

- Schema version `v1` is immutable: do not drop or rename columns, or change column types, without a version bump.
- Breaking changes require coordination with downstream consumers (dbt source definitions, BigQuery tables, app schemas) and must:
  1. Increment `schema_version` in manifest metadata (e.g., to `v2`).
  2. Update this contract document with a new section documenting the changes.
  3. Adjust ingestion scripts, dbt sources, and documentation to match the new schema.
- Non-breaking additions (new nullable columns) are permitted but must be documented here and communicated to downstream consumers.
