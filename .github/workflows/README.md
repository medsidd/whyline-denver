# WhyLine Denver – GitHub Workflows Documentation

**Last Updated**: October 26, 2025

This document describes the 6 GitHub Actions workflows that automate WhyLine Denver's data pipeline. These workflows handle ingestion, transformation, testing, and CI/CD (including documentation deployment)—running over 5,500 times per year at an estimated cost of **$38** (well within GitHub's free tier).

---

## Table of Contents

1. [Overview](#overview)
2. [Workflow Architecture](#workflow-architecture)
3. [Workflow Specifications](#workflow-specifications)
4. [Scheduling Strategy](#scheduling-strategy)
5. [Secrets & Configuration](#secrets--configuration)
6. [Monitoring & Alerts](#monitoring--alerts)
7. [Troubleshooting](#troubleshooting)
8. [Cost Analysis](#cost-analysis)
9. [Additional Resources](#additional-resources)

---

## Overview

WhyLine Denver uses GitHub Actions for **end-to-end pipeline orchestration**:

```
.github/workflows/
│
├── hourly/                  (5am-7pm MST, 15x/day)
│   ├─ hourly-gtfs-rt.yml   → Capture 3 snapshots (2 min apart)
│   └─ hourly-bq-load.yml   → Load snapshots to BigQuery (+30 min offset)
│
├── nightly/                 (8am-9:30am UTC / 1-2:45am MST)
│   ├─ nightly-ingest.yml   → Refresh static data (GTFS, crashes, weather)
│   ├─ nightly-bq.yml       → dbt run/test + export marts to GCS
│   └─ nightly-duckdb.yml   → Sync DuckDB from Parquet exports
│
└── ci/                      (On push/PR, plus docs on main)
    └─ ci.yml               → Lint, format, test + dbt docs to GitHub Pages
```

**Why GitHub Actions?**
- **Free tier**: 2,000 minutes/month for private repos (WhyLine Denver uses ~800 min/month)
- **Version-controlled**: Workflows live in `.github/workflows/`; changes are auditable
- **Declarative**: YAML syntax is readable and reproducible
- **No infrastructure**: Serverless; no cron daemons or orchestrators to maintain

---

## Workflow Architecture

### Data Flow Through Workflows

```
┌─ HOURLY CYCLE (15x/day) ───────────────────────────────────────┐
│                                                                  │
│  5:00 AM MST (12:00 UTC)                                        │
│    hourly-gtfs-rt.yml triggers                                  │
│      ├─ Fetch RTD GTFS-RT APIs (Trip Updates + Vehicle Pos)    │
│      ├─ Write 3 snapshots to GCS (2 min apart)                 │
│      └─ Exit (duration: ~3 min)                                 │
│                                                                  │
│  5:30 AM MST (12:30 UTC)                                        │
│    hourly-bq-load.yml triggers (+30 min offset)                 │
│      ├─ Scan GCS for new snapshot files                        │
│      ├─ Load to raw_gtfsrt_trip_updates, raw_gtfsrt_vehicle... │
│      └─ Exit (duration: ~2 min)                                 │
│                                                                  │
│  ... repeats every hour through 7pm MST (14 more cycles)        │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘

┌─ NIGHTLY CYCLE (once per day) ─────────────────────────────────┐
│                                                                  │
│  1:00 AM MST (8:00 UTC)                                         │
│    nightly-ingest.yml triggers                                  │
│      ├─ ingest-gtfs-static (monthly GTFS ZIP)                  │
│      ├─ ingest-crashes (5y + YTD)                              │
│      ├─ ingest-sidewalks (full dataset)                        │
│      ├─ ingest-noaa (rolling 30-day weather backfill)          │
│      ├─ ingest-acs (2023 demographics, if needed)              │
│      ├─ ingest-tracts (Denver boundaries, if needed)           │
│      └─ bq-load (load all CSVs to BigQuery)                    │
│    Exit (duration: ~8 min)                                      │
│                                                                  │
│  2:00 AM MST (9:00 UTC)                                         │
│    nightly-bq.yml triggers                                      │
│      ├─ dbt parse                                              │
│      ├─ dbt run --select staging.*                            │
│      ├─ dbt run --select intermediate.*                        │
│      ├─ dbt run --select marts.*                               │
│      ├─ dbt test (40+ data quality tests)                      │
│      ├─ export marts to GCS as Parquet                         │
│      └─ upload dbt artifacts (manifest, catalog)               │
│    Exit (duration: ~12 min)                                     │
│                                                                  │
│  2:30 AM MST (9:30 UTC)                                         │
│    nightly-duckdb.yml triggers                                  │
│      ├─ Download Parquet exports from GCS                      │
│      ├─ Materialize hot marts in DuckDB                        │
│      ├─ Create views for cold marts                            │
│      └─ Update sync_state.json                                 │
│    Exit (duration: ~5 min)                                      │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Workflow Specifications

### 1. `hourly/hourly-gtfs-rt.yml` – GTFS Realtime Snapshots

**Purpose**: Capture trip delays and vehicle positions 15 times per day to build a rich temporal dataset.

**Schedule**:
```yaml
schedule:
  - cron: '0 12 * * *'  # 5am MST
  - cron: '0 13 * * *'  # 6am MST
  - cron: '0 14 * * *'  # 7am MST
  - cron: '0 15 * * *'  # 8am MST
  - cron: '0 16 * * *'  # 9am MST
  - cron: '0 17 * * *'  # 10am MST
  - cron: '0 18 * * *'  # 11am MST
  - cron: '0 19 * * *'  # 12pm MST
  - cron: '0 20 * * *'  # 1pm MST
  - cron: '0 21 * * *'  # 2pm MST
  - cron: '0 22 * * *'  # 3pm MST
  - cron: '0 23 * * *'  # 4pm MST
  - cron: '0 0 * * *'   # 5pm MST
  - cron: '0 1 * * *'   # 6pm MST
  - cron: '0 2 * * *'   # 7pm MST
```
**Rationale**: Covers service hours (5am-7pm MST) when most transit operates. Avoids late-night dead zones.

**Triggers**: Also supports `workflow_dispatch` for manual runs.

**Steps**:
1. **Checkout code** (`actions/checkout@v4`)
2. **Setup Python 3.11** (`actions/setup-python@v4`)
3. **Install dependencies** (`pip install -r requirements.txt`)
4. **Configure GCP credentials** (from `GCP_SA_KEY` secret)
5. **Run ingestion**:
   ```bash
   python -m whylinedenver.ingest.gtfs_realtime \
     --gcs \
     --bucket whylinedenver-raw \
     --snapshots 3 \
     --interval-sec 120
   ```
   This fetches both Trip Updates and Vehicle Positions APIs, then waits 2 minutes and repeats 3 times.

**Outputs**:
- `gs://whylinedenver-raw/raw/rtd_gtfsrt/snapshot_at=YYYY-MM-DDTHH:MM/trip_updates.csv.gz`
- `gs://whylinedenver-raw/raw/rtd_gtfsrt/snapshot_at=YYYY-MM-DDTHH:MM/vehicle_positions.csv.gz`

**Success Criteria**: Workflow completes in <5 minutes; QA script validates ≥40 snapshots/day.

**Common Failures**:
- RTD API timeout (503/504)
- GCS permissions issue
- GitHub Actions runner timeout (rare)

**Monitoring**: Check workflow status at [GitHub Actions](https://github.com/medsidd/whyline-denver/actions/workflows/hourly-gtfs-rt.yml).

---

### 2. `hourly/hourly-bq-load.yml` – BigQuery Hourly Load

**Purpose**: Load GTFS-RT snapshots from GCS to BigQuery tables.

**Schedule**:
```yaml
schedule:
  - cron: '30 12 * * *'  # 5:30am MST
  - cron: '30 13 * * *'  # 6:30am MST
  ... (15 total, offset +30 min from snapshots)
```
**Rationale**: 30-minute delay allows snapshot upload to complete before loading.

**Steps**:
1. **Checkout, setup Python, install deps** (same as hourly-gtfs-rt)
2. **Configure GCP credentials**
3. **Run loader**:
   ```bash
   python -m load.bq_load \
     --src gcs \
     --bucket whylinedenver-raw \
     --since $(date -u -v-1d +%Y-%m-%d)  # Last 24 hours
   ```

**Idempotency**: Loader tracks MD5 hashes in `__ingestion_log` table; duplicate files are skipped.

**Outputs**:
- Rows appended to `raw_gtfsrt_trip_updates` (partitioned by `feed_ts_utc`)
- Rows appended to `raw_gtfsrt_vehicle_positions` (partitioned by `feed_ts_utc`)

**Success Criteria**: Workflow completes in <3 minutes; no duplicate loads.

**Common Failures**:
- No new files in GCS (not an error, just no-op)
- BigQuery quota exceeded (rare; WhyLine Denver is well under limits)

---

### 3. `nightly/nightly-ingest.yml` – Static Data Refresh

**Purpose**: Refresh GTFS schedules, crashes, sidewalks, weather, and demographics.

**Schedule**:
```yaml
schedule:
  - cron: '0 8 * * *'  # 1am MST (8am UTC)
```
**Rationale**: Off-peak hours; no conflict with hourly workflows.

**Steps**:
1. **Checkout, setup Python, install deps**
2. **Configure GCP credentials**
3. **Run ingestion suite**:
   ```bash
   make nightly-ingest-bq
   # Expands to:
   #   make INGEST_DEST=gcs ingest-static
   #   make bq-load
   ```

**Ingestion Targets** (executed serially):
- `ingest-gtfs-static`: Download RTD GTFS ZIP, extract TXT files, upload to GCS
- `ingest-crashes`: Fetch Denver crash data (last 5 years + YTD) from ArcGIS API
- `ingest-sidewalks`: Fetch sidewalk segments with geometry from Denver Open Data
- `ingest-noaa`: Fetch last 30 days of weather from NOAA CDO API (rolling backfill)
- `ingest-acs`: Fetch 2023 ACS 5-year estimates (tract-level demographics)
- `ingest-tracts`: Fetch Denver census tract boundaries from TIGERweb

**Outputs**: CSVs uploaded to GCS under respective paths (e.g., `raw/noaa_daily/extract_date=YYYY-MM-DD/`)

**Then** (after ingestion completes):
- `bq-load` scans GCS for new files and loads to BigQuery

**Duration**: ~8 minutes

**Success Criteria**: All 6 ingestors succeed; BigQuery tables show new `_extract_date`.

**Common Failures**:
- NOAA API rate limit (rare; token required)
- ArcGIS API timeout (Denver Open Data sometimes slow)
- GTFS ZIP malformed (RTD publishes bad file; manually intervene)

**Monitoring**: Check workflow logs for errors; QA script validates data freshness.

---

### 4. `nightly/nightly-bq.yml` – dbt Build & Test

**Purpose**: Transform raw data into marts, validate quality, and export to GCS.

**Schedule**:
```yaml
schedule:
  - cron: '0 9 * * *'  # 2am MST (9am UTC)
```
**Rationale**: Runs 1 hour after `nightly-ingest` to ensure raw data is loaded.

**Steps**:
1. **Checkout, setup Python, install deps**
2. **Configure GCP credentials**
3. **Run dbt pipeline**:
   ```bash
   make nightly-bq
   # Expands to:
   #   DBT_TARGET=prod dbt run --project-dir dbt --target prod --select 'staging marts'
   #   DBT_TARGET=prod dbt test --project-dir dbt --target prod --select 'marts'
   #   python -m whylinedenver.sync.export_bq_marts
   ```

**dbt Execution Order**:
1. `dbt parse`: Validate project structure
2. `dbt run --select staging.*`: Build 11 staging models (views)
3. `dbt run --select intermediate.*`: Build 7 intermediate models (views)
4. `dbt run --select marts.*`: Build 7 mart models (tables, incremental)
5. `dbt test`: Run 40+ data quality tests
6. `export_bq_marts`: Export selected marts to GCS as Parquet files

**Outputs**:
- Updated BigQuery tables in `mart_denver` dataset
- Parquet files in `gs://whylinedenver-raw/marts/<mart_name>/run_date=YYYY-MM-DD/`
- dbt artifacts (manifest.json, catalog.json) uploaded to GitHub Actions artifacts

**Duration**: ~12 minutes

**Success Criteria**: All dbt models build successfully; all tests pass; exports complete.

**Common Failures**:
- dbt test failure (data quality issue; investigate specific test)
- BigQuery quota exceeded (rare)
- Export fails due to GCS permissions

**Monitoring**: Check dbt logs in workflow output; QA script validates mart freshness.

---

### 5. `nightly/nightly-duckdb.yml` – DuckDB Sync

**Purpose**: Download Parquet exports from GCS and materialize in local DuckDB.

**Schedule**:
```yaml
schedule:
  - cron: '30 9 * * *'  # 2:30am MST (9:30am UTC)
```
**Rationale**: Runs 30 minutes after `nightly-bq` to ensure Parquet exports are ready.

**Steps**:
1. **Checkout, setup Python, install deps**
2. **Configure GCP credentials**
3. **Run sync**:
   ```bash
   make nightly-duckdb
   # Expands to:
   #   python -m whylinedenver.sync.refresh_duckdb
   ```

**Sync Logic**:
1. Read `gs://whylinedenver-raw/marts/<mart>/last_export.json` to get latest run_date
2. Download Parquet files to `data/marts_cache/`
3. For each mart:
   - **Hot marts** (reliability_by_route_day, reliability_by_stop_hour): `CREATE TABLE ... AS SELECT * FROM parquet`
   - **Cold marts** (crash_proximity, vulnerability, etc.): `CREATE VIEW ... AS SELECT * FROM parquet`
4. Update `data/sync_state.json` with sync timestamps

**Outputs**:
- `data/warehouse.duckdb` (SQLite-format DuckDB file)
- `data/sync_state.json` (metadata: last sync times, record counts)

**Duration**: ~5 minutes

**Success Criteria**: DuckDB file exists; mart tables queryable; sync_state.json updated.

**Common Failures**:
- GCS download timeout (retry usually succeeds)
- DuckDB file locked (rare; only if local process is accessing it)

**Monitoring**: QA script validates DuckDB freshness; check `SELECT MAX(service_date_mst) FROM mart_reliability_by_route_day`.

---

### 6. `ci/ci.yml` – Continuous Integration

**Purpose**: Lint, format, and test code on every push and pull request.

**Triggers**:
```yaml
on:
  push:
    branches: [main, dev]
  pull_request:
    branches: [main, dev]
```

**Steps**:
1. **Checkout, setup Python 3.11**
2. **Cache pip dependencies** (speeds up subsequent runs)
3. **Install requirements**
4. **Run pre-commit hooks** (secret scanning, trailing whitespace, etc.)
5. **Lint**: `make lint` → `ruff check . && black --check .`
6. **Test**: `make test` → `pytest` (unit + integration tests)
7. **Test ingestion**: `make test-ingest` → `pytest -k ingest` (smoke tests for ingestors)

**Duration**: ~4 minutes

**Success Criteria**: All checks pass; no secrets committed; code formatted; tests green.

**Common Failures**:
- Linting error (run `make format` locally to auto-fix)
- Test failure (fix code, re-run)
- Pre-commit hook failure (e.g., detected secret in commit; rewrite history)

**Monitoring**: PR status checks show CI results; merges blocked if CI fails.

**Additional Jobs** (only on push to main):

After the `build` job passes, two additional jobs run sequentially:

**Job 2: docs** (conditional - main branch only)
1. **Checkout code**
2. **Setup Python 3.11**
3. **Cache pip dependencies**
4. **Install requirements**
5. **Configure GCP credentials** (from `GCP_SA_KEY` secret)
6. **Set environment variables** (GCP_PROJECT_ID, dataset names)
7. **Build dbt docs** (`make pages-build`)
   - Runs `make dbt-docs` (uses existing `dbt_with_env.py` infrastructure)
   - Copies artifacts to `./site/`
8. **Upload Pages artifact**

**Job 3: deploy** (conditional - main branch only)
1. **Deploy to GitHub Pages** (uses `actions/deploy-pages@v4`)
2. **Output deployment URL** (e.g., `https://medsidd.github.io/whyline-denver/`)

**Why integrated with CI?**
- dbt models only change when code is pushed
- CI already validates models compile successfully
- Reuses existing secrets (GCP_PROJECT_ID, GCP_SA_KEY)
- Simpler: one workflow instead of two
- Documentation automatically updates when tests pass

**Setup Requirements** (One-time):
1. Go to repo Settings → Pages
2. Set Source to "GitHub Actions"
3. Documentation auto-deploys on next push to main (after tests pass)

---

## Scheduling Strategy

### Hourly Workflow Timing

**Problem**: GitHub Actions cron is not guaranteed to run exactly on schedule (can delay 5-15 minutes during peak times).

**Solution**: Use 15 discrete cron jobs instead of a single job running every hour. This maximizes chance of capturing all service hours even if some runs delay.

**Coverage Window**: 5am-7pm MST (14 hours) → 15 runs × 3 snapshots = **45 snapshots/day**

**Why 3 snapshots per run?** Smooths over API jitter. If one snapshot fails (503 error), we still capture 2 others.

**Why 2-minute intervals?** GTFS-RT feeds update every 1-2 minutes; 2-minute spacing avoids duplicate data.

### Nightly Workflow Sequencing

**Dependency Chain**:
```
nightly-ingest (8am UTC)
    ↓ +1 hour
nightly-bq (9am UTC)
    ↓ +30 min
nightly-duckdb (9:30am UTC)
```

**Why time gaps?**
- Ensures raw data is loaded before dbt runs
- Ensures Parquet exports complete before DuckDB sync
- Avoids race conditions (e.g., dbt reading partially-loaded tables)

**Fallback**: If a workflow fails, subsequent workflows still run (no hard dependencies). Manual intervention may be needed to backfill.

---

## Secrets & Configuration

### GitHub Secrets Required

| Secret Name | Purpose | Format |
|-------------|---------|--------|
| `GCP_SA_KEY` | Service account JSON for GCS/BigQuery access | Base64-encoded JSON |
| `GCP_PROJECT_ID` | Google Cloud project ID | String (e.g., `whyline-denver`) |
| `GCS_BUCKET` | GCS bucket name for raw data | String (e.g., `whylinedenver-raw`) |
| `NOAA_CDO_TOKEN` | NOAA Climate Data Online API key | String |
| `CENSUS_API_KEY` | U.S. Census Bureau API key (optional) | String |

**How to Add Secrets**:
1. Go to repo → Settings → Secrets and variables → Actions
2. Click "New repository secret"
3. Paste value (for `GCP_SA_KEY`, base64-encode the JSON first)

### Environment Variables in Workflows

Set in workflow YAML under `env`:
```yaml
env:
  GCP_PROJECT_ID: ${{ secrets.GCP_PROJECT_ID }}
  GCS_BUCKET: ${{ secrets.GCS_BUCKET }}
  NOAA_CDO_TOKEN: ${{ secrets.NOAA_CDO_TOKEN }}
  BQ_DATASET_RAW: raw_denver
  BQ_DATASET_STG: stg_denver
  BQ_DATASET_MART: mart_denver
  ENGINE: bigquery
```

These are injected into the Python process when scripts run.

---

## Monitoring & Alerts

### GitHub Actions Status Badges

README displays live status for each workflow:

```markdown
![CI](https://github.com/medsidd/whyline-denver/actions/workflows/ci.yml/badge.svg)
![Nightly Ingest](https://github.com/medsidd/whyline-denver/actions/workflows/nightly-ingest.yml/badge.svg)
![Nightly BQ](https://github.com/medsidd/whyline-denver/actions/workflows/nightly-bq.yml/badge.svg)
![Nightly DuckDB](https://github.com/medsidd/whyline-denver/actions/workflows/nightly-duckdb.yml/badge.svg)
```

Green badge = recent runs succeeded. Red badge = investigate.

### QA Validation Script

Run `./scripts/qa_script.sh` to validate:
- Workflow success rates (should be >80%)
- Data freshness (GTFS-RT <2 hours old, weather <7 days behind)
- Row counts (40+ snapshots/day)

See [docs/QA_Validation_Guide.md](../../docs/QA_Validation_Guide.md) for details.

### Manual Workflow Inspection

```bash
# List recent runs for a workflow
gh run list --workflow=hourly-gtfs-rt.yml --limit 20

# View specific run details
gh run view <run-id>

# Download logs for debugging
gh run view <run-id> --log > logs.txt
```

### Alerts

**Current State**: Manual monitoring via status badges + QA script.

**Future Enhancement**: Set up GitHub Actions notifications to Slack/email on workflow failure.

---

## Troubleshooting

### Problem: Hourly workflow shows "skipped" runs

**Cause**: GitHub Actions has a 10-minute startup latency during peak times. If multiple workflows queue, some may skip.

**Solution**: Accept that 1-2 runs/day may skip. QA script validates ≥40 snapshots/day (out of 45 possible), allowing 5 misses.

**Mitigation**: Consider switching to a dedicated orchestrator (Airflow, Prefect) if reliability needs increase.

---

### Problem: Nightly-BQ workflow fails with "BigQuery quota exceeded"

**Cause**: dbt run scans too much data in a single day (>1TB).

**Solution**:
1. Check which models are scanning excessive data: `dbt run --select marts.* --log-level debug`
2. Add partitioning/clustering to large tables
3. Use incremental models instead of full refreshes

WhyLine Denver scans ~100GB/month, well under 1TB free tier.

---

### Problem: dbt test fails with "unique constraint violated"

**Cause**: Duplicate rows in a model (e.g., `unique(route_id)` fails).

**Investigation**:
```sql
-- Find duplicates
SELECT route_id, COUNT(*) as cnt
FROM stg_denver.stg_gtfs_routes
GROUP BY route_id
HAVING COUNT(*) > 1;
```

**Common Root Causes**:
- Deduplication logic broken (e.g., window rank not filtering `rank = 1`)
- Multiple ingestion extracts loaded without deduplication

**Fix**: Review staging model SQL; ensure `WHERE rank = 1` or equivalent logic.

---

### Problem: Export to GCS fails with "403 Forbidden"

**Cause**: Service account lacks `storage.objects.create` permission.

**Solution**:
1. Go to GCP Console → IAM & Admin → Service Accounts
2. Find service account (e.g., `whyline-dbt@whyline-denver.iam.gserviceaccount.com`)
3. Grant "Storage Object Creator" role on bucket `whylinedenver-raw`

---

### Problem: DuckDB sync shows "file locked"

**Cause**: Another process (e.g., local Streamlit app) is accessing `data/warehouse.duckdb`.

**Solution**: Kill local processes, then manually run:
```bash
make sync-duckdb
```

In CI, this shouldn't happen since workflows don't overlap.

---

## Cost Analysis

### Estimated Annual Costs

| Component | Usage | Cost/Year |
|-----------|-------|-----------|
| **GitHub Actions compute** | ~800 min/month × 12 = 9,600 min | $0 (within 2,000 min/month free tier) |
| **GCS storage** | 18GB (16GB GTFS-RT + 2GB exports) | $0.55 |
| **BigQuery storage** | 25GB (raw + staging + marts) | $0.50 |
| **BigQuery compute** | 365 dbt runs, ~100GB scanned/day | ~$7 (within 1TB/month free tier) |
| **Data transfer (egress)** | Minimal (Parquet exports to GCS) | <$0.10 |
| **TOTAL** | | **~$8/year** |

**Key Insight**: GitHub Actions is free for WhyLine Denver's usage. BigQuery scans are well under the 1TB/month free tier. Storage costs dominate but are negligible.

**Comparison**: Running equivalent pipelines on Airflow/EC2 would cost ~$100-200/year (t3.small instance + EBS storage).

---

## Additional Resources

- **[Root README](../../README.md)** – Project overview, quickstart, FAQ
- **[dbt Models Documentation](../../dbt/models/README.md)** – All 29 models, tests, and materialization strategies
- **[Pipeline Architecture](../../docs/ARCHITECTURE.md)** – Full data flow from ingestion to marts
- **[QA Validation Guide](../../docs/QA_Validation_Guide.md)** – How to validate pipeline health
- **[Data Contracts](../../docs/contracts/CONTRACTS.md)** – Schema specifications for raw outputs

---

**Questions?** Check workflow logs in GitHub Actions UI or run the QA script: `./scripts/qa_script.sh`.
