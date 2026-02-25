from __future__ import annotations

import argparse
import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Optional

from google.cloud import bigquery, storage

from whyline.config import Settings
from whyline.sync.constants import ALLOWLISTED_MARTS
from whyline.sync.state import (
    BQStateStore,
    CompositeStateStore,
    ExportState,
    GCSStateStore,
)

LOGGER = logging.getLogger(__name__)

PARTITIONED_MARTS: frozenset[str] = frozenset(
    {"mart_reliability_by_route_day", "mart_reliability_by_stop_hour"}
)


@dataclass(slots=True, frozen=True)
class ExportResult:
    mart_name: str
    exported_partitions: tuple[date, ...]
    destination_uri_template: str
    last_run_ts: datetime


class MartExporter:
    """Coordinates BigQuery -> Parquet exports and progress tracking."""

    def __init__(
        self,
        settings: Settings,
        *,
        bq_client: Optional[bigquery.Client] = None,
        storage_client: Optional[storage.Client] = None,
        allowlisted_marts: Sequence[str] = ALLOWLISTED_MARTS,
        state_store: Optional[CompositeStateStore] = None,
    ) -> None:
        self.settings = settings
        self.project = settings.GCP_PROJECT_ID
        self.dataset = settings.BQ_DATASET_MART
        self.bucket = settings.GCS_BUCKET
        self.allowlisted_marts = tuple(allowlisted_marts)

        self._bq_client = bq_client or bigquery.Client(project=self.project)
        self._storage_client = storage_client or storage.Client(project=self.project)
        self._state_store = state_store or CompositeStateStore(
            BQStateStore(self._bq_client, self.dataset),
            GCSStateStore(self._storage_client, self.bucket),
        )

    def run(
        self, *, since: Optional[date] = None, marts: Optional[Iterable[str]] = None
    ) -> list[ExportResult]:
        marts_to_process = tuple(self._validate_marts(marts))
        LOGGER.info(
            "Starting mart export for %s (since=%s)",
            ", ".join(marts_to_process),
            since.isoformat() if since else "all available partitions",
        )
        results: list[ExportResult] = []
        for mart_name in marts_to_process:
            if mart_name in PARTITIONED_MARTS:
                result = self._export_partitioned_mart(mart_name, since)
            else:
                result = self._export_snapshot_mart(mart_name)
            if result:
                results.append(result)
        return results

    def _validate_marts(self, marts: Optional[Iterable[str]]) -> Iterable[str]:
        if marts is None:
            return self.allowlisted_marts
        invalid = sorted(set(marts) - set(self.allowlisted_marts))
        if invalid:
            raise ValueError(f"Unsupported mart(s): {', '.join(invalid)}")
        # Preserve the caller's order while de-duplicating.
        seen: set[str] = set()
        ordered = []
        for mart in marts:
            if mart in seen:
                continue
            seen.add(mart)
            ordered.append(mart)
        return ordered

    def _export_partitioned_mart(
        self, mart_name: str, since: Optional[date]
    ) -> Optional[ExportResult]:
        state = self._state_store.load(mart_name)
        LOGGER.info("Loaded state for %s: %s", mart_name, state)
        partitions = self._list_partitions_to_export(mart_name, state, since)
        if not partitions:
            LOGGER.info("No new partitions found for %s; skipping", mart_name)
            return None

        destination_template = f"gs://{self.bucket}/marts/{mart_name}/run_date={{date}}/*"
        last_exported: Optional[date] = None
        for partition_date in partitions:
            destination_uri = destination_template.format(date=partition_date.isoformat())
            sql = self._build_partition_export_sql(mart_name, partition_date, destination_uri)
            LOGGER.info(
                "Exporting %s partition %s to %s", mart_name, partition_date, destination_uri
            )
            self._execute_export(sql)
            last_exported = partition_date
            self._persist_state(mart_name, last_exported)

        final_state = self._persist_state(mart_name, last_exported, finalize=True)
        return ExportResult(
            mart_name=mart_name,
            exported_partitions=tuple(partitions),
            destination_uri_template=destination_template,
            last_run_ts=final_state.last_run_ts or self._now(),
        )

    def _export_snapshot_mart(self, mart_name: str) -> Optional[ExportResult]:
        today = self._now().date()
        state = self._state_store.load(mart_name)
        if state and state.last_run_ts and state.last_run_ts.date() >= today:
            LOGGER.info("Snapshot mart %s already exported today; skipping", mart_name)
            return None

        destination_uri = f"gs://{self.bucket}/marts/{mart_name}/run_date={today.isoformat()}/*"
        sql = self._build_snapshot_export_sql(mart_name, destination_uri)
        LOGGER.info("Exporting snapshot mart %s to %s", mart_name, destination_uri)
        self._execute_export(sql)
        final_state = self._persist_state(mart_name, today, finalize=True)
        return ExportResult(
            mart_name=mart_name,
            exported_partitions=(today,),
            destination_uri_template=f"gs://{self.bucket}/marts/{mart_name}/run_date={{date}}/*",
            last_run_ts=final_state.last_run_ts or self._now(),
        )

    def _persist_state(
        self,
        mart_name: str,
        last_service_date: Optional[date],
        *,
        finalize: bool = False,
    ) -> ExportState:
        # Use a fresh timestamp per persistence to reflect progress.
        timestamp = self._now()
        state = ExportState(
            mart_name=mart_name,
            last_service_date=last_service_date,
            last_run_ts=timestamp,
        )
        self._state_store.write(state)
        if finalize:
            LOGGER.info(
                "Updated state for %s: last_service_date=%s last_run_ts=%s",
                mart_name,
                last_service_date.isoformat() if last_service_date else "N/A",
                timestamp.isoformat(),
            )
        return state

    def _list_partitions_to_export(
        self,
        mart_name: str,
        state: Optional[ExportState],
        since: Optional[date],
    ) -> list[date]:
        cutoff = self._determine_cutoff(state, since)
        LOGGER.info(
            "Scanning partitions for %s with cutoff %s",
            mart_name,
            cutoff.isoformat() if cutoff else "start",
        )
        params = []
        predicate = ""
        if cutoff:
            predicate = "WHERE service_date_mst >= @cutoff"
            params.append(bigquery.ScalarQueryParameter("cutoff", "DATE", cutoff))
        query = f"""
            SELECT DISTINCT service_date_mst
            FROM `{self.project}.{self.dataset}.{mart_name}`
            WHERE service_date_mst IS NOT NULL
        """
        if predicate:
            query = f"""
                SELECT DISTINCT service_date_mst
                FROM `{self.project}.{self.dataset}.{mart_name}`
                WHERE service_date_mst IS NOT NULL
                  AND service_date_mst >= @cutoff
            """
        job = self._bq_client.query(
            query,
            job_config=bigquery.QueryJobConfig(query_parameters=params),
        )
        partitions = sorted(row[0] for row in job)
        LOGGER.info("Found %d partitions for %s", len(partitions), mart_name)
        return partitions

    @staticmethod
    def _determine_cutoff(state: Optional[ExportState], since: Optional[date]) -> Optional[date]:
        candidate: Optional[date] = since
        if state and state.last_service_date:
            next_day = state.last_service_date + timedelta(days=1)
            if candidate is None or next_day > candidate:
                candidate = next_day
        return candidate

    def _build_partition_export_sql(
        self, mart_name: str, run_date: date, destination_uri: str
    ) -> str:
        table_ref = f"`{self.project}.{self.dataset}.{mart_name}`"
        return f"""
            EXPORT DATA OPTIONS(
              uri='{destination_uri}',
              format='PARQUET',
              overwrite=true
            ) AS
            SELECT * FROM {table_ref}
            WHERE service_date_mst = DATE('{run_date.isoformat()}')
        """

    def _build_snapshot_export_sql(self, mart_name: str, destination_uri: str) -> str:
        table_ref = f"`{self.project}.{self.dataset}.{mart_name}`"
        return f"""
            EXPORT DATA OPTIONS(
              uri='{destination_uri}',
              format='PARQUET',
              overwrite=true
            ) AS
            SELECT * FROM {table_ref}
        """

    def _execute_export(self, sql: str) -> None:
        LOGGER.debug("Executing export SQL:\n%s", sql)
        job = self._bq_client.query(sql)
        job.result()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export BigQuery marts to Parquet in GCS.")
    parser.add_argument(
        "--since",
        type=_parse_date,
        help="Export partitions on or after this date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--mart",
        action="append",
        dest="marts",
        help="Limit export to specific mart(s). Can be specified multiple times.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices={"DEBUG", "INFO", "WARNING", "ERROR"},
        help="Logging level (default: INFO).",
    )
    return parser.parse_args(argv)


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:  # pragma: no cover - argument parsing guard
        raise argparse.ArgumentTypeError(f"Invalid date '{value}': {exc}") from exc


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = Settings()
    exporter = MartExporter(settings)
    try:
        exporter.run(since=args.since, marts=args.marts)
    except Exception:  # pragma: no cover - CLI top-level guard
        LOGGER.exception("Export failed")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
