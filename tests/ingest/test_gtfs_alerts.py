"""RTD service alerts: protobuf parsing and the snapshot files the loader reads."""

from __future__ import annotations

import gzip
import io
import json
import re

import pandas as pd
from google.transit import gtfs_realtime_pb2

from whyline.ingest import gtfs_alerts
from whyline.load import bq_load
from whyline.load.registry import JOBS

CELL = {
    "TIMESTAMP": re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"),
    "INT64": re.compile(r"-?\d+"),
    "STRING": re.compile(r".*", re.S),
}


def _feed() -> bytes:
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = 1793637796  # 2026-11-02T16:43:16Z
    closure = feed.entity.add(id="85437").alert
    closure.cause = gtfs_realtime_pb2.Alert.CONSTRUCTION
    closure.effect = gtfs_realtime_pb2.Alert.NO_SERVICE
    closure.header_text.translation.add(text="Stop closed", language="en")
    closure.description_text.translation.add(
        text="Use the stop\nacross the street, please", language="en"
    )
    for stop in ("12478", "12479"):
        closure.informed_entity.add(route_id="15", route_type=3, stop_id=stop)
    closure.active_period.add(start=1736330400)  # open-ended
    closure.active_period.add(start=1793600000, end=1793610000)
    detour = feed.entity.add(id="90001").alert  # no cause, no periods, a trip
    detour.effect = gtfs_realtime_pb2.Alert.DETOUR
    detour.header_text.translation.add(text="Desvío", language="es")
    detour.informed_entity.add(agency_id="RTD", direction_id=1).trip.trip_id = "T9"
    feed.entity.add(id="vp").vehicle.vehicle.id = "not an alert"
    return feed.SerializeToString()


def test_alerts_parse_into_entity_and_period_rows():
    alerts, periods = gtfs_alerts.parse_alerts(_feed())
    assert list(alerts.alert_id) == ["85437", "85437", "90001"]
    first = alerts.iloc[0]
    assert (first.cause, first.effect, first.stop_id, first.route_type) == (
        "CONSTRUCTION",
        "NO_SERVICE",
        "12478",
        3,
    )
    assert first.feed_ts_utc == "2026-11-02T16:43:16Z"
    detour = alerts.iloc[2]
    assert pd.isna(detour.cause) and detour.header_text == "Desvío"  # first translation
    assert (detour.trip_id, detour.direction_id, detour.agency_id) == ("T9", 1, "RTD")
    assert periods.values.tolist() == [
        ["2026-11-02T16:43:16Z", "85437", "2025-01-08T10:00:00Z", None],
        ["2026-11-02T16:43:16Z", "85437", "2026-11-02T06:13:20Z", "2026-11-02T09:00:00Z"],
    ]


def test_snapshot_files_match_the_registry(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(gtfs_alerts, "fetch_feed", lambda url, timeout: (_feed(), None))
    args = ["--local", "--now-utc", "2026-11-02T16:47:30+00:00"]
    assert gtfs_alerts.main(args) == 0
    snapshot = tmp_path / "data/raw/rtd_gtfsrt_alerts/snapshot_at=2026-11-02T16:47"
    manifest = json.loads((snapshot / "manifest.json").read_text())
    specs = {job.table: job for job in JOBS}
    for name, table in (
        ("alerts.csv.gz", "raw_gtfsrt_alerts"),
        ("alert_periods.csv.gz", "raw_gtfsrt_alert_periods"),
    ):
        job = specs[table]
        assert f"rtd_gtfsrt_alerts/snapshot_at=*/{name}" in job.patterns
        data = (snapshot / name).read_bytes()
        assert manifest["files"][name]["hash_md5"] == bq_load.md5_bytes(data)
        frame = pd.read_csv(io.StringIO(gzip.decompress(data).decode()), dtype=str)
        assert list(frame.columns) == [c.name for c in job.columns], table
        for column in job.columns:
            for value in frame[column.name].dropna():
                assert CELL[column.field_type].fullmatch(value), (table, column.name, value)
    assert bq_load.infer_extract_date(str(snapshot / "alerts.csv.gz")).isoformat() == "2026-11-02"
    # A second run in the same minute leaves the snapshot alone.
    monkeypatch.setattr(gtfs_alerts, "fetch_feed", lambda url, timeout: (None, "boom"))
    assert gtfs_alerts.main(args) == 0


def test_fetch_failure_writes_nothing(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(gtfs_alerts, "fetch_feed", lambda url, timeout: (None, "timeout"))
    assert gtfs_alerts.main(["--local", "--now-utc", "2026-11-02T16:47:30+00:00"]) == 1
    assert not (tmp_path / "data").exists()
