-- One-off export for the stop-visit backfill (owner-run; writes Parquet to GCS, creates no tables).
-- Compile: dbt compile --select backfill_export
--          --vars '{stream_start_date: "YYYY-MM-DD", backfill_export_uri: "gs://BUCKET/backfill/export"}'
-- Run:     bq query --use_legacy_sql=false < dbt/target/compiled/whyline_denver_dbt/analyses/backfill_export.sql
-- Then:    python -m whyline.ingest.gtfs_rt_backfill --export <uri> --from 2025-10-23 --until <stream start - 1>
-- Dry runs (2026-10-28): old trip updates 11.2 GiB and vehicle positions 0.8 GiB over the whole range
-- (about 0.08 GiB per daily statement), schedule extract per date 1.7 GiB, ingestion log 0.01 GiB, static
-- extracts about 0.06 GiB per distinct feed version. With the 10 MB minimum on each of the ~740 daily
-- statements, about 19 GiB in all, inside the monthly free tier. Runtime: roughly 1-2 hours.
DECLARE start_date DATE DEFAULT DATE '2025-10-23';
DECLARE end_date DATE DEFAULT DATE_SUB(DATE '{{ var("stream_start_date", "2100-01-01") }}', INTERVAL 1 DAY);
DECLARE uri STRING DEFAULT '{{ var("backfill_export_uri", "gs://SET-ME") }}';
DECLARE extracts ARRAY<DATE>;

IF STARTS_WITH(uri, 'gs://SET-ME') OR end_date >= CURRENT_DATE() THEN
    RAISE USING MESSAGE = 'Set stream_start_date (first full stream day) and backfill_export_uri.';
END IF;

-- Static GTFS: the extract the schedule used on each service date, each file at its latest load on or
-- before that extract, deduplicated by file content (ingestion-log hashes) so an unchanged feed exports once.
CREATE TEMP TABLE file_hashes AS
SELECT
    `table` AS tbl,
    SAFE.PARSE_DATE('%Y-%m-%d', REGEXP_EXTRACT(_source_path, r'extract_date=(\d{4}-\d{2}-\d{2})')) AS file_extract,
    ANY_VALUE(_hash_md5) AS hash
FROM `{{ source('raw', 'raw_gtfs_stops').database }}.{{ source('raw', 'raw_gtfs_stops').schema }}.__ingestion_log`
WHERE `table` IN ('raw_gtfs_stops', 'raw_gtfs_routes', 'raw_gtfs_trips', 'raw_gtfs_stop_times', 'raw_gtfs_shapes')
GROUP BY 1, 2
HAVING file_extract IS NOT NULL;

CREATE TEMP TABLE service_extract AS
SELECT service_date_mst AS service_date, ANY_VALUE(gtfs_extract_date) AS extract_date
FROM {{ ref('fct_scheduled_stop_time') }}
WHERE service_date_mst BETWEEN start_date AND end_date
GROUP BY 1;

CREATE TEMP TABLE version_files AS
SELECT e.extract_date, f.tbl, MAX(f.file_extract) AS file_extract
FROM (SELECT DISTINCT extract_date FROM service_extract) AS e
JOIN file_hashes AS f ON f.file_extract <= e.extract_date
GROUP BY 1, 2;

CREATE TEMP TABLE versions AS
SELECT extract_date, MIN(extract_date) OVER (PARTITION BY content) AS static_version
FROM (
    SELECT v.extract_date, TO_JSON_STRING(ARRAY_AGG(STRUCT(v.tbl, h.hash) ORDER BY v.tbl)) AS content
    FROM version_files AS v
    JOIN file_hashes AS h ON h.tbl = v.tbl AND h.file_extract = v.file_extract
    GROUP BY 1
);

EXECUTE IMMEDIATE FORMAT("""
EXPORT DATA OPTIONS (uri = '%s/service_static/*.parquet', format = 'PARQUET', overwrite = true) AS
SELECT s.service_date, v.static_version
FROM service_extract AS s JOIN versions AS v USING (extract_date)""", uri);

EXECUTE IMMEDIATE FORMAT("""
EXPORT DATA OPTIONS (uri = '%s/version_files/*.parquet', format = 'PARQUET', overwrite = true) AS
SELECT DISTINCT v.static_version, f.tbl, f.file_extract
FROM versions AS v JOIN version_files AS f ON f.extract_date = v.static_version""", uri);

-- Only the extracts the representative versions use, as a literal list so partitions prune.
FOR t IN (
    SELECT 'stops' AS name, 'raw_gtfs_stops' AS tbl, 'stop_id, stop_lat, stop_lon' AS cols
    UNION ALL SELECT 'routes', 'raw_gtfs_routes', 'route_id, route_type'
    UNION ALL SELECT 'trips', 'raw_gtfs_trips', 'trip_id, route_id, direction_id, shape_id, trip_headsign'
    UNION ALL SELECT 'stop_times', 'raw_gtfs_stop_times', 'trip_id, stop_sequence, stop_id, shape_dist_traveled'
    UNION ALL SELECT 'shapes', 'raw_gtfs_shapes', 'shape_id, shape_pt_lat, shape_pt_lon, shape_pt_sequence, shape_dist_traveled'
) DO
    SET extracts = (
        SELECT ARRAY_AGG(DISTINCT f.file_extract)
        FROM versions AS v JOIN version_files AS f ON f.extract_date = v.static_version
        WHERE f.tbl = t.tbl
    );
    EXECUTE IMMEDIATE FORMAT("""
    EXPORT DATA OPTIONS (uri = '%s/static/%s/*.parquet', format = 'PARQUET', overwrite = true) AS
    SELECT _extract_date, %s
    FROM `{{ source('raw', 'raw_gtfs_stops').database }}.{{ source('raw', 'raw_gtfs_stops').schema }}.%s`
    WHERE _extract_date IN UNNEST(%T)""", uri, t.name, t.cols, t.tbl, extracts);
END FOR;

-- The old 15-minute snapshots, one directory per UTC day so the backfill reads them in order.
FOR d IN (SELECT day FROM UNNEST(GENERATE_DATE_ARRAY(start_date, end_date)) AS day) DO
    EXECUTE IMMEDIATE FORMAT("""
    EXPORT DATA OPTIONS (uri = '%s/tu/date=%t/*.parquet', format = 'PARQUET', overwrite = true) AS
    SELECT feed_ts_utc, trip_id, route_id, stop_id, stop_sequence, schedule_relationship, event_ts_utc, start_date
    FROM {{ source('raw', 'raw_gtfsrt_trip_updates') }}
    WHERE DATE(feed_ts_utc) = %T""", uri, d.day, d.day);
    EXECUTE IMMEDIATE FORMAT("""
    EXPORT DATA OPTIONS (uri = '%s/vp/date=%t/*.parquet', format = 'PARQUET', overwrite = true) AS
    SELECT feed_ts_utc, trip_id, route_id, vehicle_id, lon, lat, event_ts_utc
    FROM {{ source('raw', 'raw_gtfsrt_vehicle_positions') }}
    WHERE DATE(feed_ts_utc) = %T""", uri, d.day, d.day);
END FOR;
