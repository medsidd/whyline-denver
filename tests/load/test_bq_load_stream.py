"""Loader behaviour for the continuous stream tables (no cloud calls)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from whyline.load import bq_load
from whyline.load.registry import JOBS


class FakeClient:
    def __init__(self):
        self.created: list[bigquery.Table] = []

    def get_table(self, table_id):
        raise NotFound(table_id)

    def create_table(self, table):
        self.created.append(table)


def created(table: str) -> bigquery.Table:
    client = FakeClient()
    bq_load.ensure_destination_table(client, next(j for j in JOBS if j.table == table))
    return client.created[0]


def test_stream_tables_expire_after_90_days_and_visits_partition_by_load_hour():
    day = 86_400_000
    tu = created("raw_gtfsrt_tu_changes").time_partitioning
    assert (tu.type_, tu.field, tu.expiration_ms) == ("DAY", "feed_ts_utc", 90 * day)
    visits = created("raw_gtfsrt_stop_visits")
    assert (visits.time_partitioning.type_, visits.time_partitioning.field) == (
        "HOUR",
        "_ingested_at",
    )
    assert visits.time_partitioning.expiration_ms == 90 * day
    assert visits.clustering_fields == ["route_id", "trip_id"]
    old = created("raw_gtfsrt_trip_updates").time_partitioning  # existing tables: unchanged
    assert (old.type_, old.expiration_ms) == ("DAY", None)


def item(label: str) -> bq_load.PlanItem:
    relative = f"rtd_gtfsrt_stream/snapshot_at={label}/stop_visits.csv.gz"
    ref = bq_load.FileRef(f"gs://b/raw/{relative}", relative, None, 1, True)
    return bq_load.PlanItem(job=JOBS[0], file=ref, hash_md5="h", already_loaded=True)


def warnings(plan, cache, now, caplog) -> list[str]:
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="whyline.load.bq_load"):
        bq_load.warn_if_stream_stale(plan, cache, now)
    return [r.getMessage() for r in caplog.records]


def test_stream_staleness_warnings(caplog):
    now = datetime(2026, 11, 2, 14, 17, tzinfo=UTC)
    fresh = [item("2026-11-02T13:45"), item("2026-11-02T14:00")]
    assert warnings(fresh, set(), now, caplog) == []
    stale = [item("2026-11-02T13:30")]  # sealed 13:45, 32 minutes ago
    assert warnings(stale, set(), now, caplog) == [
        "STREAM_STALE newest=2026-11-02T13:30 age_min=32"
    ]
    loaded_before = {("gs://b/raw/rtd_gtfsrt_stream/snapshot_at=2026-11-01T00:00/x.csv.gz", "h")}
    assert warnings([], loaded_before, now, caplog) == [
        "STREAM_MISSING no stream batch in the load window"
    ]
    assert warnings([], set(), now, caplog) == []  # poller not deployed yet: stay quiet
