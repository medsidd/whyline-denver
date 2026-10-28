"""The backfill reads the warehouse export and runs the stream engine on 15-minute snapshots."""

from __future__ import annotations

import csv
import gzip
import io
from datetime import UTC, date, datetime

import pyarrow as pa
import pyarrow.parquet as pq
from test_rt_engine import ll

from whyline.ingest import gtfs_rt_backfill

DAY = date(2025, 11, 2)
VERSION = date(2025, 11, 1)


def ts(h: int, m: int) -> datetime:
    return datetime(2025, 11, 2, h, m, tzinfo=UTC)


def write(root, sub: str, rows: dict) -> None:
    (root / sub).mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table(rows), root / sub / "part-0.parquet")


def export(root) -> None:
    stops = {f"S{i}": ll(500.0 * i, 0.0) for i in range(5)}
    shape = [ll(float(x), 0.0) for x in range(0, 2600, 100)]
    v = [VERSION]
    write(root, "service_static", {"service_date": [DAY], "static_version": v})
    write(
        root,
        "version_files",
        {
            "static_version": v * 5,
            "tbl": [
                "raw_gtfs_stops",
                "raw_gtfs_routes",
                "raw_gtfs_trips",
                "raw_gtfs_stop_times",
                "raw_gtfs_shapes",
            ],
            "file_extract": v * 5,
        },
    )
    write(
        root,
        "static/stops",
        {
            "_extract_date": v * 5,
            "stop_id": list(stops),
            "stop_lat": [p[0] for p in stops.values()],
            "stop_lon": [p[1] for p in stops.values()],
        },
    )
    write(root, "static/routes", {"_extract_date": v, "route_id": ["15"], "route_type": ["3"]})
    write(
        root,
        "static/trips",
        {
            "_extract_date": v,
            "trip_id": ["T1"],
            "route_id": ["15"],
            "direction_id": [0],
            "shape_id": ["shp"],
            "trip_headsign": ["Downtown"],
        },
    )
    write(
        root,
        "static/stop_times",
        {
            "_extract_date": v * 5,
            "trip_id": ["T1"] * 5,
            "stop_sequence": [1, 2, 3, 4, 5],
            "stop_id": list(stops),
            "shape_dist_traveled": [500.0 * i for i in range(5)],
        },
    )
    write(
        root,
        "static/shapes",
        {
            "_extract_date": v * len(shape),
            "shape_id": ["shp"] * len(shape),
            "shape_pt_lat": [p[0] for p in shape],
            "shape_pt_lon": [p[1] for p in shape],
            "shape_pt_sequence": list(range(1, len(shape) + 1)),
            "shape_dist_traveled": [float(x) for x in range(0, 2600, 100)],
        },
    )
    # Old snapshot rows: event_ts_utc is the predicted time; no stop fields on vehicles.
    listed = [(ts(15, 0), [2, 3, 4, 5]), (ts(15, 15), [4, 5]), (ts(15, 30), [5])]
    tu = [(feed, seq, ts(15, 5 * (seq - 1))) for feed, seqs in listed for seq in seqs]
    write(
        root,
        f"tu/date={DAY}",
        {
            "feed_ts_utc": [r[0] for r in tu],
            "trip_id": ["T1"] * len(tu),
            "route_id": ["15"] * len(tu),
            "stop_id": [f"S{r[1] - 1}" for r in tu],
            "stop_sequence": [r[1] for r in tu],
            "schedule_relationship": ["SCHEDULED"] * len(tu),
            "event_ts_utc": [r[2] for r in tu],
            "start_date": ["20251102"] * len(tu),
        },
    )
    vp = [(ts(15, 0), 300.0), (ts(15, 15), 1300.0)]  # no report in the 15:30 snapshot
    write(
        root,
        f"vp/date={DAY}",
        {
            "feed_ts_utc": [r[0] for r in vp],
            "trip_id": ["T1"] * 2,
            "route_id": ["15"] * 2,
            "vehicle_id": ["V1"] * 2,
            "lon": [ll(r[1], 0.0)[1] for r in vp],
            "lat": [ll(r[1], 0.0)[0] for r in vp],
            "event_ts_utc": [r[0] for r in vp],
        },
    )


def test_backfill_turns_snapshots_into_flagged_visits(tmp_path):
    export(tmp_path / "export")
    args = [
        "--export",
        str(tmp_path / "export"),
        "--from",
        str(DAY),
        "--until",
        str(DAY),
        "--out",
        str(tmp_path / "out"),
    ]
    assert gtfs_rt_backfill.main(args) == 0
    batch = tmp_path / "out" / "snapshot_at=2025-11-02T00:00"
    visits = {
        int(r["stop_sequence"]): r
        for r in csv.DictReader(
            io.StringIO(gzip.decompress((batch / "stop_visits.csv.gz").read_bytes()).decode())
        )
    }
    assert sorted(visits) == [2, 3, 4]
    assert {visits[s]["arrival_method"] for s in (2, 3)} == {"backfill_shape_crossing"}
    assert visits[2]["arrival_ts_utc"] == "2025-11-02T15:03:00Z"  # 900 s * 200/1000 m
    assert visits[3]["arrival_ts_utc"] == "2025-11-02T15:10:30Z"
    assert (visits[2]["arrival_earliest_ts"], visits[2]["arrival_latest_ts"]) == (
        "2025-11-02T15:00:00Z",
        "2025-11-02T15:15:00Z",
    )
    assert (
        visits[2]["low_confidence"] == "false"
    )  # a 15-minute window is within the 20-minute limit
    assert visits[4]["arrival_method"] == "backfill_prediction"  # vehicle never seen past it
    assert visits[4]["arrival_ts_utc"] == "2025-11-02T15:15:00Z"
    assert {r["data_version"] for r in visits.values()} == {"backfill_v1"}
    assert {r["static_md5"] for r in visits.values()} == {"2025-11-01"}
    status = list(
        csv.DictReader(
            io.StringIO(gzip.decompress((batch / "trip_status.csv.gz").read_bytes()).decode())
        )
    )
    assert [(s["trip_id"], s["outcome"]) for s in status] == [("T1", "partial")]
    assert (batch / "manifest.json").exists()
