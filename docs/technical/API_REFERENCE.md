# API reference

FastAPI registers five routers under `/api` in `api/main.py`. `api/models.py` is the request/response source of truth; `frontend/src/types/api.ts` mirrors it. Use the running backend's `/docs` or `/openapi.json` for machine-readable contracts. Examples below use a local backend; public dashboard requests are proxied through Next.js.

## Endpoint inventory

| Method and path | Behavior |
|---|---|
| `GET /api/health` | Returns `status` and `engine_default`; no warehouse/model-count check |
| `GET /api/freshness` | Returns `bigquery_freshness` and `duckdb_freshness` strings from sync state/fallback artifacts |
| `GET /api/filters/{engine_name}` | Route IDs, weather bins, available minimum/maximum service dates |
| `GET /api/filters/{engine_name}/stops` | Stop lookup list (`stop_id`, `stop_name`, `lat`, `lon`) |
| `GET /api/models` | Allowed model names, qualified names, descriptions, and column metadata from dbt artifacts |
| `POST /api/sql/generate` | Generate SQL using the selected provider and apply filters/guardrails/dialect adaptation |
| `POST /api/sql/validate` | Validate/adapt SQL; optionally return a BigQuery dry-run estimate |
| `POST /api/sql/prebuilt/{index}` | Return raw prebuilt SQL; no engine argument/adaptation/validation |
| `POST /api/sql/prebuilt/{index}/for/{engine_name}` | Validate and adapt prebuilt SQL for DuckDB or BigQuery |
| `POST /api/query/run` | Revalidate/adapt/execute SQL and enrich displayed results |
| `POST /api/downloads/mart` | CSV export of one of seven explicitly listed analytic marts |
| `GET /api/downloads/warehouse` | Binary download of the configured DuckDB file, or 404 |

`engine` is `duckdb` or `bigquery`. Generation defaults to DuckDB; validation, execution, and mart-download requests require an engine. Health's default comes from configuration and is independent of request defaults.

## Generate SQL

```json
{
  "question": "Which routes have the lowest on-time share?",
  "engine": "duckdb",
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

Response: `sql`, `explanation`, `cache_hit`, `error`, and `applied_filters`/`skipped_filters` (empty here; set by the ready-made endpoints). Provider/guardrail failures can return HTTP 200 with a non-null `error`. Prompt cache keys include provider, engine, question, and filters; default TTL is 900 seconds per process. Gemini sends the question, filters, and schema brief to the provider. When dates are set, the prompt tells the model the server adds the date range and not to write its own; without dates it asks for a recent window when the question implies one. Stub avoids provider calls; other named providers are unimplemented.

## Validate SQL

Request to `/api/sql/validate`:

```json
{"sql":"SELECT stop_id, stop_name FROM mart_gtfs_stops LIMIT 10","engine":"duckdb"}
```

Response fields: `valid`, nullable `sanitized_sql`, nullable `bq_est_bytes`, nullable `error`. BigQuery estimation errors are nonfatal, so `valid: true` with no estimate does not prove the query will execute.

Guardrails accept one SELECT/WITH statement, reject denylisted write keywords (a query that starts with another word gets "SQL must start with SELECT or WITH. Check the first word ('SELEC')."), and check referenced table/project/dataset allowlists. They add `LIMIT 5000` only when a numeric limit is absent; existing limits are not reduced. BigQuery's partition-filter suggestion checks for a configured date column without a WHERE clause; it does not guarantee effective partition pruning. These are regex checks and must be backed by least-privilege database credentials.

## Prebuilt SQL

Indices follow the order of `PREBUILT` in `src/whyline/prebuilt.py`: 0 worst routes by on-time share, 1 crash exposure, 2 snow days against other days per route and method, 3 equity gaps, 4 scheduled frequency, 5 arrival-prediction accuracy, 6 missed trips, 7 slowest bus segments at rush hour. `frontend/src/types/api.ts` mirrors the labels. Prefer the engine-specific endpoint used by the frontend.

Both endpoints take an optional `FilterState` body (an empty or missing body uses each question's default window). `build_prebuilt_sql` puts the user's dates in place of the default window and adds the route, stop and weather predicates the question supports, with the right table alias. The response adds `applied_filters` and `skipped_filters`, lists of `dates`, `routes`, `stop` and `weather`: skipped are filters the user set that the question doesn't take, or with invalid values (a filter with some valid and some invalid values is in both lists). `explanation` is a plain sentence written for each question.

| # | Question | Dates (default window) | Routes | Stop | Weather |
|---|---|---|---|---|---|
| 0 | Worst 10 routes by on-time share | ✓ (30 days) | ✓ | – | ✓ |
| 1 | Crash exposure | – | – | ✓ | – |
| 2 | Snow vs other days | – (keeps 365 days; needs 3 snow days) | ✓ | – | – |
| 3 | Equity gaps | – | – | ✓ | – |
| 4 | Frequency | – | ✓ | – | – |
| 5 | Prediction accuracy | ✓ (30 days) | ✓ | – | – |
| 6 | Missed trips | ✓ (7 complete days) | ✓ | – | – |
| 7 | Slow segments | – (28-day mart) | ✓ (`s.route_id`) | – | – |

## Execute

```bash
curl -sS http://localhost:8000/api/query/run   -H 'Content-Type: application/json'   -d '{"engine":"duckdb","sql":"SELECT stop_id, stop_name FROM mart_gtfs_stops LIMIT 5"}'
```

`question` is optional and is used in logging. Response fields are:

| Field | Meaning |
|---|---|
| `rows` | Number of displayed records |
| `columns` | Displayed column names after enrichment |
| `data` | List of row objects |
| `total_rows` | Result size before the display truncation, not a count of all source-table rows |
| `stats` | Engine execution metadata; shape varies by engine |
| `error` | Nullable execution/validation error |

Execution always re-sanitizes server-side. Results display at most 10,000 records; SQL/engine limits still determine work performed before display. Stop IDs can add missing stop names/coordinates and route IDs can add missing route names via cached lookup tables. Lookup availability is separate from query success.

Identical engine/SQL results can be served from the process cache (180-second default TTL). `/api/filters/{engine}` caches its whole response for 10 minutes per process, unless it reported an error. This is not shared across instances and can briefly serve data from before a warehouse refresh.

## Downloads

Mart request:

```json
{
  "engine": "duckdb",
  "mart": "mart_reliability_by_route_day",
  "limit_rows": 200000,
  "date_column": "service_date_mst",
  "date_start": "2026-10-14",
  "date_end": "2026-10-25"
}
```

`limit_rows` defaults to 200,000 and accepts 1,000–2,000,000. Date filtering is applied only when all three date fields are present. `date_column` must be `service_date_mst` on a mart in `DATED_MARTS` ( the route-day, stop-hour, prediction, crowding-by-route, missed-trip, wait-by-route and run-time marts; other marts take none); anything else, a non-ISO date or a reversed range returns 400. Those seven marts are returned newest first (`ORDER BY service_date_mst DESC`), so the row limit keeps the latest rows; without dates they get `WHERE service_date_mst IS NOT NULL`, which the BigQuery guardrail requires wherever that column appears. The query still goes through guardrails. The response is `text/csv` with a download filename; it is not a Parquet endpoint, and CSV content is built in memory before the streaming response.

Allowed download marts are `MART_OPTIONS` in `api/routers/downloads.py`: the 18 app marts other than the two GTFS reference marts. The two GTFS reference marts are queryable/exported into DuckDB but absent from this CSV endpoint's separate allowlist.

Warehouse download resolves `DUCKDB_PATH` at module load. Set an absolute path in environments where path resolution matters and verify the endpoint separately from query execution. The implementation reads the binary file into memory before returning it.

## Errors and health interpretation

Pydantic request validation returns 422. Explicit `HTTPException`s use FastAPI's `detail` field: 400 for invalid download arguments or engine-specific prebuilt engine, 404 for unknown prebuilt index or missing warehouse, and 500 for download execution failures. SQL generation/validation/query handlers also encode many failures in HTTP-200 response `error` fields. Clients must check both HTTP status and body.

`/api/health` does not load artifacts or execute SQL. `/api/freshness` reports synchronization metadata, not per-source coverage; timezone formatting differs between deployments and should be read with the returned zone label. Validate actual data using [QA checks](../QA_Validation_Guide.md).
