"""Helpers for persisting and retrieving sync_state.json locally and from GCS."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Mapping, Optional

LOGGER = logging.getLogger(__name__)

# Default local location of sync_state.json; callers can override via arguments.
DEFAULT_SYNC_STATE_PATH = Path("data/sync_state.json")
SYNC_STATE_GCS_REQUIRED_ENV = "SYNC_STATE_GCS_REQUIRED"


class SyncStateUploadError(RuntimeError):
    """Raised when sync state cannot be uploaded to the configured GCS bucket."""


def _gcs_target() -> Optional[tuple[str, str]]:
    """Return the (bucket, blob) configured for sync_state uploads/downloads."""
    bucket = os.getenv("SYNC_STATE_GCS_BUCKET")
    if not bucket:
        return None
    blob = os.getenv("SYNC_STATE_GCS_BLOB", "state/sync_state.json")
    return bucket, blob


def _ensure_storage_client():
    try:
        from google.cloud import storage
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency guard
        raise SyncStateUploadError(
            "google-cloud-storage is required to access sync_state.json in GCS."
        ) from exc
    try:
        return storage.Client()
    except Exception as exc:  # pragma: no cover - credential/network errors
        raise SyncStateUploadError("Unable to initialize Google Cloud Storage client") from exc


def _require_gcs_upload() -> bool:
    return os.getenv(SYNC_STATE_GCS_REQUIRED_ENV, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def download_sync_state(
    *,
    path: Path = DEFAULT_SYNC_STATE_PATH,
) -> bool:
    """Ensure a local copy of sync_state.json exists by downloading from GCS if available."""
    target = _gcs_target()
    if not target:
        LOGGER.debug("No GCS target configured; skipping sync_state download.")
        return False

    bucket_name, blob_name = target
    try:
        client = _ensure_storage_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        if not blob.exists():
            LOGGER.info("sync_state.json not found in gs://%s/%s", bucket_name, blob_name)
            return False
        contents = blob.download_as_bytes()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
        LOGGER.debug(
            "Downloaded sync_state.json from gs://%s/%s to %s", bucket_name, blob_name, path
        )
        return True
    except Exception as exc:  # pragma: no cover - network/credential errors
        LOGGER.warning(
            "Failed to download sync_state.json from gs://%s/%s: %s", bucket_name, blob_name, exc
        )
        return False


def write_sync_state(
    payload: Mapping[str, Any],
    *,
    path: Path = DEFAULT_SYNC_STATE_PATH,
) -> None:
    """Write sync_state locally and optionally mirror it to GCS."""
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialized, encoding="utf-8")
    LOGGER.debug("Wrote sync state to %s", path)

    target = _gcs_target()
    if not target:
        LOGGER.debug("No GCS target configured; skipping sync_state upload.")
        return

    bucket_name, blob_name = target
    try:
        client = _ensure_storage_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_string(serialized, content_type="application/json")
        LOGGER.info("Uploaded sync state to gs://%s/%s", bucket_name, blob_name)
    except Exception as exc:  # pragma: no cover - network/credential errors
        message = f"Failed to upload sync_state.json to gs://{bucket_name}/{blob_name}: {exc}"
        if _require_gcs_upload():
            raise SyncStateUploadError(message) from exc
        LOGGER.warning("%s (continuing without remote mirror)", message)


def load_sync_state(
    *,
    path: Path = DEFAULT_SYNC_STATE_PATH,
    prefer_gcs: bool = True,
) -> Optional[dict[str, Any]]:
    """Load sync_state, preferring GCS when configured."""
    target = _gcs_target() if prefer_gcs else None
    if target:
        bucket_name, blob_name = target
        try:
            client = _ensure_storage_client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            contents = blob.download_as_text(encoding="utf-8")
            LOGGER.debug("Loaded sync state from gs://%s/%s", bucket_name, blob_name)
            return json.loads(contents)
        except Exception as exc:  # pragma: no cover - network/credential errors
            LOGGER.warning(
                "Unable to load sync state from gs://%s/%s (%s); falling back to local file.",
                bucket_name,
                blob_name,
                exc,
            )

    if not path.exists():
        LOGGER.debug("Local sync_state.json not found at %s", path)
        return None

    try:
        contents = path.read_text(encoding="utf-8")
        LOGGER.debug("Loaded sync state from %s", path)
        return json.loads(contents)
    except json.JSONDecodeError as exc:
        LOGGER.warning("Local sync_state.json is malformed (%s): %s", path, exc)
        return None
