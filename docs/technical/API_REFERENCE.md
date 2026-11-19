# API reference

FastAPI registers five routers under `/api` in `api/main.py`. `api/models.py` is the request/response source of truth; `frontend/src/types/api.ts` mirrors it. Use the running backend's `/docs` or `/openapi.json` for machine-readable contracts. Examples below use a local backend; public dashboard requests are proxied through Next.js.

## Endpoint inventory

| Method and path | Behavior |
|---|---|
| `GET /api/health` | Returns `status`; no model-count or BigQuery check |
| `GET /api/freshness` | Returns `bigquery_freshness`, from sync state or the dbt run results |
| `GET /api/filters` | Route IDs, weather bins, available minimum/maximum service dates |
| `GET /api/filters/stops` | Stop lookup list (`stop_id`, `stop_name`, `lat`, `lon`) |
| `GET /api/routes/shapes?ids=15,0` | Lines for up to 10 route IDs (comma-separated, request order): `route_id`, `direction_id`, `path` as `[lon, lat]` pairs, one entry per line part. Reads `mart_route_shapes` once per process every 6 hours; invalid or unknown IDs are skipped, and the answer is empty if the table can't be read |
| `GET /api/models` | Allowed model names, qualified names, descriptions, and column metadata from dbt artifacts |
| `POST /api/sql/generate` | Generate SQL using the selected provider, add the filter predicates, check it and qualify table names |
| `POST /api/sql/validate` | Check SQL and dry-run it on BigQuery (estimate plus BigQuery's own statement and table check) |
| `POST /api/sql/prebuilt/{index}` | A ready-made question's SQL with the filters it supports, checked and qualified |
| `POST /api/query/run` | Re-check and run SQL on BigQuery and enrich displayed results |
| `POST /api/downloads/mart` | CSV export of one of the 18 marts in `MART_OPTIONS` |

Every query runs on BigQuery. Until November 19, 2026 the API also answered on a DuckDB copy of the app marts and served that file at `GET /api/downloads/warehouse`; both are gone. Requests no longer take `engine`; clients that still send it are not refused (unknown fields are ignored). The engine-named routes (`/api/filters/{engine}`, `/api/filters/{engine}/stops`, `/api/sql/prebuilt/{index}/for/{engine}`) were removed once the dashboard moved to the routes above.

## Generate SQL

```json
{
  "question": "Which routes have the lowest on-time share?",
  "filters": {
    "start_date": "2026-10-14",
    "end_date": "2026-10-25",
    "routes": [],
    "stop_id": "",
    "weather": []
  }
}
```

`question` is required. `filters` is optional and defaults to empty/null fields. Its shape is `FilterState`: nullable `start_date`/`end_date` strings, route/weather string lists, and a stop string. The implementation injects supported conditions when relevant column names appear in generated SQL; filters are not a universal relational query builder and do not rewrite edited SQL. Filter values are validated first (`clean_filters` in `src/whyline/prebuilt.py`): routes and weather bins must match `[A-Za-z0-9_-]{1,16}`, the stop `[A-Za-z0-9]{1,16}`, and dates must be ISO dates with the start on or before the end. Invalid values are dropped, never quoted into SQL. Review the actual SQL.

Response: `sql`, `explanation`, `cache_hit`, `error`, `applied_filters`/`skipped_filters` (empty here; set by the ready-made endpoints), and `is_live`: true when the SQL reads a live view (`mart_vehicles_now`, `mart_stop_visits_recent`), which trails real time by 15–30 minutes. The prompt sends questions about right now to those views and tells the model not to date-filter them; they have no `service_date_mst`, so the date filter isn't injected. Provider/guardrail failures can return HTTP 200 with a non-null `error`. Prompt cache keys include provider, question, and filters; default TTL is 900 seconds per process. Gemini sends the question, filters, and schema brief to the provider. When dates are set, the prompt asks for exactly the predicate the server injects (`service_date_mst BETWEEN DATE '…' AND DATE '…'`) and no other date window, so the injection finds it and adds nothing; without dates it asks for a recent window when the question implies one. The prompt also gives today's Denver date, so "yesterday" and "last week" resolve correctly, and says today's rows are partial. Stub avoids provider calls; other named providers are unimplemented.

## Validate SQL

Request to `/api/sql/validate`:

```json
{"sql":"SELECT stop_id, stop_name FROM mart_gtfs_stops LIMIT 10"}
```

Response fields: `valid`, nullable `sanitized_sql`, nullable `bq_est_bytes`, nullable `error`, and `is_live` (the SQL reads a live view). The dry run is part of validation: a table outside the allowlist or anything but one SELECT returns `valid: false`, and so does any query BigQuery refuses (unknown column, syntax), with BigQuery's message. Only a missing estimate from a credentials or network failure is nonfatal. `sql` accepts at most 20,000 characters and `question` 1,000; longer requests get 422.

Guardrails accept one SELECT/WITH statement, reject denylisted write keywords (a query that starts with another word gets "SQL must start with SELECT or WITH. Check the first word ('SELEC')."), and check referenced table/project/dataset allowlists. They add `LIMIT 5000` only when a numeric limit is absent; existing limits are not reduced in the SQL, but the API fetches at most 10,000 rows for a query (see Execution). The partition-filter suggestion checks for a configured date column without a WHERE clause; it does not guarantee effective partition pruning. `EXTRACT(HOUR FROM ts)`'s FROM is not read as a table, by the check or by BigQuery table qualification (both treated it as one before November 9, 2026). `FROM`/`JOIN UNNEST(...)`, `IS DISTINCT FROM` and a `;` inside quotes are accepted (rejected before November 15, 2026).

These text checks give early, readable errors; they are not the security boundary, because a comma join or a comment after `FROM` gets a second table past them. Since November 15, 2026 BigQuery re-checks visitor SQL before it runs (`allowed_tables` in `bigquery_engine.execute` and `estimate`): the dry run must be one `SELECT`, and every table it reports must be an allowed mart in the mart dataset or, when the query names a live view, a base table behind the two live views (found by dry-running the views; before November 19 any query could read those tables, so a comma join reached `core_denver.fct_stop_visit`). Dataset access is meant to be the last layer: once the live views are authorized views and the API account reads only `mart_denver`, even a query that names a live view cannot read its base tables directly. On November 19, 2026 the account could still read `core_denver`, `stg_denver` and `raw_denver`; the steps are in [operations](OPERATIONS.md).

## Prebuilt SQL

Indices follow the order of `PREBUILT` in `src/whyline/prebuilt.py`: 0 worst routes by on-time share, 1 crash exposure, 2 snow days against other days per route and method, 3 equity gaps, 4 scheduled frequency, 5 arrival-prediction accuracy, 6 missed trips, 7 slowest bus segments at rush hour, 8 routes running right now (live). `frontend/src/types/api.ts` mirrors the labels.

The endpoint takes an optional `FilterState` body (an empty or missing body uses each question's default window: the last N complete days in Denver, ending yesterday, written as literal dates because BigQuery's `CURRENT_DATE` is UTC and runs a day ahead every Denver evening). `build_prebuilt_sql` puts the user's dates in place of the default window and adds the route, stop and weather predicates the question supports, with the right table alias. The response adds `applied_filters` and `skipped_filters`, lists of `dates`, `routes`, `stop` and `weather`: skipped are filters the user set that the question doesn't take, or with invalid values (a filter with some valid and some invalid values is in both lists). `explanation` is a plain sentence written for each question.

| # | Question | Dates (default window) | Routes | Stop | Weather |
|---|---|---|---|---|---|
| 0 | Worst 10 routes by on-time share (days with `pct_observed` ≥ 0.5) | ✓ (30 days) | ✓ | – | ✓ |
| 1 | Crash exposure | – | – | ✓ | – |
| 2 | Snow vs other days | – (keeps 365 days; needs 3 snow days) | ✓ | – | – |
| 3 | Equity gaps | – | – | ✓ | – |
| 4 | Frequency | – | ✓ | – | – |
| 5 | Prediction accuracy | ✓ (30 days) | ✓ | – | – |
| 6 | Missed trips | ✓ (7 days) | ✓ | – | – |
| 7 | Slow segments | – (28-day mart) | ✓ (`s.route_id`) | – | – |
| 8 | Routes running right now (live) | – (live view) | ✓ | – | – |

## Execute

```bash
curl -sS http://localhost:8000/api/query/run   -H 'Content-Type: application/json'   -d '{"sql":"SELECT stop_id, stop_name FROM mart_gtfs_stops LIMIT 5"}'
```

`question` is optional and is used in logging. Response fields are:

| Field | Meaning |
|---|---|
| `rows` | Number of displayed records |
| `columns` | Displayed column names after enrichment |
| `data` | List of row objects |
| `total_rows` | Result size before the display truncation, not a count of all source-table rows |
| `stats` | Execution metadata: `engine` (`bigquery`), `rows`, `total_rows`, `bq_est_bytes` |
| `error` | Nullable execution/validation error |
| `is_live` | The SQL reads a live view |
| `live_loaded_at` | For live results: when the newest vehicle report was made, `YYYY-MM-DD HH:MM UTC` (from `MAX(report_ts_utc)` of `mart_vehicles_now`, cached 60 s) |

Execution always re-sanitizes server-side. Results hold at most 10,000 records, and the API fetches no more than that whatever `LIMIT` the SQL carries; `total_rows` is still the full count. The scan is bounded separately, by `MAX_BYTES_BILLED` and a 120-second job timeout. The result cache keeps at most 64 results for three minutes. Stop IDs can add missing stop names/coordinates and route IDs can add missing route names, from `mart_gtfs_stops` and `mart_gtfs_routes` read once per process. Lookup availability is separate from query success.

Identical SQL results can be served from the process cache (180-second default TTL). `/api/filters` caches its whole response for 10 minutes per process, unless it reported an error. This is not shared across instances and can briefly serve data from before a rebuild.

## Downloads

Mart request:

```json
{
  "mart": "mart_reliability_by_route_day",
  "limit_rows": 200000,
  "date_column": "service_date_mst",
  "date_start": "2026-10-14",
  "date_end": "2026-10-25"
}
```

`limit_rows` defaults to 200,000 and accepts 1,000–500,000 (2,000,000 before November 15, 2026). Date filtering is applied only when all three date fields are present. `date_column` must be `service_date_mst` on a mart in `DATED_MARTS` ( the route-day, stop-hour, prediction, crowding-by-route, missed-trip, wait-by-route and run-time marts; other marts take none); anything else, a non-ISO date or a reversed range returns 400. Those seven marts are returned newest first (`ORDER BY service_date_mst DESC`), so the row limit keeps the latest rows; without dates they get `WHERE service_date_mst IS NOT NULL`, which the guardrail requires wherever that column appears. The query still goes through guardrails. The response is `text/csv` with a download filename; it is not a Parquet endpoint. The result is held in memory as a table and sent as CSV in 50,000-row pieces; at most two downloads build at once per instance, and a third gets 429 (the dashboard shows its "too many requests" message). Downloads are not cached.

Allowed download marts are `MART_OPTIONS` in `api/routers/downloads.py`: the 18 app marts other than the two GTFS reference marts, which are queryable but absent from this CSV endpoint's separate allowlist.

## Errors and health interpretation

Pydantic request validation returns 422. Explicit `HTTPException`s use FastAPI's `detail` field: 400 for invalid download arguments, 404 for an unknown prebuilt index, and 500 for download execution failures. SQL generation/validation/query handlers also encode many failures in HTTP-200 response `error` fields. Clients must check both HTTP status and body.

`/api/health` does not load artifacts or execute SQL. `/api/freshness` reports when dbt last built BigQuery, not per-source coverage; timezone formatting differs between deployments and should be read with the returned zone label. Validate actual data using [QA checks](../QA_Validation_Guide.md).
