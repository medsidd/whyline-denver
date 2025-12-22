"""Shared ingestion helpers for WhyLine Denver ingestors."""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import time
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, Union
import pandas as pd
import requests

try:
    from google.cloud import storage  # type: ignore
except ImportError:  # pragma: no cover - optional dependency at runtime
    storage = None  # type: ignore[assignment]

if TYPE_CHECKING:  # pragma: no cover
    from google.cloud.storage import Client
else:  # pragma: no cover
    Client = Any

PathLike = Union[str, Path]
_GCS_CLIENT: Client | None = None

_LOG_LEVEL_NAME = os.getenv("WLD_LOG_LEVEL", "INFO").upper()
_LOG_LEVEL = getattr(logging, _LOG_LEVEL_NAME, logging.INFO)
logging.basicConfig(
    level=_LOG_LEVEL,
    format="%(asctime)s %(name)s [%(levelname)s] %(message)s",
)


def get_logger(name: str) -> logging.Logger:
    """Return a module-level logger configured with the shared ingestion format."""
    logger = logging.getLogger(name)
    logger.setLevel(_LOG_LEVEL)
    return logger


def http_get_with_retry(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
    retries: int = 3,
    backoff_factor: float = 1.5,
    logger: logging.Logger | None = None,
) -> requests.Response:
    """Perform an HTTP GET with exponential backoff for transient errors."""

    logger = logger or logging.getLogger(__name__)
    attempt = 0
    delay = backoff_factor
    while True:
        try:
            response = requests.get(url, params=params, headers=headers, timeout=timeout)
            if response.status_code >= 500:
                response.raise_for_status()
            return response
        except requests.HTTPError as exc:  # includes status >= 500
            attempt += 1
            if attempt > retries:
                raise
            logger.warning(
                "HTTP error (%s) for %s; retrying in %.1fs (attempt %d/%d)",
                exc,
                url,
                delay,
                attempt,
                retries,
            )
            time.sleep(delay)
            delay *= backoff_factor
        except requests.RequestException as exc:
            attempt += 1
            if attempt > retries:
                raise
            logger.warning(
                "Request error (%s) for %s; retrying in %.1fs (attempt %d/%d)",
                exc,
                url,
                delay,
                attempt,
                retries,
            )
            time.sleep(delay)
            delay *= backoff_factor


def write_csv(df: pd.DataFrame, path: PathLike, *, compression: str = "gzip") -> None:
    """
    Serialize a DataFrame to UTF-8 CSV, writing gzip output by default.

    If a GCS URI (gs://bucket/path.csv.gz) is provided, the blob is uploaded directly.
    Otherwise, the file is written locally, creating parent directories when needed.
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError("write_csv expects a pandas.DataFrame")

    csv_bytes = df.to_csv(index=False).encode("utf-8")
    if compression not in (None, "gzip"):
        raise ValueError("compression must be 'gzip' or None")

    if compression == "gzip":
        buffer = BytesIO()
        with gzip.GzipFile(fileobj=buffer, mode="wb") as gz:
            gz.write(csv_bytes)
        payload = buffer.getvalue()
        content_type = "application/gzip"
    else:
        payload = csv_bytes
        content_type = "text/csv"

    target = str(path)
    if _is_gcs_path(target):
        bucket_name, blob_path = _split_gcs_uri(target)
        upload_bytes_gcs(bucket_name, blob_path, payload, content_type)
    else:
        path_obj = Path(target)
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        with path_obj.open("wb") as f:
            f.write(payload)


def write_manifest(path: PathLike, meta: dict[str, Any]) -> None:
    """Write a manifest.json adjacent to the provided file or directory."""
    manifest_payload = json.dumps(meta, indent=2, sort_keys=True).encode("utf-8")
    target = str(path)

    if _is_gcs_path(target):
        bucket_name, blob_path = _split_gcs_uri(target)
        prefix = (
            blob_path
            if blob_path.endswith("/")
            else f"{blob_path.rsplit('/', 1)[0]}/" if "/" in blob_path else ""
        )
        manifest_blob = f"{prefix}manifest.json"
        upload_bytes_gcs(bucket_name, manifest_blob, manifest_payload, "application/json")
    else:
        path_obj = Path(target)
        if path_obj.suffix:
            manifest_path = path_obj.parent / "manifest.json"
        else:
            manifest_path = path_obj / "manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_bytes(manifest_payload)


def upload_bytes_gcs(bucket: str, path: str, data: bytes, content_type: str) -> None:
    """Upload bytes to Google Cloud Storage under the provided bucket/path."""
    if bucket.startswith("gs://"):
        bucket, path = _split_gcs_uri(bucket)
    client = _get_gcs_client()
    blob = client.bucket(bucket).blob(path)
    blob.upload_from_string(data, content_type=content_type)


def exists(path: PathLike) -> bool:
    """Return True when the local path or GCS blob exists."""
    target = str(path)
    if _is_gcs_path(target):
        bucket_name, blob_path = _split_gcs_uri(target)
        client = _get_gcs_client()
        blob = client.bucket(bucket_name).blob(blob_path)
        return blob.exists(client=client)
    return Path(target).exists()


def hash_bytes_md5(data: bytes) -> str:
    """Return hex digest of the provided bytes using MD5."""
    return hashlib.md5(data, usedforsecurity=False).hexdigest()  # noqa: S324


def sizeof_bytes(data: bytes) -> int:
    """Return byte length of the provided payload."""
    return len(data)


def utc_now_iso() -> str:
    """Return current UTC time as ISO-8601 string with Z suffix."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _is_gcs_path(path: str) -> bool:
    return path.startswith("gs://")


def _split_gcs_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("gs://"):
        raise ValueError(f"Not a GCS URI: {uri}")
    parts = uri[5:].split("/", 1)
    if len(parts) == 1:
        raise ValueError(f"GCS URI missing object path: {uri}")
    bucket, blob_path = parts
    return bucket, blob_path


def _get_gcs_client() -> Client:
    global _GCS_CLIENT
    if storage is None:
        raise ImportError(
            "google-cloud-storage is required for GCS operations but is not installed."
        )
    if _GCS_CLIENT is None:
        _GCS_CLIENT = storage.Client()
    return _GCS_CLIENT
