# API Reference

The WhyLine Denver API is a FastAPI service running on port 8080 (Cloud Run) or 8000 (local dev). All endpoints are prefixed with `/api`.

**Base URL (local)**: `http://localhost:8000`
**Base URL (production)**: Cloud Run service URL (set as `API_BASE_URL` in Vercel)

---

## Health

### GET /api/health

Returns service status and the default query engine.

**Response**

```json
{
  "status": "ok",
  "engine_default": "duckdb"
}
```

`engine_default` reflects the `ENGINE` environment variable.

---

### GET /api/freshness

Returns human-readable timestamps for when each engine's data was last updated.

**Response**

```json
{
  "bigquery_freshness": "2025-03-01 09:05 UTC",
  "duckdb_freshness": "2025-03-01 09:32 UTC"
}
```

Sources: `dbt/target/run_results.json` → `sync_state.json` → latest `run_date` in mart tables. Returns `"Unavailable"` if none of those are readable.

---

## Filters

### GET /api/filters/{engine_name}

Returns the available filter options for the sidebar. Use this to populate the routes dropdown and date range controls.

**Path parameters**

| Parameter | Values | Required |
|-----------|--------|----------|
| `engine_name` | `"duckdb"` or `"bigquery"` | Yes |

**Response**

```json
{
  "routes": ["1", "15L", "16", "40", "83"],
  "weather_bins": ["heavy", "light", "mod", "none"],
  "date_min": "2024-10-01",
  "date_max": "2025-03-01",
  "error": null
}
```

Source: distinct values from `mart_reliability_by_route_day`. `error` is a string if the routes query failed (e.g., DuckDB file not found), `null` otherwise.

---

### GET /api/filters/{engine_name}/stops

Returns all transit stops with coordinates. Intended for stop-level filtering.

**Path parameters**: same as above

**Response**

```json
[
  {
    "stop_id": "1234",
    "stop_name": "Colfax & Broadway",
    "stop_lat": 39.7392,
    "stop_lon": -104.9880
  }
]
```

Returns an empty list for DuckDB (stop geometry is fetched from BigQuery staging only). For BigQuery, queries `stg_gtfs_stops`.

---

### GET /api/models

Returns all dbt models available for querying, with column descriptions.

**Response**

```json
{
  "models": [
    {
      "name": "mart_reliability_by_route_day",
      "fq_name": "`whyline-denver.mart_denver.mart_reliability_by_route_day`",
      "description": "Daily on-time performance by route and weather condition.",
      "columns": {
        "route_id": {
          "name": "route_id",
          "type": "STRING",
          "description": "Transit route identifier"
        },
        "pct_on_time": {
          "name": "pct_on_time",
          "type": "FLOAT64",
          "description": "Fraction of stop events within 300 seconds of schedule"
        }
      }
    }
  ]
}
```

Only models with `meta.allow_in_app: true` in their dbt schema.yml are included. Loaded from `dbt/target/manifest.json` once at process startup.

---

## SQL Generation and Validation

### POST /api/sql/generate

Converts a natural language question into SQL using the LLM.

**Request body**

```json
{
  "question": "Which routes have the worst on-time performance in snow?",
  "engine": "duckdb",
  "filters": {
    "start_date": "2025-01-01",
    "end_date": "2025-03-01",
    "routes": ["1", "15L"],
    "stop_id": "",
    "weather": ["snow", "heavy"]
  }
}
```

All `filters` fields are optional. `start_date` and `end_date` are ISO 8601 date strings.

**Response**

```json
{
  "sql": "SELECT route_id, AVG(pct_on_time) AS avg_on_time\nFROM mart_reliability_by_route_day\nWHERE precip_bin IN ('snow', 'heavy')\n  AND service_date_mst BETWEEN '2025-01-01' AND '2025-03-01'\nGROUP BY route_id\nORDER BY avg_on_time ASC\nLIMIT 10",
  "explanation": "This query ranks routes by average on-time performance during snow conditions between January and March 2025. Lower values indicate worse service, helping planners identify which routes degrade most in winter weather.",
  "cache_hit": false,
  "error": null
}
```

`cache_hit: true` if the exact same (provider, engine, question, filters) was already answered this session — no LLM call was made.

**Generation flow**:
1. Check prompt cache
2. Build schema brief + prompt
3. Call LLM (`GEMINI_API_KEY` required; falls back to stub if `LLM_PROVIDER=stub`)
4. Inject filter clauses into SQL
5. Sanitize (guardrails) + adapt dialect
6. Cache and return

---

### POST /api/sql/validate

Validates and sanitizes a SQL string. Use this to check user-edited SQL before running.

**Request body**

```json
{
  "sql": "SELECT route_id, COUNT(*) FROM mart_reliability_by_route_day GROUP BY route_id",
  "engine": "duckdb"
}
```

**Response**

```json
{
  "valid": true,
  "sanitized_sql": "SELECT route_id, COUNT(*) FROM mart_reliability_by_route_day GROUP BY route_id LIMIT 5000",
  "bq_est_bytes": null,
  "error": null
}
```

For `engine: "bigquery"`, `bq_est_bytes` contains the estimated bytes the query would scan (from a BigQuery dry-run). For DuckDB, it is `null`.

**Guardrail rules applied** (returns `valid: false` with `error` message if any fail):
- Must be a single SELECT statement
- No INSERT, UPDATE, DELETE, CREATE, DROP, ALTER, MERGE, TRUNCATE, GRANT, REVOKE
- All table/CTE references must be in the dbt allowlist
- BigQuery only: project and dataset must match configured values
- Appends `LIMIT 5000` if no LIMIT clause is present

---

### POST /api/sql/prebuilt/{index}

Returns one of four pre-written analytical queries.

**Path parameters**

| Index | Question |
|-------|---------|
| 0 | Worst 10 routes by average on-time performance (last 30 days) |
| 1 | Stops with highest crash exposure |
| 2 | Where snow hurts reliability most |
| 3 | Equity gaps — high vulnerability stops with low reliability |

**Response**: same shape as `/api/sql/generate`.

---

### POST /api/sql/prebuilt/{index}/for/{engine_name}

Same as above but explicitly adapts the SQL for the given engine.

---

## Query Execution

### POST /api/query/run

Executes a SQL query and returns results.

**Request body**

```json
{
  "sql": "SELECT route_id, AVG(pct_on_time) FROM mart_reliability_by_route_day GROUP BY route_id ORDER BY 2 ASC LIMIT 10",
  "engine": "duckdb",
  "question": "Worst-performing routes"
}
```

`question` is optional — used only for logging.

**Response**

```json
{
  "rows": 10,
  "columns": ["route_id", "avg_pct_on_time", "stop_name", "lat", "lon"],
  "data": [
    {
      "route_id": "83",
      "avg_pct_on_time": 0.612,
      "route_name": "83 Martin Luther King Jr",
      "route_long_name": "Martin Luther King Junior Boulevard"
    }
  ],
  "total_rows": 10,
  "stats": {
    "engine": "duckdb",
    "rows": 10,
    "latency_ms": 42
  },
  "error": null
}
```

**Result enrichment**: Before returning:
- If `stop_id` is in the columns, a left-join with `mart_gtfs_stops` adds `stop_name`, `lat`, `lon`
- If `route_id` is in the columns, a left-join with `mart_gtfs_routes` adds `route_name`, `route_long_name`

**Display limit**: Up to 10,000 rows are returned. `total_rows` reflects the actual result count before the limit.

**Server-side re-sanitization**: The API always re-sanitizes and re-adapts the SQL from the client. The client's `sanitized_sql` is never trusted.

**Caching**: Identical (engine, SQL) pairs return a cached result within the same process session.

---

## Downloads

### POST /api/downloads/mart

Streams a full mart table as a CSV file download.

**Request body**

```json
{
  "engine": "duckdb",
  "mart": "mart_reliability_by_route_day",
  "limit_rows": 200000,
  "date_column": "service_date_mst",
  "date_start": "2025-01-01",
  "date_end": "2025-03-01"
}
```

`date_column`, `date_start`, and `date_end` are optional. `limit_rows` must be between 1,000 and 2,000,000.

**Allowed `mart` values**:
- `mart_reliability_by_route_day`
- `mart_reliability_by_stop_hour`
- `mart_crash_proximity_by_stop`
- `mart_access_score_by_stop`
- `mart_vulnerability_by_stop`
- `mart_priority_hotspots`
- `mart_weather_impacts`

**Response**: Streaming CSV with `Content-Disposition: attachment` header.

---

### GET /api/downloads/warehouse

Downloads the local DuckDB warehouse binary file.

**Response**: Streaming binary file (`warehouse.duckdb`). Returns 404 if `DUCKDB_PATH` does not exist.

This allows stakeholders to download the entire warehouse for local analysis in any DuckDB client.

---

## Error handling

All error responses follow the same pattern:

```json
{
  "error": "Human-readable error message",
  ... other fields are null or empty ...
}
```

HTTP status codes:
- `200` — success (including partial failures described in `error` field)
- `404` — resource not found (warehouse file, invalid mart name)
- `422` — request validation error (FastAPI Pydantic model mismatch)
- `500` — unexpected server error

---

## Development

Start the API locally:

```bash
make api-dev   # FastAPI with hot reload at http://localhost:8000
```

The interactive OpenAPI docs are available at `http://localhost:8000/docs`.

Test the API:

```bash
make api-test  # pytest suite for api/ endpoints
```

```bash
# Quick smoke test
curl http://localhost:8000/api/health
curl http://localhost:8000/api/freshness
curl http://localhost:8000/api/filters/duckdb
curl -X POST http://localhost:8000/api/sql/prebuilt/0
curl -X POST http://localhost:8000/api/query/run \
  -H "Content-Type: application/json" \
  -d '{"sql":"SELECT route_id, AVG(pct_on_time) avg FROM mart_reliability_by_route_day GROUP BY 1 ORDER BY 2 LIMIT 5","engine":"duckdb"}'
```
