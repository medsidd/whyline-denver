from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Dict, Iterable, Optional
from unittest.mock import MagicMock

from whyline.config import Settings
from whyline.sync.export_bq_marts import ALLOWLISTED_MARTS, MartExporter
from whyline.sync.state import ExportState


class FakeStateStore:
    def __init__(self, initial: Optional[Dict[str, ExportState]] = None) -> None:
        self.states: Dict[str, ExportState] = initial or {}
        self.written: list[ExportState] = []

    def load(self, mart_name: str) -> Optional[ExportState]:
        return self.states.get(mart_name)

    def write(self, state: ExportState) -> None:
        self.states[state.mart_name] = state
        self.written.append(state)


class FakeQueryJob:
    def __init__(self, rows: Iterable[tuple] = ()) -> None:
        self._rows = list(rows)

    def __iter__(self):
        return iter(self._rows)

    def result(self):
        return self


def test_partitioned_mart_exports_new_partitions(monkeypatch):
    settings = Settings()
    mart_name = "mart_reliability_by_route_day"
    initial_state = ExportState(
        mart_name=mart_name,
        last_service_date=date(2025, 1, 2),
        last_run_ts=datetime(2025, 1, 2, 12, 0, tzinfo=UTC),
    )
    state_store = FakeStateStore({mart_name: initial_state})

    partition_rows = [
        (date(2025, 1, 3),),
        (date(2025, 1, 4),),
    ]
    partition_job = FakeQueryJob(partition_rows)
    export_job = FakeQueryJob()

    bq_client = MagicMock()
    bq_client.query.side_effect = [partition_job, export_job, export_job]

    exporter = MartExporter(
        settings,
        bq_client=bq_client,
        storage_client=MagicMock(),
        state_store=state_store,
        allowlisted_marts=ALLOWLISTED_MARTS,
    )

    timestamps = [
        datetime(2025, 1, 10, 0, 0, tzinfo=UTC),
        datetime(2025, 1, 10, 0, 5, tzinfo=UTC),
        datetime(2025, 1, 10, 0, 10, tzinfo=UTC),
    ]
    exporter._now = MagicMock(side_effect=timestamps)  # type: ignore[assignment]

    results = exporter.run(since=date(2025, 1, 1), marts=[mart_name])

    assert len(results) == 1
    result = results[0]
    assert result.mart_name == mart_name
    assert result.exported_partitions == (date(2025, 1, 3), date(2025, 1, 4))
    assert state_store.states[mart_name].last_service_date == date(2025, 1, 4)
    assert state_store.states[mart_name].last_run_ts == timestamps[-1]
    assert bq_client.query.call_count == 3


def test_snapshot_mart_skips_if_already_exported_today():
    settings = Settings()
    mart_name = "mart_access_score_by_stop"
    frozen_now = datetime(2025, 1, 20, 9, 30, tzinfo=UTC)
    state_store = FakeStateStore(
        {
            mart_name: ExportState(
                mart_name=mart_name,
                last_service_date=date(2025, 1, 19),
                last_run_ts=frozen_now,
            )
        }
    )

    exporter = MartExporter(
        settings,
        bq_client=MagicMock(),
        storage_client=MagicMock(),
        state_store=state_store,
        allowlisted_marts=ALLOWLISTED_MARTS,
    )
    exporter._now = MagicMock(return_value=frozen_now)  # type: ignore[assignment]

    results = exporter.run(marts=[mart_name])

    assert results == []
    exporter._bq_client.query.assert_not_called()
    assert len(state_store.written) == 0
