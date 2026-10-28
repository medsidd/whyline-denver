# BigQuery cost optimization: lessons from 2025

This is retained engineering history explaining current design choices. It is not a current runbook, price list, or verified bill. The former long case study and December cost report mixed different workload projections and contained inconsistent arithmetic. Those figures are not retained as measured outcomes. [Operations](../technical/OPERATIONS.md) records the current dated billing snapshot and refresh method.

## 1. Avoid one query per input file

The early loader checked ingestion history repeatedly for files it had already seen. Even a tiny metadata table can create substantial query volume and minimum-billing overhead when queried once per file at high frequency.

The design moved toward loading ingestion history into process-local lookup structures and using source hashes to skip identical file loads. The useful lesson is to avoid unnecessary warehouse round trips before optimizing the warehouse query itself. Inspect `src/whyline/load/bq_load.py` and `registry.py` for the current implementation; historical query-count estimates are not a present workload measurement.

MD5-based file deduplication does not eliminate different extracts containing the same logical observation. Staging still needs a deliberate business grain and version-selection policy.

## 2. Prune at the source boundary

Downstream date filters do not necessarily prevent upstream views/joins or MERGE targets from scanning more history. The historical investigation compared query plans/bytes after changes rather than assuming that adding a date column or materialization always reduced cost.

Current realtime staging includes both a narrow incremental timestamp window and explicit raw date predicates. When changing it, inspect source and target scan behavior, late-arrival coverage, and full-refresh behavior. A smaller window saves work only if it still reaches the corrections the application needs.

## 3. Materialize according to repeated work

A view avoids stored derived data but can repeat expensive schedule expansion every time a dependent query runs. Materializing every layer can instead add large rebuild/MERGE costs. Earlier attempts explored both and changed direction as the analysis scope grew.

The current compromise includes a table for scheduled arrivals, incremental realtime staging/headway tables, and partitioned reliability marts. These choices reflect repeated work and historical scope, not a universal preference for views or tables. The old case study's long-range schedule expansion was especially useful for showing how increasing the analysis window can invalidate a previously cheap architecture.

A materialized dependency also needs a refresh owner. The current nightly selection does not explicitly rebuild every intermediate table; use deliberate layer/ancestor selections when rebuilding schedules. Documentation must describe that actual behavior rather than promising a full DAG rebuild.

## 4. Grain and nulls matter to incremental correctness

The historical recovery encountered duplicate rows and MERGE behavior after grain/key changes. The durable lesson is to prove the actual output grain, handle nullable keys intentionally, and test both initial/full and incremental paths. Declaring a `unique_key` is not proof that the source is unique or the target has been cleaned.

Current realtime staging selects one record per feed timestamp/trip, while stop-hour and route-day marts have different grouped grains. See [model reference](../../dbt/models/README.md) for the exact current definitions. Do not copy a historical key into a different model.

## 5. Frequency multiplies per-run work

A modest query cost repeated every few minutes can dominate a small project's bill. Capture frequency, load/transform frequency, retained history, and serving freshness are separate knobs. The old five-minute schedule was later reduced; the October 26, 2026 readback shows 15-minute jobs.

Evaluate cost per completed run, runs per day, and observed billing together. Extrapolations must state their workload, time range, and credit assumptions. An estimate made before a pause or architecture change should not appear as today's annual cost.

## 6. Deployment and billing evidence are separate

Changes in GitHub batch source do not automatically update Cloud Run job images. Apply the tested immutable digest to both realtime jobs and confirm executions use it. A pushed `:latest` tag is insufficient.

BigQuery job metadata helps attribute query work, but processed bytes, billed bytes, list-price estimates, gross charges, credits, and net invoices are different measures. Use the billing export for actual cost totals and bounded regional job metadata for workload diagnosis. Include storage and other services when describing platform cost.

## What to reuse

Measure before/after over comparable windows, change the dominant repeated work, check correctness and missingness, deploy every execution path, and then remeasure net billing. Preserve raw inputs for replay. Keep [current architecture](../technical/ARCHITECTURE.md), [deployment](../technical/DEPLOYMENT.md), and [operations](../technical/OPERATIONS.md) separate from historical projections.
