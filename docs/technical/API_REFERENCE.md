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

`question` is required. `filters` is optional and defaults to empty/null fields. Its shape is `FilterState`: nullable `start_date`/`end_date` strings, route/weather string lists, and a stop string. The implementation injects supported conditions when relevant column names appear in generated SQL; filters are not a universal relational query builder and do not automatically rewrite arbitrary edited SQL or raw prebuilt queries. Review the actual SQL.

Response: `sql`, `explanation`, `cache_hit`, `error`. Provider/guardrail failures can return HTTP 200 with a non-null `error`. Prompt cache keys include provider, engine, question, and filters; default TTL is 900 seconds per process. Gemini sends the question, filters, and schema brief to the provider. Stub avoids provider calls; other named providers are unimplemented.

## Validate SQL

Request to `/api/sql/validate`:

```json
{"sql":"SELECT stop_id, stop_name FROM mart_gtfs_stops LIMIT 10","engine":"duckdb"}
```

Response fields: `valid`, nullable `sanitized_sql`, nullable `bq_est_bytes`, nullable `error`. BigQuery estimation errors are nonfatal, so `valid: true` with no estimate does not prove the query will execute.

Guardrails accept one SELECT/WITH statement, reject denylisted write keywords, and check referenced table/project/dataset allowlists. They add `LIMIT 5000` only when a numeric limit is absent; existing limits are not reduced. BigQuery's partition-filter suggestion checks for a configured date column without a WHERE clause; it does not guarantee effective partition pruning. These are regex checks and must be backed by least-privilege database credentials.

## Prebuilt SQL

Indices 0–3 correspond to worst routes, crash exposure, a weather comparison, and equity gaps. Prefer the engine-specific endpoint used by the frontend. The weather card's label mentions snow, but its SQL filters moderate/heavy precipitation (`mod`, `heavy`), not `snow_day`; it must not be interpreted as a snow-only comparison.

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

Identical engine/SQL results can be served from the process cache (180-second default TTL). This is not shared across instances and can briefly serve data from before a warehouse refresh.

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

`limit_rows` defaults to 200,000 and accepts 1,000–2,000,000. Date filtering is applied only when all three date fields are present. Reversed date ranges return 400. The query still goes through guardrails. The response is `text/csv` with a download filename; it is not a Parquet endpoint, and CSV content is built in memory before the streaming response.

Allowed download marts: route-day reliability, stop-hour reliability, crash proximity, sidewalk access, vulnerability, priority hotspots, and weather impacts. The two GTFS reference marts are queryable/exported into DuckDB but absent from this CSV endpoint's separate allowlist.

Warehouse download resolves `DUCKDB_PATH` at module load. Set an absolute path in environments where path resolution matters and verify the endpoint separately from query execution. The implementation reads the binary file into memory before returning it.

## Errors and health interpretation

Pydantic request validation returns 422. Explicit `HTTPException`s use FastAPI's `detail` field: 400 for invalid download arguments or engine-specific prebuilt engine, 404 for unknown prebuilt index or missing warehouse, and 500 for download execution failures. SQL generation/validation/query handlers also encode many failures in HTTP-200 response `error` fields. Clients must check both HTTP status and body.

`/api/health` does not load artifacts or execute SQL. `/api/freshness` reports synchronization metadata, not per-source coverage; timezone formatting differs between deployments and should be read with the returned zone label. Validate actual data using [QA checks](../QA_Validation_Guide.md).
