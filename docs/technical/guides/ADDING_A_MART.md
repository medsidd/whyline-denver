# Add a mart

Define the question, output grain, missingness policy, units, and score direction first. Read the closest existing SQL and [metric glossary](../../public/METRICS_GLOSSARY.md). A mart is an analysis contract, not just a table exposed to an LLM.

Build serving marts from gold core only (`ref('dim_*')`, `ref('fct_*')`, `ref('bridge_*')`), never from silver `stg_*` models. If the question needs a new business process, add a fact with a declared grain and dimension keys in `dbt/models/core/` first, and check the bus matrix in the [model reference](../../../dbt/models/README.md). Join Type 2 dimensions on the natural key plus `is_latest_version` (labels) or `is_current` (current network only). Append descriptive columns such as names and coordinates at the end so the LLM can answer without joins; `build_schema_brief` lists every column.

## Reach every consumer

| Place | Change |
|---|---|
| `dbt/models/marts/<domain>/mart_*.sql` | SQL, materialization, stable grain/key, `meta={'allow_in_app': true}` for app exposure |
| Relevant schema YAML | A description for every column (units, nullability), and quality tests. `persist_docs` copies them to BigQuery, so an undescribed column shows blank there |
| `src/whyline/sync/constants.py` | Add to `ALLOWLISTED_MARTS`; API schema exposure requires both this list and manifest config metadata |
| `api/routers/downloads.py` | Add to `MART_OPTIONS` if CSV downloads are intended; `ALLOWED_MARTS` is derived from that list |
| `frontend/src/types/api.ts` and DownloadPanel consumers | Update the frontend mart options/types if exposing the new download |
| Tests/fixtures and docs | Model grain, incremental/late changes, schema exposure, public definitions |

Read actual consumers with `rg` before editing these names.

## Materialization

Use a snapshot table for a full current analysis or an incremental date-partitioned model for time-series data. Assess repeated joins, target merge scans, late source corrections, and key uniqueness. A view can repeatedly recompute expensive dependencies. Do not use insert-overwrite unless replacing complete selected partitions is correct.

Include `current_timestamp() AS build_run_at`, not a DATE, so rebuilt rows can be told from old ones. For an incremental model, choose a bounded lookback that actually reaches corrections; filters must prune both relevant source and target work where appropriate. Compare full-refresh and incremental results.

Document metadata in schema YAML and configure app exposure on the SQL model. Existing range tests use the project's `accepted_range` macro; the project does not require an invented `dbt_utils` dependency for that test.

## Build, validate, and publish

Use the repository wrapper/profile from the root; for an authorized cloud build:

```bash
PYTHONPATH=src python -m tools.dbt_with_env run --project-dir dbt --target prod --select +mart_your_metric
PYTHONPATH=src python -m tools.dbt_with_env test --project-dir dbt --target prod --select mart_your_metric
```

Replace the example name. A leading `+` includes ancestors; a trailing `+` includes descendants. Running an existing model with `--full-refresh` is not a read-only verification step and may be expensive.

After a build, regenerate or obtain matching manifest/catalog artifacts, redeploy the API (its image carries them), and verify `/api/models` plus a real query. Check CSV download separately if enabled. For new visualization columns, inspect `frontend/src/lib/chartLogic.ts` and result rendering rather than assuming any shape produces a useful chart.

Shared SQL fixes used by realtime processing must reach the realtime image (job and VM) as well as the GitHub batch workflows. Follow [deployment](../DEPLOYMENT.md) and verify the deployed image and actual served data.
