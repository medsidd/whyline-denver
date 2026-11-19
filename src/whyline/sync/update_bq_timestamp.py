"""Update BigQuery timestamp in sync_state.json after dbt runs."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from whyline.sync.state_store import SyncStateUploadError, write_sync_state

LOGGER = logging.getLogger(__name__)

SYNC_STATE_PATH = Path("data/sync_state.json")
DBT_RUN_RESULTS_PATH = Path("dbt/target/run_results.json")


def update_bigquery_timestamp() -> int:
    """Update BigQuery timestamp from dbt run_results.json."""
    # Read dbt run results to get the latest timestamp
    if not DBT_RUN_RESULTS_PATH.exists():
        LOGGER.warning("dbt run_results.json not found at %s", DBT_RUN_RESULTS_PATH)
        return 1

    try:
        with DBT_RUN_RESULTS_PATH.open("r", encoding="utf-8") as fh:
            run_results = json.load(fh)
    except json.JSONDecodeError as exc:
        LOGGER.error("Failed to parse dbt run_results.json: %s", exc)
        return 1

    # Extract timestamp from metadata
    metadata = run_results.get("metadata", {})
    generated_at = metadata.get("generated_at")

    if not generated_at:
        # Fallback: use current timestamp
        LOGGER.warning("No generated_at in dbt run_results, using current time")
        generated_at = datetime.now(UTC).isoformat()

    # Only the BigQuery time is kept: the DuckDB fields went with the DuckDB copy (Nov 2026)
    sync_state = {"bigquery_updated_at_utc": generated_at}

    # Write updated state locally and mirror to GCS if configured
    try:
        write_sync_state(sync_state, path=SYNC_STATE_PATH)
    except SyncStateUploadError as exc:
        LOGGER.error("%s", exc)
        return 1

    LOGGER.info("Updated BigQuery timestamp to %s", generated_at)
    return 0


def main() -> int:
    """CLI entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    try:
        return update_bigquery_timestamp()
    except Exception:  # pragma: no cover
        LOGGER.exception("Failed to update BigQuery timestamp")
        return 1


if __name__ == "__main__":
    sys.exit(main())
