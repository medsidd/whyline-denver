# Adding a New Data Source

This guide walks through adding an 8th data source to WhyLine Denver. The process follows the same pattern as all existing ingestors.

---

## Overview

Each data source requires four components:
1. An ingestor in `src/whyline/ingest/`
2. A BigQuery raw table (created by the loader)
3. One or more dbt staging models
4. Registration in the Makefile and nightly workflow

---

## Step 1: Write the Ingestor

Create `src/whyline/ingest/your_source.py`. Follow the existing pattern from any existing ingestor (e.g., `denver_crashes.py`).

### Required structure

```python
"""CLI to ingest <description>."""

from whyline.ingest import io

DEFAULT_SOURCE_URL = "https://..."
OUTPUT_FILENAME = "your_data.csv.gz"
COLUMNS = ["col1", "col2", ...]
LOGGER = io.get_logger(__name__)


def run(args: argparse.Namespace) -> int:
    # 1. Determine output root (local or GCS)
    # 2. Check if output already exists → skip if so (idempotency)
    # 3. Fetch data
    # 4. Normalize to DataFrame
    # 5. Gzip-compress and write
    # 6. Write manifest
    return 0


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run(args)


def build_parser() -> argparse.ArgumentParser:
    # Always include: --local/--gcs, --bucket, --extract-date
    ...


if __name__ == "__main__":
    raise SystemExit(main())
```

### Key rules

**Idempotency**: Check if the output file already exists before fetching. Use `io.exists(output_path)` and return 0 early if so.

**Output path**: Always use `extract_date={YYYY-MM-DD}` as the partition directory:
```
data/raw/your_source/extract_date=2025-03-01/your_data.csv.gz
```

**Manifest**: Write a `manifest.json` alongside every output file. Use `io.write_manifest()`. Include at minimum: `source`, `extract_date`, `written_at_utc`, `row_count`, `bytes`, `hash_md5`, `schema_version`.

**GCS/local abstraction**: Use `io.upload_bytes_gcs()` for GCS writes and `Path.write_bytes()` for local writes. Check with `_is_gcs_path()` to distinguish.

**Shared utilities**: Use these from `whyline.ingest.io`:
- `io.http_get_with_retry(url, ...)` — HTTP with exponential backoff
- `io.hash_bytes_md5(data)` — MD5 hex digest
- `io.sizeof_bytes(data)` — byte count
- `io.utc_now_iso()` — current UTC timestamp as ISO string
- `io.get_logger(__name__)` — structured logger

---

## Step 2: Register in Makefile

Add a make target in the `Makefile`:

```makefile
ingest-your-source:
    $(PY) -m whyline.ingest.your_source \
        --gcs --bucket $(GCS_BUCKET) \
        --extract-date $(EXTRACT_DATE)
```

Add it to the `ingest-all` dependency list:

```makefile
ingest-all: ingest-gtfs-static ingest-gtfs-rt ingest-crashes ... ingest-your-source
```

And to `ingest-static` if it's a static (non-realtime) source:

```makefile
ingest-static: ingest-gtfs-static ingest-crashes ... ingest-your-source
```

---

## Step 3: Define the BigQuery raw table

The BigQuery loader (`bq_load.py`) creates tables automatically from the CSV schema. Add the new source to `src/whyline/load/registry.py`:

```python
{
    "name": "raw_your_source",
    "source_glob": "your_source/extract_date=*/your_data.csv.gz",
    "partition_column": "extract_date",
    "schema": [
        bigquery.SchemaField("col1", "STRING"),
        bigquery.SchemaField("col2", "INTEGER"),
        # ... match COLUMNS from ingestor
    ],
}
```

Run `make bq-load-local` after ingesting locally to verify the table loads correctly.

---

## Step 4: Write the dbt staging model

Create `dbt/models/staging/stg_your_source.sql`:

```sql
-- dbt staging model for <description>
with source as (
    select * from {{ source('raw_denver', 'raw_your_source') }}
    where extract_date = (
        select max(extract_date) from {{ source('raw_denver', 'raw_your_source') }}
    )
),

renamed as (
    select
        col1 as output_col1,
        col2 as output_col2,
        extract_date
    from source
)

select * from renamed
```

Add it to `dbt/models/staging/schema.yml`:

```yaml
models:
  - name: stg_your_source
    description: "Clean staging view of <description>."
    columns:
      - name: output_col1
        description: "..."
        tests:
          - not_null
```

---

## Step 5: Add to the nightly workflow

In `.github/workflows/nightly-ingest.yml`, add the new make target to the workflow step:

```yaml
- name: Ingest all sources
  run: make nightly-ingest-bq  # This already calls ingest-all if you updated it
```

If the new source needs additional credentials (API key etc.), add them as GitHub Actions secrets and expose them as environment variables in the workflow.

---

## Step 6: Write tests

Add `tests/ingest/test_your_source.py` following the pattern in existing test files:

```python
from whyline.ingest.your_source import normalize_records, build_manifest

def test_normalize_basic():
    raw = [{"col1": "value", "col2": 42}]
    records, stats = normalize_records(raw)
    assert len(records) == 1
    assert records[0]["output_col1"] == "value"

def test_normalize_drops_missing_location():
    raw = [{"col1": None, "col2": None}]
    records, stats = normalize_records(raw)
    assert len(records) == 0
```

---

## Step 7: Optionally expose in a mart

If the new data source contributes to analytics, create a mart in the appropriate domain folder (`dbt/models/marts/`). Add `meta: {allow_in_app: true}` to its schema.yml entry to make it queryable from the dashboard.

---

## Checklist

- [ ] `src/whyline/ingest/your_source.py` written and idempotent
- [ ] `make ingest-your-source` target added to Makefile
- [ ] Source added to `ingest-all` (and `ingest-static` if applicable)
- [ ] BigQuery table schema in `registry.py`
- [ ] `dbt/models/staging/stg_your_source.sql` created
- [ ] Model added to `dbt/models/staging/schema.yml` with tests
- [ ] `tests/ingest/test_your_source.py` written
- [ ] Nightly ingest workflow updated if new credentials are needed
