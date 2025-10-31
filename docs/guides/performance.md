# Streamlit Performance & Stability Guide

This app is sensitive to re-runs and remote I/O. Use the settings below to keep interactions snappy and stable in Cloud Run.

## 1) Reuse heavy resources (already wired)

The DuckDB engine now:
- Reuses one connection per thread (no reconnect on every widget change)
- Copies the database file to local ephemeral storage on first use to avoid GCS FUSE latency
- Applies conservative PRAGMAs for threads/memory/temp directory

Environment variables you can tune:
- DUCKDB_PATH: Absolute or relative path to the warehouse file (e.g., /mnt/gcs/<bucket>/warehouse.duckdb)
- DUCKDB_COPY_LOCAL: Set to "0" to disable local copy (default: "1")
- DUCKDB_LOCAL_PATH: Local destination path (default: /tmp/warehouse.duckdb)
- DUCKDB_READ_ONLY: "1" for read-only (default), "0" to allow writes
- DUCKDB_THREADS: Number of DuckDB threads (default: 2)
- DUCKDB_MEMORY_LIMIT: Memory limit (default: 1GB)
- DUCKDB_TEMP_DIR: Temp directory (default: system temp)

## 2) Cloud Run settings

- Concurrency: 10 recommended for Python+Streamlit
- CPU: 2 vCPU
- Memory: 2GiB or 4GiB if large DataFrames
- Minimum instances: 1 if cold start latency matters
- Timeout: 600s (to handle large exports)

## 3) NGINX proxy for Streamlit

`deploy/streamlit-service/nginx.conf` is configured for:
- WebSockets/streaming with `Upgrade`/`Connection` headers
- Long timeouts: `proxy_read_timeout 86400` and buffering disabled
- Static asset caching and SEO endpoints

## 4) Memory hygiene

- Avoid stashing very large DataFrames in `st.session_state`; prefer parameters in session and cache results with `st.cache_data`.
- Downsample before rendering heavy charts/maps (the app does this for common cases).
- Logs are rotated at ~10MB automatically (`data/logs/queries.jsonl`).

## 5) BigQuery engine (optional)

- Uses dry run to estimate bytes and `maximum_bytes_billed` to cap cost
- Caches dbt model allowlist and schema qualifications

## 6) Troubleshooting

- If you still see pauses on every widget, check that Cloud Run traffic reaches Streamlit via NGINX (`/app/` path) and that concurrency isn’t too high.
- If DuckDB queries are slow in production only, verify the database is being opened from `/tmp/warehouse.duckdb` (set `DUCKDB_COPY_LOCAL=1` and log the resolved path if needed).
