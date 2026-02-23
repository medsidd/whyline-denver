from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Optional

from google.api_core.exceptions import NotFound
from google.cloud import bigquery, storage

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class ExportState:
    """Represents export progress for a mart."""

    mart_name: str
    last_service_date: Optional[date] = None
    last_run_ts: Optional[datetime] = None

    def to_json(self) -> str:
        return json.dumps(
            {
                "mart_name": self.mart_name,
                "last_service_date": (
                    self.last_service_date.isoformat() if self.last_service_date else None
                ),
                "last_run_ts": self._format_timestamp(self.last_run_ts),
            },
            separators=(",", ":"),
        )

    @classmethod
    def from_json(cls, payload: str) -> ExportState:
        raw = json.loads(payload)
        last_service_date = cls._parse_date(raw.get("last_service_date"))
        last_run_ts = cls._parse_timestamp(raw.get("last_run_ts"))
        return cls(
            mart_name=raw["mart_name"],
            last_service_date=last_service_date,
            last_run_ts=last_run_ts,
        )

    @staticmethod
    def _parse_date(value: Optional[str]) -> Optional[date]:
        if not value:
            return None
        return date.fromisoformat(value)

    @staticmethod
    def _parse_timestamp(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    @staticmethod
    def _format_timestamp(value: Optional[datetime]) -> Optional[str]:
        if not value:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class BQStateStore:
    """Persist export state in BigQuery."""

    _TABLE_NAME = "__export_state"

    def __init__(self, client: bigquery.Client, dataset_id: str) -> None:
        self._client = client
        self._dataset_id = dataset_id
        self._project = client.project
        self._table_ref = f"{self._project}.{self._dataset_id}.{self._TABLE_NAME}"

    def ensure_table(self) -> None:
        """Ensure the control table exists."""
        try:
            self._client.get_table(self._table_ref)
        except NotFound:
            LOGGER.info("Creating export state table %s", self._table_ref)
            schema = [
                bigquery.SchemaField("mart_name", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("last_service_date", "DATE", mode="NULLABLE"),
                bigquery.SchemaField("last_run_ts", "TIMESTAMP", mode="NULLABLE"),
            ]
            table = bigquery.Table(self._table_ref, schema=schema)
            table.clustering_fields = ["mart_name"]
            self._client.create_table(table)

    def load(self, mart_name: str) -> Optional[ExportState]:
        self.ensure_table()
        query = (
            f"SELECT mart_name, last_service_date, last_run_ts "
            f"FROM `{self._table_ref}` "
            f"WHERE mart_name = @mart_name "
            f"ORDER BY last_run_ts DESC "
            f"LIMIT 1"
        )
        job = self._client.query(
            query,
            job_config=bigquery.QueryJobConfig(
                query_parameters=[bigquery.ScalarQueryParameter("mart_name", "STRING", mart_name)],
            ),
        )
        rows = list(job)
        if not rows:
            return None
        row = rows[0]
        return ExportState(
            mart_name=row["mart_name"],
            last_service_date=row.get("last_service_date"),
            last_run_ts=row.get("last_run_ts"),
        )

    def write(self, state: ExportState) -> None:
        self.ensure_table()
        query = (
            f"MERGE `{self._table_ref}` AS target "
            "USING (SELECT @mart_name AS mart_name, "
            "@last_service_date AS last_service_date, "
            "@last_run_ts AS last_run_ts) AS source "
            "ON target.mart_name = source.mart_name "
            "WHEN MATCHED THEN UPDATE SET "
            "  last_service_date = source.last_service_date, "
            "  last_run_ts = source.last_run_ts "
            "WHEN NOT MATCHED THEN "
            "  INSERT (mart_name, last_service_date, last_run_ts) "
            "  VALUES (source.mart_name, source.last_service_date, source.last_run_ts)"
        )
        self._client.query(
            query,
            job_config=bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("mart_name", "STRING", state.mart_name),
                    bigquery.ScalarQueryParameter(
                        "last_service_date", "DATE", state.last_service_date
                    ),
                    bigquery.ScalarQueryParameter("last_run_ts", "TIMESTAMP", state.last_run_ts),
                ],
            ),
        ).result()


class GCSStateStore:
    """Persist export state marker in GCS."""

    def __init__(self, client: storage.Client, bucket: str) -> None:
        self._client = client
        self._bucket_name = bucket

    def _blob_path(self, mart_name: str) -> str:
        return f"marts/{mart_name}/last_export.json"

    def load(self, mart_name: str) -> Optional[ExportState]:
        bucket = self._client.bucket(self._bucket_name)
        blob = bucket.blob(self._blob_path(mart_name))
        try:
            payload = blob.download_as_text()
        except NotFound:
            return None
        try:
            state = ExportState.from_json(payload)
        except (ValueError, KeyError) as exc:
            LOGGER.warning(
                "Ignoring malformed state marker for %s: %s", mart_name, exc, exc_info=exc
            )
            return None
        return state

    def write(self, state: ExportState) -> None:
        bucket = self._client.bucket(self._bucket_name)
        blob = bucket.blob(self._blob_path(state.mart_name))
        blob.upload_from_string(state.to_json(), content_type="application/json")


class CompositeStateStore:
    """Reads from both BQ and GCS and writes to both."""

    def __init__(self, bq_store: BQStateStore, gcs_store: GCSStateStore) -> None:
        self._bq_store = bq_store
        self._gcs_store = gcs_store

    def load(self, mart_name: str) -> Optional[ExportState]:
        bq_state = self._safe_load(self._bq_store, mart_name)
        gcs_state = self._safe_load(self._gcs_store, mart_name)
        return self._select_freshest(bq_state, gcs_state)

    def write(self, state: ExportState) -> None:
        self._bq_store.write(state)
        self._gcs_store.write(state)

    def _safe_load(self, store, mart_name: str) -> Optional[ExportState]:
        try:
            return store.load(mart_name)
        except NotFound:
            LOGGER.debug("State backend missing for %s; treating as empty", mart_name)
            return None

    @staticmethod
    def _select_freshest(
        *states: Optional[ExportState],
    ) -> Optional[ExportState]:
        freshest: Optional[ExportState] = None
        for state in states:
            if not state:
                continue
            if not freshest or CompositeStateStore._is_newer(state, freshest):
                freshest = state
        return freshest

    @staticmethod
    def _is_newer(candidate: ExportState, reference: ExportState) -> bool:
        """Return True if candidate is more recent than reference."""
        cand_ts = candidate.last_run_ts or datetime.min.replace(tzinfo=UTC)
        ref_ts = reference.last_run_ts or datetime.min.replace(tzinfo=UTC)
        return cand_ts > ref_ts
