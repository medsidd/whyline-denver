"""Offline tests for the realtime stream engine (static geometry, diff, visits)."""

from __future__ import annotations

import io
import math
import pickle
import zipfile
from datetime import UTC, datetime

import pytest
from google.transit import gtfs_realtime_pb2 as rt

from whyline.ingest import rt_static
from whyline.ingest.rt_engine import (
    TRIP_STATUS_COLUMNS,
    VISIT_COLUMNS,
    Geom,
    Report,
    StopUpdate,
    TripListing,
    TripUpdateDiff,
    VisitEngine,
    parse_trip_updates,
    parse_vehicle_positions,
)

SD = "20261028"


def T(h: int, m: int, s: int) -> int:
    return int(datetime(2026, 10, 28, h, m, s, tzinfo=UTC).timestamp())


def ll(x: float, y: float) -> tuple[float, float]:
    """Inverse of rt_static.to_xy."""
    return rt_static.LAT0 + y / rt_static._KY, rt_static.LON0 + x / rt_static._KX


def gtfs_zip(shapes, stops, trips, *, with_dist=True) -> bytes:
    """shapes: {id: [(x, y)]}; stops: {id: (x, y)}; trips: [(trip, route, type, shape, [(seq, stop, dist)])]."""
    files = {
        "routes.txt": ["route_id,route_type"],
        "stops.txt": ["stop_id,stop_lat,stop_lon"],
        "trips.txt": ["trip_id,route_id,direction_id,shape_id,trip_headsign"],
        "stop_times.txt": ["trip_id,stop_sequence,stop_id,shape_dist_traveled"],
        "shapes.txt": ["shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence,shape_dist_traveled"],
    }
    for sid, (x, y) in stops.items():
        lat, lon = ll(x, y)
        files["stops.txt"].append(f"{sid},{lat:.8f},{lon:.8f}")
    for shape_id, pts in shapes.items():
        run = 0.0
        for i, (x, y) in enumerate(pts):
            if i:
                run += math.hypot(x - pts[i - 1][0], y - pts[i - 1][1])
            lat, lon = ll(x, y)
            dist = f"{run:.2f}" if with_dist else ""
            files["shapes.txt"].append(f"{shape_id},{lat:.8f},{lon:.8f},{i + 1},{dist}")
    routes = set()
    for trip_id, route_id, route_type, shape_id, rows in trips:
        if route_id not in routes:
            files["routes.txt"].append(f"{route_id},{route_type}")
            routes.add(route_id)
        files["trips.txt"].append(f"{trip_id},{route_id},0,{shape_id},Downtown")
        for seq, stop_id, dist in rows:
            files["stop_times.txt"].append(f"{trip_id},{seq},{stop_id},{dist if with_dist else ''}")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, lines in files.items():
            z.writestr(name, "\n".join(lines) + "\n")
    return buf.getvalue()


def straight_feed() -> rt_static.StaticFeed:
    shape = [(x, 0.0) for x in range(0, 2600, 100)]
    stops = {f"S{i}": (500.0 * i, 0.0) for i in range(5)}
    rows = [(i + 1, f"S{i}", 500.0 * i) for i in range(5)]
    return rt_static.load_zip(gtfs_zip({"shp": shape}, stops, [("T1", "15", "3", "shp", rows)]))


class Harness:
    def __init__(self, feed: rt_static.StaticFeed):
        self.feed = feed
        self.engine = VisitEngine(self.lookup)
        self.visits: list[dict] = []
        self.status: list[dict] = []

    def lookup(self, trip_id: str, md5: str | None, start_date: str = "") -> Geom | None:
        trip = self.feed.trips.get(trip_id)
        return Geom(trip, self.feed.shapes[trip.shape_id], self.feed) if trip else None

    def _drain(self):
        visits, status = self.engine.drain()
        self.visits += [dict(zip(VISIT_COLUMNS, v, strict=True)) for v in visits]
        self.status += [dict(zip(TRIP_STATUS_COLUMNS, s, strict=True)) for s in status]

    def tu(self, ts: int, stops: dict[int, tuple[str, int | None, str]] | None, rel="SCHEDULED"):
        trips = {}
        if stops is not None:
            ups = {
                seq: StopUpdate(sid, pred, None, None, None, r)
                for seq, (sid, pred, r) in stops.items()
            }
            trips[("T1", SD)] = TripListing("T1", SD, "15", 0, rel, ts, None, ups)
        self.engine.on_trip_updates(ts, trips)
        self._drain()

    def vp(
        self, ts: int, x: float, y: float, stop_id: str, status: str | None, *, age=0, vehicle="V1"
    ):
        lat, lon = ll(x, y)
        r = Report(
            ts - age,
            "e1",
            vehicle,
            "",
            "T1",
            SD,
            "15",
            0,
            None,
            stop_id,
            status,
            lat,
            lon,
            None,
            None,
            None,
        )
        self.engine.on_reports(ts, [r])
        self._drain()
        return r

    def flush(self):
        self.engine.flush()
        self._drain()

    def visit(self, seq: int) -> dict:
        (row,) = (v for v in self.visits if v["stop_sequence"] == seq)
        return row


PRED_BASE = T(15, 50, 0)


def listed(*seqs: int, base: int = PRED_BASE) -> dict[int, tuple[str, int, str]]:
    return {seq: (f"S{seq - 1}", base + 60 * seq, "SCHEDULED") for seq in seqs}


def test_far_side_stop_worked_example():
    h = Harness(straight_feed())
    h.tu(T(15, 41, 0), listed(3, 4, 5))
    h.vp(T(15, 41, 31), 1000 - 180, 0, "S2", "IN_TRANSIT_TO")
    h.vp(T(15, 42, 1), 1035, 0, "S2", "STOPPED_AT")
    h.vp(T(15, 42, 31), 1038, 0, "S2", "STOPPED_AT")
    h.tu(T(15, 42, 35), listed(4, 5))
    assert h.visits == []  # still at the stop: departure not yet known
    h.vp(T(15, 43, 1), 1260, 0, "S3", "IN_TRANSIT_TO")
    v = h.visit(3)
    assert v["arrival_ts_utc"] == "2026-10-28T15:41:56Z"
    assert (v["arrival_earliest_ts"], v["arrival_latest_ts"]) == (
        "2026-10-28T15:41:31Z",
        "2026-10-28T15:42:01Z",
    )
    assert v["arrival_method"] == "shape_crossing"
    assert v["stopped_observed"] is True
    assert (v["departure_earliest_ts"], v["departure_latest_ts"]) == (
        "2026-10-28T15:42:31Z",
        "2026-10-28T15:43:01Z",
    )
    assert (v["dwell_min_sec"], v["dwell_max_sec"]) == (30, 60)
    assert v["service_date"] == "2026-10-28" and v["stop_role"] == "middle"
    assert v["is_final"] is True and v["data_version"] == "stream_v1"


def test_crossing_without_stopping():
    h = Harness(straight_feed())
    h.tu(T(15, 41, 0), listed(3, 4, 5))
    h.vp(T(15, 41, 35), 1000 - 250, 0, "S2", "IN_TRANSIT_TO")
    h.vp(T(15, 42, 5), 1000 + 150, 0, "S3", "IN_TRANSIT_TO")
    h.tu(T(15, 42, 35), listed(4, 5))
    v = h.visit(3)
    assert v["arrival_ts_utc"] == "2026-10-28T15:41:54Z"
    assert v["arrival_method"] == "shape_crossing"
    assert v["stopped_observed"] is False
    assert v["departure_earliest_ts"] is None and v["dwell_min_sec"] is None


def test_bus_stopped_short_of_the_pole():
    h = Harness(straight_feed())
    h.tu(T(15, 41, 0), listed(3, 4, 5))
    h.vp(T(15, 41, 31), 750, 0, "S2", "IN_TRANSIT_TO")
    h.vp(T(15, 42, 1), 970, 0, "S2", "STOPPED_AT")
    h.vp(T(15, 42, 31), 972, 0, "S2", "STOPPED_AT")
    h.vp(T(15, 43, 1), 1150, 0, "S3", "IN_TRANSIT_TO")
    h.tu(T(15, 43, 5), listed(4, 5))
    v = h.visit(3)
    # Pure pole crossing would put this at the departure (about 15:42:36).
    assert v["arrival_ts_utc"] == "2026-10-28T15:41:46Z"
    assert v["arrival_latest_ts"] == "2026-10-28T15:42:01Z"
    assert (v["dwell_min_sec"], v["dwell_max_sec"]) == (30, 60)


def test_gap_longer_than_30_seconds():
    h = Harness(straight_feed())
    h.vp(T(15, 41, 31), 820, 0, "S2", "IN_TRANSIT_TO")
    h.vp(T(15, 43, 31), 1300, 0, "S3", "IN_TRANSIT_TO")
    h.flush()
    v = h.visit(3)
    assert v["arrival_method"] == "shape_crossing_gap"
    assert v["arrival_earliest_ts"] == "2026-10-28T15:41:31Z"
    assert v["arrival_latest_ts"] == "2026-10-28T15:43:31Z"
    assert v["arrival_ts_utc"] == "2026-10-28T15:42:16Z"  # 31 s + 120 s * 180/480


def test_corner_uses_along_route_distance():
    shape = [(x, 0.0) for x in range(0, 501, 50)] + [(500.0, y) for y in range(50, 501, 50)]
    stops = {"S0": (0.0, 0.0), "S1": (500.0, 100.0), "S2": (500.0, 500.0)}
    rows = [(1, "S0", 0.0), (2, "S1", 600.0), (3, "S2", 1000.0)]
    feed = rt_static.load_zip(gtfs_zip({"L": shape}, stops, [("T1", "15", "3", "L", rows)]))
    h = Harness(feed)
    h.vp(T(15, 0, 0), 450, 0, "S1", "IN_TRANSIT_TO")
    r = h.vp(T(15, 0, 30), 498, 170, "S2", "IN_TRANSIT_TO")
    assert r.dist == pytest.approx(670.0, abs=1.0) and r.lateral == pytest.approx(2.0, abs=0.5)
    h.flush()
    assert h.visit(2)["arrival_ts_utc"] == "2026-10-28T15:00:20Z"  # 30 s * 150/220


def test_loop_serving_the_same_stop_twice():
    out = [(x, 0.0) for x in range(0, 1001, 100)]
    back = [(x, 8.0) for x in range(1000, -1, -100)]
    stops = {
        "A": (0.0, 0.0),
        "X": (300.0, 4.0),
        "M": (1000.0, 4.0),
        "R": (700.0, 8.0),
        "E": (0.0, 8.0),
    }
    rows = [
        (1, "A", 0.0),
        (2, "X", 300.0),
        (3, "M", 1004.0),
        (4, "R", 1308.0),
        (5, "X", 1708.0),
        (6, "E", 2008.0),
    ]
    feed = rt_static.load_zip(gtfs_zip({"O": out + back}, stops, [("T1", "15", "3", "O", rows)]))
    h = Harness(feed)
    h.vp(T(16, 0, 0), 100, 0, "X", "IN_TRANSIT_TO")
    h.vp(T(16, 0, 30), 420, 1, "M", "IN_TRANSIT_TO")
    h.vp(T(16, 1, 0), 900, 0, "M", "IN_TRANSIT_TO")
    h.vp(T(16, 1, 30), 950, 8, "R", "IN_TRANSIT_TO")
    # Nearer the outbound lane: an unconstrained projection would snap to the wrong pass.
    r = h.vp(T(16, 2, 0), 500, 3, "X", "IN_TRANSIT_TO")
    assert r.dist == pytest.approx(1508.0, abs=1.0)
    h.vp(T(16, 2, 30), 150, 7, "E", "IN_TRANSIT_TO")
    h.flush()
    assert h.visit(2)["arrival_ts_utc"] == "2026-10-28T16:00:19Z"
    assert h.visit(5)["arrival_ts_utc"] == "2026-10-28T16:02:17Z"
    assert h.visit(2)["stop_id"] == h.visit(5)["stop_id"] == "X"


def test_last_prediction_worked_example():
    h = Harness(straight_feed())
    later = {seq: (f"S{seq - 1}", T(15, 50, 0), "SCHEDULED") for seq in (4, 5)}
    stop2 = {2: ("S1", T(15, 41, 20), "SCHEDULED")}
    h.tu(T(15, 38, 0), {**stop2, **later, 3: ("S2", T(15, 42, 40), "SCHEDULED")})
    h.tu(T(15, 41, 0), {**stop2, **later, 3: ("S2", T(15, 42, 10), "SCHEDULED")})
    h.tu(T(15, 41, 30), {**later, 3: ("S2", T(15, 42, 10), "SCHEDULED")})  # stop 2 served
    h.tu(T(15, 42, 30), later)  # stop 3 gone: two due drops in order show the trip ran
    assert h.visits == []  # no vehicle yet: give one the grace period to produce a crossing
    h.flush()
    v = h.visit(3)
    assert v["arrival_method"] == "last_prediction"
    assert v["arrival_ts_utc"] == "2026-10-28T15:42:10Z"
    assert (v["arrival_earliest_ts"], v["arrival_latest_ts"]) == (
        "2026-10-28T15:41:00Z",
        "2026-10-28T15:42:30Z",
    )
    assert v["last_prediction_published_ts"] == "2026-10-28T15:41:00Z"


def test_stops_dropped_before_due_are_not_visits_and_do_not_block_crossings():
    # Observed live: RTD dropped all 52 stops of a late trip at once while it stayed listed.
    h = Harness(straight_feed())
    future = {seq: (f"S{seq - 1}", T(15, 20, 0) + 60 * seq, "SCHEDULED") for seq in (2, 3, 4, 5)}
    h.tu(T(15, 0, 0), future)
    h.tu(T(15, 0, 30), {})  # still listed, every stop dropped long before it was due
    h.vp(T(15, 1, 0), 300, 0, "S1", "IN_TRANSIT_TO")
    h.vp(T(15, 1, 30), 700, 0, "S2", "IN_TRANSIT_TO")
    h.flush()
    assert [(v["stop_sequence"], v["arrival_method"]) for v in h.visits] == [(2, "shape_crossing")]


def test_vanished_trip_gets_no_visits():
    h = Harness(straight_feed())
    h.tu(T(15, 0, 0), listed(1, 2, 3, 4, 5))
    h.tu(T(15, 0, 30), None)
    h.flush()
    assert h.visits == []
    (status,) = h.status
    assert status["outcome"] == "vanished" and status["n_visits"] == 0


def test_canceled_trip_is_status_only():
    h = Harness(straight_feed())
    h.tu(T(15, 0, 0), {}, rel="CANCELED")
    h.tu(T(15, 0, 30), None)
    h.flush()
    assert h.visits == []
    assert h.status[0]["outcome"] == "canceled"
    assert h.status[0]["final_schedule_relationship"] == "CANCELED"


def test_skipped_stop_has_no_arrival():
    h = Harness(straight_feed())
    h.tu(T(15, 0, 0), {**listed(4, 5), 3: ("S2", T(15, 5, 0), "SKIPPED")})
    h.tu(T(15, 0, 30), listed(4, 5))
    v = h.visit(3)
    assert v["skipped"] is True and v["arrival_method"] == "skipped"
    assert v["arrival_ts_utc"] is None and v["arrival_earliest_ts"] is None


def test_terminal_recorded_from_prediction_when_trip_vanishes():
    h = Harness(straight_feed())
    h.tu(T(15, 0, 0), listed(4, 5))
    h.vp(T(15, 0, 10), 1600, 0, "S4", "IN_TRANSIT_TO")
    h.tu(T(15, 1, 0), {5: ("S4", T(15, 2, 0), "SCHEDULED")})
    h.tu(T(15, 1, 30), None)  # gone: only the final stop was left, predicted within 2 minutes
    h.flush()
    v = h.visit(5)
    assert v["arrival_method"] == "last_prediction" and v["stop_role"] == "last"
    assert h.status[0]["outcome"] == "completed"


def test_repeated_and_stale_reports_are_not_timing_evidence():
    h = Harness(straight_feed())
    first = h.vp(T(15, 0, 0), 800, 0, "S2", "IN_TRANSIT_TO")
    lat, lon = ll(1200, 0)
    repeat = Report(
        first.report_ts,
        "e1",
        "V1",
        "",
        "T1",
        SD,
        "15",
        0,
        None,
        "S3",
        None,
        lat,
        lon,
        None,
        None,
        None,
    )
    h.engine.on_reports(T(15, 0, 30), [repeat])
    assert repeat.is_repeat and not repeat.valid
    stale = h.vp(T(15, 1, 0), 1300, 0, "S3", "IN_TRANSIT_TO", age=200)
    assert stale.age == 200 and not stale.valid
    far = h.vp(T(15, 1, 30), 1250, 400, "S3", "IN_TRANSIT_TO")
    assert far.lateral == pytest.approx(400, abs=1) and not far.valid
    h.flush()
    assert h.visits == []  # no valid pair brackets stop 3


def test_bounding_box_covers_the_whole_network():
    """Eldora (NB1) and north Longmont (327) are inside; a 0,0 fix and Grand Junction are not."""
    h = Harness(straight_feed())
    points = [
        ((39.9377, -105.5841), True),
        ((40.2067, -105.1), True),
        ((0.0, 0.0), False),
        ((39.0639, -108.5506), False),
    ]
    for i, ((lat, lon), inside) in enumerate(points):
        r = Report(
            T(15, 0, i),
            "e1",
            f"V{i}",
            "",
            "T1",
            SD,
            "15",
            0,
            None,
            "S2",
            None,
            lat,
            lon,
            None,
            None,
            None,
        )
        h.engine.on_reports(T(15, 0, i), [r])
        assert r.in_bbox is inside


def test_engine_survives_a_checkpoint_round_trip():
    def run(split: bool) -> list[dict]:
        h = Harness(straight_feed())
        h.tu(T(15, 41, 0), listed(3, 4, 5))
        h.vp(T(15, 41, 31), 820, 0, "S2", "IN_TRANSIT_TO")
        h.vp(T(15, 42, 1), 1035, 0, "S2", "STOPPED_AT")
        if split:
            h.engine = pickle.loads(pickle.dumps(h.engine))  # noqa: S301 - our own object
            assert h.engine.lookup is None
            h.engine.lookup = h.lookup
        h.vp(T(15, 42, 31), 1038, 0, "S2", "STOPPED_AT")
        h.tu(T(15, 42, 35), listed(4, 5))
        h.vp(T(15, 43, 1), 1260, 0, "S3", "IN_TRANSIT_TO")
        return h.visits

    assert run(split=True) == run(split=False) and len(run(split=False)) == 1


def test_trip_update_diff_emits_changes_drops_and_vanish():
    def trips(stops):
        ups = {
            seq: StopUpdate(sid, arr, None, None, None, "SCHEDULED")
            for seq, (sid, arr) in stops.items()
        }
        return {("T1", SD): TripListing("T1", SD, "15", 0, "SCHEDULED", 1, None, ups)}

    diff = TripUpdateDiff()
    first = diff.apply(100, trips({1: ("S0", 1000), 2: ("S1", 2000)}))
    assert [r[1] for r in first] == ["trip_new", "new", "new"]
    second = diff.apply(130, trips({2: ("S1", 2010)}))
    assert [(r[1], r[9]) for r in second] == [("changed", 2), ("dropped", 1)]
    assert second[1][11] == "1970-01-01T00:16:40Z"  # a dropped row carries the last emitted time
    assert diff.apply(160, trips({2: ("S1", 2010)})) == []
    assert [r[1] for r in diff.apply(190, {})] == ["trip_vanished"]


def test_protobuf_parsers_keep_absolute_times_and_vehicle_fields():
    msg = rt.FeedMessage()
    msg.header.gtfs_realtime_version = "2.0"
    msg.header.timestamp = 1000
    tu = msg.entity.add(id="1").trip_update
    tu.trip.trip_id, tu.trip.start_date = "T1", SD
    tu.timestamp = 990
    stu = tu.stop_time_update.add(stop_sequence=3, stop_id="S2")
    stu.arrival.time = 1100
    ts, trips = parse_trip_updates(msg.SerializeToString())
    assert ts == 1000
    assert (
        trips[("T1", SD)].stops[3].arrival == 1100
        and trips[("T1", SD)].stops[3].arrival_delay is None
    )

    msg = rt.FeedMessage()
    msg.header.gtfs_realtime_version = "2.0"
    msg.header.timestamp = 1000
    v = msg.entity.add(id="9").vehicle
    v.trip.trip_id, v.trip.start_date, v.trip.direction_id = "T1", SD, 1
    v.vehicle.id = "6001"
    v.position.latitude, v.position.longitude = 39.74, -104.99
    v.timestamp, v.stop_id = 995, "S2"
    v.current_status = rt.VehiclePosition.STOPPED_AT
    ts, (report,) = parse_vehicle_positions(msg.SerializeToString())
    assert (report.vehicle_id, report.stop_id, report.status, report.direction_id) == (
        "6001",
        "S2",
        "STOPPED_AT",
        1,
    )


def test_static_without_shape_dist_traveled_projects_stops():
    shape = [(x, 0.0) for x in range(0, 2001, 100)]
    stops = {"S0": (0.0, 0.0), "S1": (700.0, 3.0), "S2": (1500.0, -2.0)}
    rows = [(1, "S0", 0), (2, "S1", 0), (3, "S2", 0)]
    feed = rt_static.load_zip(
        gtfs_zip({"shp": shape}, stops, [("T1", "15", "3", "shp", rows)], with_dist=False)
    )
    trip = feed.trips["T1"]
    assert list(trip.dists) == pytest.approx([0.0, 700.0, 1500.0], abs=8.0)
    assert feed.shapes["shp"].ds[-1] == pytest.approx(2000.0, rel=0.01)
