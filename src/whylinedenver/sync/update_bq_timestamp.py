"""Update BigQuery timestamp in sync_state.json after dbt runs."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from whylinedenver.sync.state_store import SyncStateUploadError, load_sync_state, write_sync_state

LOGGER = logging.getLogger(__name__)

SYNC_STATE_PATH = Path("data/sync_state.json")
DBT_RUN_RESULTS_PATH = Path("dbt/target/run_results.json")


def _load_and_merge_state(path: Path) -> tuple[dict, bool]:
    default: dict[str, object] = {}

    remote_state = load_sync_state(path=path, prefer_gcs=True)
    if remote_state:
        LOGGER.info("Downloaded existing sync_state.json from GCS")
        serialized = json.dumps(remote_state, indent=2, sort_keys=True) + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(serialized, encoding="utf-8")
        default = dict(remote_state)
    elif path.exists():
        LOGGER.warning("Using local sync_state.json only; remote download was unavailable")
    else:
        LOGGER.error(
            "Unable to download sync_state.json from GCS and no local copy exists; refusing to overwrite state"
        )
        return {}, False

    state = load_sync_state(path=path, prefer_gcs=False)
    if state is None:
        LOGGER.error("sync_state.json not found locally after download attempt")
        return {}, False

    if default:
        state.setdefault("duckdb_synced_at_utc", default.get("duckdb_synced_at_utc"))
        if not isinstance(state.get("marts"), dict) or not state["marts"]:
            state["marts"] = default.get("marts", {})

    return state, True


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

    # Ensure we have the latest sync_state locally before merging.
    sync_state, ok = _load_and_merge_state(SYNC_STATE_PATH)
    if not ok:
        return 1

    # Update BigQuery timestamp while preserving other fields
    sync_state["bigquery_updated_at_utc"] = generated_at

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
