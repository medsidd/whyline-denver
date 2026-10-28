# Add a data source

Read an existing ingestor with the closest source format, [raw contracts](../../contracts/CONTRACTS.md), and the actual `load/registry.py` definitions before changing anything. Seven ingestors exist today; a new source needs explicit registration, not just a new file.

## Required reach

| Place | Required decision/change |
|---|---|
| `src/whyline/ingest/<source>.py` | Fetch, normalize, validate, serialize, local/GCS output, idempotency, manifest, argparse CLI |
| `src/whyline/load/registry.py` | Add a `JobSpec` with ordered types/patterns, partition/clustering if appropriate |
| `dbt/models/sources_raw.yml` | Declare the new raw source table under source name `raw` |
| `dbt/models/staging/` and schema YAML | Cleaning/deduplication policy, documentation, data assertions |
| `Makefile` | Target using `$(PY)` and `$(INGEST_MODE_ARGS)`; add to `ingest-all` and, if appropriate, `ingest-static` |
| `.github/workflows/nightly-ingest.yml` | Map any new secret into the consuming step; existing recipe calls `ingest-static`, not `ingest-all` |
| `tests/ingest/` and fixtures | Contract, missing/invalid/empty data, manifests, skip/retry behavior; mock external calls |
| Documentation | Source coverage, contract, pipeline inventory, and any resulting mart semantics |

## Follow the existing I/O pattern

Reuse `whyline.ingest.io` for retries, logging, manifests, hashing, file-existence checks, and GCS writes. Read helper signatures; private source-local helpers are not a universal public interface. Typical static outputs use `data/raw/<source>/extract_date=…/`; cloud output adds `gs://<bucket>/raw/`. Realtime uses snapshot timestamps rather than extract dates.

Choose when an existing output is safe to skip and when a correction needs a new extract/version. Validate before publishing the data/manifest so downstream consumers do not interpret an empty/error response as a successful extract. Preserve unknown values rather than inventing observations.

## Registry and staging

The registry uses dataclasses, not dictionaries and not automatic schema inference. Match existing `JobSpec`, `Column`/`_cols`, `Partitioning`, and `Clustering` usage. CSV column order and null representation must agree with the writer and load job; adding a field can require loader changes even when nullable.

A staging source reference is:

```sql
select * from {{ source('raw', 'raw_your_source') }}
```

Use `_extract_date` and `_ingested_at` metadata only according to the selected source's semantics. A latest-extract dimension, append-only event stream, and revised daily observation require different deduplication rules. Add tests for the intended grain and incremental selection if relevant.

## Validation and rollout

Run focused offline tests, `make test`, and relevant lint. Parse dbt with explicit dummy profile settings if checking without cloud access. Local ingestion still contacts source APIs; `bq-load-local` writes BigQuery, and a full workflow dispatch writes multiple cloud layers. Keep deployment/execution within the authorized task.

After authorized production loading, verify source counts/quality, schema, staging grain, downstream tests, exported content, and served results. Exposing a new mart also requires [the mart guide](ADDING_A_MART.md); a staging model alone is not API-queryable.
