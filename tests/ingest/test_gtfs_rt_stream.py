"""Offline tests for the stream poller: batching, checkpoints, uploads, skipping and replay."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest
from google.api_core.exceptions import PreconditionFailed
from google.transit import gtfs_realtime_pb2 as rt
from test_rt_engine import SD, T, gtfs_zip, ll

from whyline.ingest import gtfs_rt_stream as stream
from whyline.ingest import rt_static
from whyline.ingest.rt_engine import TripUpdateDiff, VisitEngine


def tu_payload(ts: int, stops: dict[int, int]) -> bytes:
    msg = rt.FeedMessage()
    msg.header.gtfs_realtime_version = "2.0"
    msg.header.timestamp = ts
    tu = msg.entity.add(id="T1").trip_update
    tu.trip.trip_id, tu.trip.start_date, tu.trip.route_id = "T1", SD, "15"
    tu.timestamp = ts
    for seq, arrival in stops.items():
        stu = tu.stop_time_update.add(stop_sequence=seq, stop_id=f"S{seq - 1}")
        stu.arrival.time = arrival
    return msg.SerializeToString()


def vp_payload(ts: int, x: float, stop_id: str, status: int) -> bytes:
    msg = rt.FeedMessage()
    msg.header.gtfs_realtime_version = "2.0"
    msg.header.timestamp = ts
    v = msg.entity.add(id="V1").vehicle
    v.trip.trip_id, v.trip.start_date, v.trip.route_id = "T1", SD, "15"
    v.vehicle.id = "V1"
    v.position.latitude, v.position.longitude = ll(x, 0.0)
    v.timestamp, v.stop_id, v.current_status = ts, stop_id, status
    return msg.SerializeToString()


def static_zip(route: str = "15") -> bytes:
    shape = [(x, 0.0) for x in range(0, 2600, 100)]
    stops = {f"S{i}": (500.0 * i, 0.0) for i in range(5)}
    rows = [(i + 1, f"S{i}", 500.0 * i) for i in range(5)]
    return gtfs_zip({"shp": shape}, stops, [("T1", route, "3", "shp", rows)])


# The far-side worked example as raw feed payloads, in arrival order.
FEED = [
    ("tu", tu_payload(T(15, 41, 0), {3: T(15, 42, 0), 4: T(15, 44, 0), 5: T(15, 46, 0)})),
    ("vp", vp_payload(T(15, 41, 31), 820, "S2", rt.VehiclePosition.IN_TRANSIT_TO)),
    ("vp", vp_payload(T(15, 42, 1), 1035, "S2", rt.VehiclePosition.STOPPED_AT)),
    ("vp", vp_payload(T(15, 42, 31), 1038, "S2", rt.VehiclePosition.STOPPED_AT)),
    ("tu", tu_payload(T(15, 42, 35), {4: T(15, 44, 0), 5: T(15, 46, 0)})),
    ("vp", vp_payload(T(15, 43, 1), 1260, "S3", rt.VehiclePosition.IN_TRANSIT_TO)),
]


def read_gz_csv(path: Path) -> list[list[str]]:
    return list(csv.reader(io.StringIO(gzip.decompress(path.read_bytes()).decode())))


def args_for(tmp_path: Path, *extra: str):
    return stream.build_parser().parse_args(
        [
            "--local",
            "--local-root",
            str(tmp_path / "data"),
            "--state-dir",
            str(tmp_path / "state"),
            *extra,
        ]
    )


def test_window_seal_writes_loader_manifest_and_archive(tmp_path):
    window = stream.Window(tmp_path, T(15, 30, 0))
    window.write("tu_changes", [tuple(range(16))])
    window.write("vp_reports", [tuple([None] * 22 + [True])])
    window.archive("tu", 100, b"tu-bytes")
    window.archive("vp", 101, b"vp-bytes")
    out = window.seal(
        tmp_path / "outbox",
        {"raw_root": "gs://b/raw/rtd_gtfsrt_stream", "source": {}, "static_md5": "abc"},
    )

    manifest = json.loads((out / "manifest.json").read_text())
    assert out.name == "2026-10-28T15:30" and manifest["snapshot_label"] == out.name
    for name, columns in stream.OUTPUTS.items():
        rows = read_gz_csv(out / f"{name}.csv.gz")
        assert rows[0] == list(columns)  # the loader maps columns by position
        meta = manifest["files"][f"{name}.csv.gz"]
        assert meta["row_count"] == len(rows) - 1
        assert (
            meta["hash_md5"]
            == hashlib.md5((out / f"{name}.csv.gz").read_bytes(), usedforsecurity=False).hexdigest()
        )
        assert meta["path"] == f"gs://b/raw/rtd_gtfsrt_stream/snapshot_at={out.name}/{name}.csv.gz"
    assert read_gz_csv(out / "vp_reports.csv.gz")[1][-1] == "true"
    with tarfile.open(out / "archive.tar") as tar:
        assert tar.getnames() == ["tu/100.pb.gz", "vp/101.pb.gz", "meta.json"]
        assert gzip.decompress(tar.extractfile("vp/101.pb.gz").read()) == b"vp-bytes"
        assert json.loads(tar.extractfile("meta.json").read())["static_md5"] == "abc"
    assert not window.dir.exists()
    with pytest.raises(FileExistsError):  # a second seal of the same label must not overwrite
        stream.Window(tmp_path, T(15, 30, 0)).seal(
            tmp_path / "outbox", {"raw_root": "x", "source": {}}
        )


def test_checkpoint_restore_truncates_unsaved_rows(tmp_path):
    s = stream.Stream(args_for(tmp_path))
    s.ensure_window(T(15, 31, 0))
    s.window.write("tu_changes", [tuple(range(16))])
    s.checkpoint()
    s.window.write(
        "tu_changes", [tuple(range(16))] * 3
    )  # written after the checkpoint, then a crash
    restored = stream.Stream(args_for(tmp_path))
    restored.restore()
    assert restored.window.rows["tu_changes"] == 1
    lines = (restored.window.dir / "tu_changes.csv").read_text().splitlines()
    assert len(lines) == 2  # header + the checkpointed row


def test_restore_ignores_a_window_sealed_after_the_checkpoint(tmp_path):
    s = stream.Stream(args_for(tmp_path))
    s.ensure_window(T(15, 31, 0))
    s.window.write("tu_changes", [tuple(range(16))])
    s.checkpoint()
    state_before_seal = s.checkpoint_path.read_bytes()
    s.seal()  # moves the batch to the outbox
    s.checkpoint_path.write_bytes(state_before_seal)  # crash before the post-seal checkpoint
    restored = stream.Stream(args_for(tmp_path))
    restored.restore()
    assert restored.window is None
    assert [p.name for p in restored.outbox.iterdir()] == ["2026-10-28T15:30"]


class FakeResponse:
    def __init__(self, status: int, content: bytes = b"", etag: str | None = None):
        self.status_code, self.content = status, content
        self.headers = {"ETag": etag} if etag else {}


def test_poll_skips_not_modified_and_repeated_headers(tmp_path, monkeypatch):
    payload = tu_payload(T(15, 41, 0), {3: T(15, 42, 0)})
    responses = iter(
        [FakeResponse(200, payload, "e1"), FakeResponse(304), FakeResponse(200, payload, "e2")]
    )
    seen_headers = []

    def fake_get(url, *, headers=None, **_kw):
        seen_headers.append(headers)
        return next(responses) if "TripUpdate" in url else FakeResponse(304)

    monkeypatch.setattr(stream.io, "http_get_with_retry", fake_get)
    s = stream.Stream(args_for(tmp_path))
    s.ensure_window(T(15, 41, 0))
    assert [s.poll_once() for _ in range(3)] == [True, False, False]
    stats = s.window.stats
    assert (stats["tu_refreshes"], stats["tu_not_modified"], stats["tu_same_header"]) == (1, 1, 1)
    assert {"If-None-Match": "e1"} in seen_headers  # conditional GET after the first 200
    with tarfile.open(s.window.tar_path) as tar:  # only the processed refresh is archived
        assert tar.getnames() == [f"tu/{T(15, 41, 0)}.pb.gz"]


def test_gcs_publish_treats_existing_objects_as_uploaded(tmp_path, monkeypatch):
    calls = []

    def fake_upload(bucket, path, data, content_type, *, if_generation_match=None):
        calls.append((bucket, path, if_generation_match))
        raise PreconditionFailed("exists")

    monkeypatch.setattr(stream.io, "upload_bytes_gcs", fake_upload)
    window = stream.Window(tmp_path, T(15, 30, 0))
    batch = window.seal(tmp_path / "outbox", {"raw_root": "r", "source": {}})
    stream.GcsSink("raw-bucket", "archive-bucket").publish(batch)
    assert {c[2] for c in calls} == {0}
    assert ("archive-bucket", "rtd_gtfsrt/date=2026-10-28/1530.tar", 0) in calls
    assert (
        "raw-bucket",
        "raw/rtd_gtfsrt_stream/snapshot_at=2026-10-28T15:30/manifest.json",
        0,
    ) in calls


def test_outbox_keeps_a_batch_until_upload_succeeds(tmp_path):
    s = stream.Stream(args_for(tmp_path))
    s.ensure_window(T(15, 31, 0))
    s.seal()
    attempts = []

    class FlakySink:
        raw_root = "r"

        def publish(self, batch):
            attempts.append(batch.name)
            if len(attempts) == 1:
                raise OSError("network down")

    s.sink = FlakySink()
    s.drain_outbox(1000.0)
    assert len(list(s.outbox.iterdir())) == 1
    s.drain_outbox(1001.0)  # inside the backoff: no new attempt
    assert len(attempts) == 1
    s.drain_outbox(1000.0 + s.upload_backoff)
    assert attempts == ["2026-10-28T15:30", "2026-10-28T15:30"] and not any(s.outbox.iterdir())


def test_replay_reproduces_live_visits(tmp_path):
    payload = static_zip()
    cache = stream.StaticCache(tmp_path / "static")
    md5, _ = cache.add(payload, 0)
    live = stream.Processor(VisitEngine(cache.lookup), TripUpdateDiff())
    window = stream.Window(tmp_path / "live", stream.window_start(T(15, 41, 0)))
    for kind, data in FEED:
        ts = live.handle(kind, data, window)
        window.archive(kind, ts, data)
    sink = stream.LocalSink(tmp_path / "data")
    sink.put_static(md5, payload)
    sink.publish(
        window.seal(
            tmp_path / "outbox", {"raw_root": sink.raw_root, "source": {}, "static_md5": md5}
        )
    )
    live_visits = read_gz_csv(
        next((tmp_path / "data/raw/rtd_gtfsrt_stream").glob("*/stop_visits.csv.gz"))
    )
    assert len(live_visits) == 2 and live_visits[1][11] == "2026-10-28T15:41:56Z"

    args = stream.build_parser().parse_args(
        ["--replay", str(tmp_path / "data/archive"), "--out", str(tmp_path / "replay")]
    )
    assert stream.run(args) == 0
    replayed = read_gz_csv(next((tmp_path / "replay").glob("snapshot_at=*/stop_visits.csv.gz")))
    assert replayed[:2] == live_visits[:2]  # same rows from the same payloads and static


def test_static_cache_keeps_the_version_a_trip_started_on(tmp_path):
    cache = stream.StaticCache(tmp_path)
    old, _ = cache.add(static_zip(), 0)
    new_payload = static_zip(route="16")
    new, changed = cache.add(new_payload, 3600)
    assert changed and cache.current == new != old
    assert cache.lookup("T1", old).feed.md5 == old  # pinned version still served
    assert cache.lookup("T1", None).feed.md5 == new
    cache.add(new_payload, 3600 + stream.STATIC_KEEP_SEC + 1)
    assert old not in cache.feeds
    assert isinstance(cache.lookup("T1", old).feed, rt_static.StaticFeed)  # falls back to current
