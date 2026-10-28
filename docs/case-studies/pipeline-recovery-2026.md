# October 2026 pipeline recovery

This case study retains the design and debugging lessons from the October 14–15 recovery. It consolidates the old restart, follow-up, weather/CI, and imported pause notes. These are dated outcomes, not guarantees of current source coverage or permission to run cloud jobs. See [operations](../technical/OPERATIONS.md) for the newer live snapshot.

## Why recovery was needed

An August 11 cost-control decision paused recurring processing while retaining BigQuery/GCS data and the website. The user later authorized resuming the cloud pipeline and separately approved publishing/running the repairs. The recovery verified both schedules and real processing, rather than equating a running local dashboard with a resumed cloud system.

The historical pause explains why retained warehouses could be stale. It is not today's operating policy: October 26 readback showed both recurring schedulers enabled and nightly workflows active/succeeding. Historical cost totals are not reused as current measurements.

## Failures, fixes, and durable lessons

| Failure | Implemented repair | Lesson |
|---|---|---|
| Census returned an HTML Missing Key response | Explicitly mapped existing `CENSUS_API_KEY` into nightly ingestion | A stored secret name does not prove the consuming process receives it. Inspect bindings without exposing values. |
| Unassigned realtime events produced null-route aggregates and failed mart tests | Excluded null route IDs from route-level aggregation; preserved source/staging events | Apply validity rules at the analytical grain rather than deleting retained raw evidence. |
| Weather extract had entirely missing precipitation | Changed inactive/no-coverage station default from Central Park `USW00023062` to DIA `USW00003017`, matching dbt | Verify station/metric/date coverage; a successful HTTP response is not complete weather data. |
| Weather units were inferred from magnitude | Treat CDO metric values and compatible local CSVs directly as mm/Celsius | Units come from the source contract, not value size. |
| Missing weather looked like dry weather | Preserved nulls, used route-day `unknown`, excluded unknown comparisons | Preserve uncertainty through derived metrics; missing is not zero/dry. |
| Older corrected partitions could be skipped during export | Included newer `build_run_at` partitions and bounded forced-export options | A latest-date checkpoint cannot represent all revisions to historical data. |
| CI reused stale dbt artifacts and then depended on local `.env` | Parse current dbt into temporary output, use a small catalog fixture and explicit dummy settings | Test current source offline and reproduce tests in a clean environment. |
| Shared cloud image initially omitted the dbt launcher | Included `tools/` and deployed an immutable image to both realtime jobs | Trace the real execution path and verify every deployment consumer. |
| Local frontend dependencies/watchers failed | Restored lockfile dependencies with `npm ci`; used polling for `EMFILE` | Check installation and host limits before rewriting application code. |

## Published evidence

- [Commit 3b31cc9](https://github.com/medsidd/whyline-denver/commit/3b31cc9): Census secret binding, null-route fix, and regression cases.
- [Commit 3d8a245](https://github.com/medsidd/whyline-denver/commit/3d8a245): station/units/missingness, raw layout support, late exports, offline artifact tests, and documentation.
- [Commit a723429](https://github.com/medsidd/whyline-denver/commit/a723429): explicit offline test environment settings.
- [Initial successful ingestion](https://github.com/medsidd/whyline-denver/actions/runs/38691066361), [BigQuery build/tests/export](https://github.com/medsidd/whyline-denver/actions/runs/38691657471), and [DuckDB refresh](https://github.com/medsidd/whyline-denver/actions/runs/38693600090).
- [Weather ingestion](https://github.com/medsidd/whyline-denver/actions/runs/38734375074), [passing CI](https://github.com/medsidd/whyline-denver/actions/runs/38734586593), and [corrected DuckDB refresh](https://github.com/medsidd/whyline-denver/actions/runs/38735780580).

The initial recovery completed 19 selected models and 42 data tests, exported all nine marts, and verified public DuckDB results through October 15 with zero null route IDs and 8,266 reference stops. These are historical counts, not today's warehouse inventory or coverage targets.

The weather repair reduced that extract's missing precipitation from 30/30 days to 4/30, but the missing dates still did not overlap with resumed transit observations. Public weather comparisons were deliberately empty at the final check. This verified correct handling of unavailable data, not a failure to produce a chart. The final CI passed 37 tests in that revision/environment.

## Recovery procedure worth retaining

1. Preserve unrelated work and inspect code/configuration without dumping credentials.
2. Separate enabled schedules, successful executions, data freshness, coverage, and actual public results.
3. Repair the root cause once and cover incremental/full and missing-data paths as relevant.
4. Publish only authorized source changes; ensure batch workflows and both realtime images use the repaired source.
5. Run ingestion, then transformation/tests/export, then DuckDB refresh sequentially, verifying completion between stages.
6. Query actual BigQuery/DuckDB/public results; timestamps alone cannot prove a new warehouse loaded.
7. Record remaining upstream gaps and billing checks separately from operational success.

No full current billing audit was performed during that recovery; the October 26 billing snapshot in operations is newer evidence. Image digests and execution IDs from individual recovery attempts are intentionally omitted from the active runbook; inspect current revisions before planning rollback.
