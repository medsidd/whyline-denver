"""Realtime stream engine: trip-update diff, report cleaning, along-route projection, stop visits.

Pure logic with no I/O. Every time decision uses feed timestamps, never the wall clock, so a
replay of archived payloads reproduces the live output exactly.
"""

from __future__ import annotations

import bisect
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import NamedTuple

from google.transit import gtfs_realtime_pb2 as rt

from whyline.ingest.rt_static import Shape, StaticFeed, Trip, project, to_xy

# Also used by the snapshot ingestor (gtfs_realtime.py). It holds every RTD shape with margin:
# Eldora reaches -105.58 and north Longmont 40.21 in the October 2026 feed.
LON_MIN, LON_MAX, LAT_MIN, LAT_MAX = -105.7, -104.4, 39.4, 40.3

STALE_SEC = {"stream": 120, "backfill": 600}
LATERAL_MAX_M = 100.0
TOL_BUS_M = 100.0
TOL_RAIL_M = 150.0
WITHIN_SEC = 30
PRED_GUARD_SEC = 60
# A stop leaving the list is evidence of service only if its final prediction had come due.
# RTD can drop every stop of a late trip at once while the trip stays listed (observed
# 2026-10-28: 52 stops dropped with predictions up to 17 minutes ahead).
DUE_SLACK_SEC = 120
LOW_CONFIDENCE_SEC = 1200
FINAL_GRACE_SEC = {"stream": 1200, "backfill": 3600}
TRIP_CLOSE_SEC = {"stream": 600, "backfill": 1800}
TOMBSTONE_SEC = 6 * 3600

TU_CHANGE_COLUMNS = (
    "feed_ts_utc",
    "change_type",
    "trip_id",
    "start_date",
    "route_id",
    "direction_id",
    "trip_schedule_relationship",
    "tu_timestamp_utc",
    "tu_vehicle_id",
    "stop_sequence",
    "stop_id",
    "arrival_ts_utc",
    "departure_ts_utc",
    "arrival_delay_sec",
    "departure_delay_sec",
    "stop_schedule_relationship",
)
VP_COLUMNS = (
    "feed_ts_utc",
    "report_ts_utc",
    "entity_id",
    "vehicle_id",
    "vehicle_label",
    "trip_id",
    "start_date",
    "route_id",
    "direction_id",
    "trip_schedule_relationship",
    "stop_id",
    "current_status",
    "lat",
    "lon",
    "bearing",
    "speed_mps",
    "occupancy_status",
    "report_age_sec",
    "is_repeat",
    "in_bbox",
    "dist_along_m",
    "lateral_offset_m",
    "valid_for_timing",
)
VISIT_COLUMNS = (
    "service_date",
    "trip_id",
    "start_date",
    "stop_sequence",
    "stop_id",
    "stop_role",
    "route_id",
    "direction_id",
    "trip_headsign",
    "vehicle_id",
    "arrival_method",
    "arrival_ts_utc",
    "arrival_earliest_ts",
    "arrival_latest_ts",
    "departure_earliest_ts",
    "departure_latest_ts",
    "dwell_min_sec",
    "dwell_max_sec",
    "skipped",
    "stopped_observed",
    "before_report_ts",
    "before_dist_along_m",
    "after_report_ts",
    "after_dist_along_m",
    "stop_dist_m",
    "nearest_offset_m",
    "last_predicted_arrival_ts",
    "last_prediction_published_ts",
    "trip_switch_at_terminal",
    "low_confidence",
    "is_final",
    "data_version",
    "static_md5",
    "emitted_at",
)
TRIP_STATUS_COLUMNS = (
    "service_date",
    "trip_id",
    "start_date",
    "route_id",
    "direction_id",
    "final_schedule_relationship",
    "outcome",
    "first_seen_ts",
    "last_seen_ts",
    "first_vp_ts",
    "last_vp_ts",
    "had_vehicle",
    "n_stops_static",
    "n_visits",
    "n_shape_crossing",
    "n_last_prediction",
    "n_skipped",
    "data_version",
    "static_md5",
    "closed_at",
)


def iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(round(ts), tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def service_date(start_date: str) -> str:
    return f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]}"


# --------------------------------------------------------------------------- parsing


@dataclass(slots=True)
class StopUpdate:
    stop_id: str
    arrival: int | None
    departure: int | None
    arrival_delay: int | None
    departure_delay: int | None
    relationship: str


@dataclass(slots=True)
class TripListing:
    trip_id: str
    start_date: str
    route_id: str
    direction_id: int | None
    relationship: str
    timestamp: int | None
    vehicle_id: str | None
    stops: dict[int, StopUpdate]


@dataclass(slots=True)
class Report:
    report_ts: int
    entity_id: str
    vehicle_id: str
    vehicle_label: str
    trip_id: str
    start_date: str
    route_id: str
    direction_id: int | None
    trip_relationship: str | None
    stop_id: str
    status: str | None
    lat: float | None
    lon: float | None
    bearing: float | None
    speed: float | None
    occupancy: str | None
    age: int | None = None
    is_repeat: bool = False
    in_bbox: bool = False
    dist: float | None = None
    lateral: float | None = None
    stop_idx: int | None = None
    valid: bool = False


def _event(stu: rt.TripUpdate.StopTimeUpdate, name: str) -> tuple[int | None, int | None]:
    if not stu.HasField(name):
        return None, None
    ev = getattr(stu, name)
    return (
        ev.time if ev.HasField("time") else None,
        ev.delay if ev.HasField("delay") else None,
    )


def parse_trip_updates(payload: bytes) -> tuple[int, dict[tuple[str, str], TripListing]]:
    msg = rt.FeedMessage()
    msg.ParseFromString(payload)
    trips: dict[tuple[str, str], TripListing] = {}
    trip_rel = rt.TripDescriptor.ScheduleRelationship.Name
    stop_rel = rt.TripUpdate.StopTimeUpdate.ScheduleRelationship.Name
    for entity in msg.entity:
        if not entity.HasField("trip_update"):
            continue
        tu = entity.trip_update
        trip = tu.trip
        if not trip.trip_id:
            continue
        stops: dict[int, StopUpdate] = {}
        for stu in tu.stop_time_update:
            if not stu.HasField("stop_sequence"):
                continue  # a stop without a sequence cannot be keyed or diffed
            arrival, arrival_delay = _event(stu, "arrival")
            departure, departure_delay = _event(stu, "departure")
            stops[stu.stop_sequence] = StopUpdate(
                stu.stop_id,
                arrival,
                departure,
                arrival_delay,
                departure_delay,
                stop_rel(stu.schedule_relationship),
            )
        trips[(trip.trip_id, trip.start_date)] = TripListing(
            trip_id=trip.trip_id,
            start_date=trip.start_date,
            route_id=trip.route_id,
            direction_id=trip.direction_id if trip.HasField("direction_id") else None,
            relationship=trip_rel(trip.schedule_relationship),
            timestamp=tu.timestamp if tu.HasField("timestamp") else None,
            vehicle_id=tu.vehicle.id if tu.HasField("vehicle") and tu.vehicle.id else None,
            stops=stops,
        )
    return msg.header.timestamp, trips


def parse_vehicle_positions(payload: bytes) -> tuple[int, list[Report]]:
    msg = rt.FeedMessage()
    msg.ParseFromString(payload)
    reports: list[Report] = []
    status_name = rt.VehiclePosition.VehicleStopStatus.Name
    occupancy_name = rt.VehiclePosition.OccupancyStatus.Name
    trip_rel = rt.TripDescriptor.ScheduleRelationship.Name
    for entity in msg.entity:
        if not entity.HasField("vehicle"):
            continue
        v = entity.vehicle
        trip = v.trip
        pos = v.position if v.HasField("position") else None
        reports.append(
            Report(
                report_ts=v.timestamp,
                entity_id=entity.id,
                vehicle_id=v.vehicle.id or entity.id,
                vehicle_label=v.vehicle.label,
                trip_id=trip.trip_id,
                start_date=trip.start_date,
                route_id=trip.route_id,
                direction_id=trip.direction_id if trip.HasField("direction_id") else None,
                trip_relationship=(
                    trip_rel(trip.schedule_relationship)
                    if trip.HasField("schedule_relationship")
                    else None
                ),
                stop_id=v.stop_id,
                status=status_name(v.current_status) if v.HasField("current_status") else None,
                lat=pos.latitude if pos is not None and pos.HasField("latitude") else None,
                lon=pos.longitude if pos is not None and pos.HasField("longitude") else None,
                bearing=pos.bearing if pos is not None and pos.HasField("bearing") else None,
                speed=pos.speed if pos is not None and pos.HasField("speed") else None,
                occupancy=(
                    occupancy_name(v.occupancy_status) if v.HasField("occupancy_status") else None
                ),
            )
        )
    return msg.header.timestamp, reports


def vp_row(feed_ts: int, r: Report) -> tuple:
    return (
        iso(feed_ts),
        iso(r.report_ts) if r.report_ts else None,
        r.entity_id,
        r.vehicle_id,
        r.vehicle_label or None,
        r.trip_id or None,
        r.start_date or None,
        r.route_id or None,
        r.direction_id,
        r.trip_relationship,
        r.stop_id or None,
        r.status,
        r.lat,
        r.lon,
        r.bearing,
        r.speed,
        r.occupancy,
        r.age,
        r.is_repeat,
        r.in_bbox,
        None if r.dist is None else round(r.dist, 1),
        None if r.lateral is None else round(r.lateral, 1),
        r.valid,
    )


# --------------------------------------------------------------------------- trip-update diff


class TripUpdateDiff:
    """Emit a row when a stop is first seen, changes, or leaves a trip that is still listed."""

    def __init__(self) -> None:
        self.listed: dict[tuple[str, str], TripListing] = {}

    def apply(self, feed_ts: int, trips: dict[tuple[str, str], TripListing]) -> list[tuple]:
        rows: list[tuple] = []
        ts = iso(feed_ts)
        for key, t in trips.items():
            prev = self.listed.get(key)
            if prev is None or prev.relationship != t.relationship:
                rows.append(self._trip_row(ts, "trip_new" if prev is None else "trip_changed", t))
            for seq, s in t.stops.items():
                old = prev.stops.get(seq) if prev is not None else None
                if old is None or (old.arrival, old.departure, old.relationship) != (
                    s.arrival,
                    s.departure,
                    s.relationship,
                ):
                    rows.append(self._stop_row(ts, "new" if old is None else "changed", t, seq, s))
            if prev is not None:
                for seq in sorted(prev.stops.keys() - t.stops.keys()):
                    rows.append(self._stop_row(ts, "dropped", t, seq, prev.stops[seq]))
        for key in sorted(self.listed.keys() - trips.keys()):
            rows.append(self._trip_row(ts, "trip_vanished", self.listed[key]))
        self.listed = trips
        return rows

    @staticmethod
    def _trip_row(ts: str | None, change: str, t: TripListing) -> tuple:
        return (
            ts,
            change,
            t.trip_id,
            t.start_date or None,
            t.route_id or None,
            t.direction_id,
            t.relationship,
            iso(t.timestamp),
            t.vehicle_id,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )

    @staticmethod
    def _stop_row(ts: str | None, change: str, t: TripListing, seq: int, s: StopUpdate) -> tuple:
        return (
            ts,
            change,
            t.trip_id,
            t.start_date or None,
            t.route_id or None,
            t.direction_id,
            t.relationship,
            iso(t.timestamp),
            t.vehicle_id,
            seq,
            s.stop_id or None,
            iso(s.arrival),
            iso(s.departure),
            s.arrival_delay,
            s.departure_delay,
            s.relationship,
        )


# --------------------------------------------------------------------------- visit engine


class Geom(NamedTuple):
    trip: Trip
    shape: Shape
    feed: StaticFeed


@dataclass(slots=True)
class Fix:
    ts: int
    dist: float
    status: str | None
    stop_idx: int | None
    vehicle_id: str
    x: float
    y: float


@dataclass(slots=True)
class Visit:
    idx: int
    created: int
    method: str
    arrival: float | None = None
    earliest: int | None = None
    latest: int | None = None
    before: Fix | None = None
    after: Fix | None = None
    first_stopped: int | None = None
    last_stopped: int | None = None
    dep_earliest: int | None = None
    dep_latest: int | None = None
    stopped_observed: bool = False
    left: bool = False
    skipped: bool = False
    switch: bool = False
    nearest: float | None = None


@dataclass(slots=True)
class TripState:
    trip_id: str
    start_date: str
    md5: str | None
    route_id: str
    direction_id: int | None
    relationship: str = "SCHEDULED"
    first_seen: int = 0
    last_seen: int = 0
    first_vp: int | None = None
    last_vp: int | None = None
    n_fixes: int = 0
    vehicle_id: str | None = None
    progress: int = 0
    fix: Fix | None = None
    listed: dict[int, tuple[int | None, int, str]] = field(default_factory=dict)
    final_pred: dict[int, tuple[int | None, int]] = field(default_factory=dict)
    dropped: dict[int, int] = field(default_factory=dict)
    n_drops: int = 0
    vanished_at: int | None = None
    visits: dict[int, Visit] = field(default_factory=dict)
    emitted: set[int] = field(default_factory=set)
    methods: dict[str, int] = field(default_factory=dict)
    seq_idx: dict[int, int] = field(default_factory=dict)


# lookup(trip_id, pinned_md5, start_date): the static version a trip started on.
Lookup = Callable[[str, "str | None", str], "Geom | None"]


class VisitEngine:
    """Turn cleaned vehicle reports and trip-update listings into final stop visits."""

    def __init__(
        self, lookup: Lookup | None, *, mode: str = "stream", data_version: str = "stream_v1"
    ):
        if mode not in ("stream", "backfill"):
            raise ValueError(f"unknown mode {mode}")
        self.lookup = lookup
        self.mode = mode
        self.data_version = data_version
        self.trips: dict[tuple[str, str], TripState] = {}
        self.vehicle_trip: dict[str, tuple[str, str]] = {}
        self.last_report_ts: dict[str, int] = {}
        self.trip_dates: dict[str, str] = {}
        self.closed: dict[tuple[str, str], int] = {}
        self.tu_keys: set[tuple[str, str]] = set()
        self.now = 0
        self.visit_rows: list[tuple] = []
        self.status_rows: list[tuple] = []

    # The lookup closes over loaded static feeds; it is re-attached after a checkpoint load.
    def __getstate__(self) -> dict:
        state = self.__dict__.copy()
        state["lookup"] = None
        return state

    def __setstate__(self, state: dict) -> None:
        self.__dict__.update(state)

    def drain(self) -> tuple[list[tuple], list[tuple]]:
        visits, status = self.visit_rows, self.status_rows
        self.visit_rows, self.status_rows = [], []
        return visits, status

    # ------------------------------------------------------------------ inputs

    def on_trip_updates(self, feed_ts: int, trips: dict[tuple[str, str], TripListing]) -> None:
        self.now = max(self.now, feed_ts)
        for key, t in trips.items():
            if key in self.closed or not key[1]:
                continue
            st = self._state(key, t.route_id, t.direction_id, feed_ts)
            st.relationship = t.relationship
            st.last_seen = feed_ts
            st.vanished_at = None
            self.trip_dates[key[0]] = key[1]
            listed: dict[int, tuple[int | None, int, str]] = {}
            for seq, s in t.stops.items():
                pred = s.arrival if s.arrival is not None else s.departure
                old = st.listed.get(seq)
                published = old[1] if old is not None and old[0] == pred else feed_ts
                listed[seq] = (pred, published, s.relationship)
            if key in self.tu_keys:  # listed in the previous refresh too, so a missing stop dropped
                for seq in sorted(st.listed.keys() - listed.keys()):
                    pred, published, rel = st.listed[seq]
                    st.dropped[seq] = feed_ts
                    st.final_pred[seq] = (pred, published)
                    if rel == "SKIPPED":
                        self._mark_skipped(st, seq, feed_ts)
                    elif pred is not None and pred <= feed_ts + DUE_SLACK_SEC:
                        st.n_drops += 1
            st.listed = listed
        for key in sorted(self.tu_keys - trips.keys()):
            st = self.trips.get(key)
            if st is not None and st.vanished_at is None:
                self._on_vanish(st, feed_ts)
        self.tu_keys = set(trips.keys())
        self._sweep()

    def on_reports(self, feed_ts: int, reports: list[Report]) -> None:
        self.now = max(self.now, feed_ts)
        for r in reports:
            self._clean(feed_ts, r)
        for r in reports:
            if r.is_repeat or not r.trip_id or r.lat is None or r.lon is None:
                continue
            start_date = r.start_date or self.trip_dates.get(r.trip_id)
            if not start_date:
                continue
            key = (r.trip_id, start_date)
            if key in self.closed:
                continue
            st = self._state(key, r.route_id, r.direction_id, feed_ts)
            st.last_seen = feed_ts
            if st.first_vp is None:
                st.first_vp = r.report_ts
            st.last_vp = r.report_ts
            prev_key = self.vehicle_trip.get(r.vehicle_id)
            if prev_key is not None and prev_key != key:
                self._switch(prev_key, r)
            self.vehicle_trip[r.vehicle_id] = key
            st.vehicle_id = r.vehicle_id
            geom = self._geom(st)
            if geom is None:
                continue
            fix = self._locate(st, geom, r)
            if fix is not None:
                self._advance(st, geom, fix)
        self._sweep()

    # ------------------------------------------------------------------ reports

    def _clean(self, feed_ts: int, r: Report) -> None:
        r.age = feed_ts - r.report_ts if r.report_ts else None
        last = self.last_report_ts.get(r.vehicle_id)
        r.is_repeat = r.report_ts == last
        if r.report_ts:
            self.last_report_ts[r.vehicle_id] = r.report_ts
        r.in_bbox = (
            r.lat is not None
            and r.lon is not None
            and LAT_MIN <= r.lat <= LAT_MAX
            and LON_MIN <= r.lon <= LON_MAX
        )

    def _locate(self, st: TripState, geom: Geom, r: Report) -> Fix | None:
        d = geom.trip.dists
        k = self._resolve(st, geom, r.stop_id)
        if k is not None:
            if r.status == "STOPPED_AT":
                lo, hi = d[k] - 150.0, d[k] + 150.0
            else:
                lo, hi = (d[k - 1] if k > 0 else d[0] - 200.0) - 50.0, d[k] + 50.0
        else:
            nxt = self._next_listed(st, geom)
            if nxt is not None:
                lo, hi = (d[nxt - 1] if nxt > 0 else d[0] - 200.0) - 50.0, d[nxt] + 50.0
            elif st.fix is not None:
                lo = st.fix.dist - 50.0
                hi = st.fix.dist + 40.0 * max(30, r.report_ts - st.fix.ts)
            else:
                lo, hi = d[0] - 200.0, d[-1] + 100.0
        if st.fix is not None and st.fix.vehicle_id == r.vehicle_id:
            floor = st.fix.dist - 50.0
            if floor > hi:  # the reported stop lags the vehicle's progress: search ahead instead
                lo, hi = floor, st.fix.dist + 40.0 * max(30, r.report_ts - st.fix.ts)
            else:
                lo = max(lo, floor)
        x, y = to_xy(r.lat, r.lon)
        hit = project(geom.shape, x, y, lo, hi)
        if hit is None:
            return None
        r.dist, r.lateral = hit
        r.stop_idx = k
        r.valid = (
            r.age is not None
            and r.age <= STALE_SEC[self.mode]
            and r.in_bbox
            and r.lateral <= LATERAL_MAX_M
            and d[0] - 100.0 <= r.dist <= d[-1] + 100.0
        )
        if not r.valid:
            return None
        return Fix(r.report_ts, r.dist, r.status, k, r.vehicle_id, x, y)

    def _resolve(self, st: TripState, geom: Geom, stop_id: str) -> int | None:
        """First occurrence of the reported stop at or after the vehicle's progress (loops)."""
        sidx = geom.feed.stop_index.get(stop_id) if stop_id else None
        if sidx is None:
            return None
        for i, s in enumerate(geom.trip.stops):
            if s == sidx and i >= st.progress:
                return i
        return None

    def _next_listed(self, st: TripState, geom: Geom) -> int | None:
        idx = [self._idx(st, geom, seq) for seq in st.listed]
        idx = [i for i in idx if i is not None]
        return min(idx) if idx else None

    # ------------------------------------------------------------------ visits

    def _advance(self, st: TripState, geom: Geom, fix: Fix, *, switch: bool = False) -> None:
        prev = st.fix if st.fix is not None and st.fix.vehicle_id == fix.vehicle_id else None
        if prev is not None and fix.ts <= prev.ts:
            return
        st.n_fixes += 1
        tol = self._tol(geom.trip)
        self._track_dwell(st, geom, fix, tol)
        if prev is not None:
            self._origin_departure(st, geom, prev, fix, tol)
            self._near_side_arrival(st, geom, prev, fix, tol, switch)
            self._pole_crossings(st, geom, prev, fix, tol, switch)
        if not switch:
            st.fix = fix
            if fix.stop_idx is not None:
                st.progress = max(st.progress, fix.stop_idx - 1)

    def _track_dwell(self, st: TripState, geom: Geom, fix: Fix, tol: float) -> None:
        """STOPPED_AT at a visited stop extends its dwell; moving past it fixes the departure."""
        d = geom.trip.dists
        for v in st.visits.values():
            if v.left or v.skipped:
                continue
            if _stopped_at(fix, d, v.idx, tol):
                if v.first_stopped is None:
                    v.first_stopped = fix.ts
                v.last_stopped = fix.ts
                v.stopped_observed = True
                v.nearest = _min(v.nearest, self._offset(geom, v.idx, fix))
            elif _past(fix, d, v.idx, tol):
                v.left = True
                if v.last_stopped is not None:
                    v.dep_earliest, v.dep_latest = v.last_stopped, fix.ts

    def _origin_departure(self, st: TripState, geom: Geom, prev: Fix, fix: Fix, tol: float) -> None:
        """The origin has no crossing at distance 0, so its event is the departure."""
        d0 = geom.trip.dists[0]
        if 0 in st.visits or 0 in st.emitted or not prev.dist <= d0 + tol < fix.dist:
            return
        v = self._new_visit(st, geom, 0, prev.ts, fix.ts, (prev.ts + fix.ts) / 2, prev, fix)
        v.left = True
        v.dep_earliest, v.dep_latest = prev.ts, fix.ts

    def _near_side_arrival(
        self, st: TripState, geom: Geom, prev: Fix, fix: Fix, tol: float, switch: bool
    ) -> None:
        """At rest short of the pole: it arrived when it reached that spot; split the gap."""
        k = fix.stop_idx
        if fix.status != "STOPPED_AT" or not k or k in st.visits or k in st.emitted:
            return
        if not (-tol <= fix.dist - geom.trip.dists[k] < 0 and prev.dist < fix.dist):
            return
        v = self._new_visit(st, geom, k, prev.ts, fix.ts, (prev.ts + fix.ts) / 2, prev, fix)
        v.first_stopped = v.last_stopped = fix.ts
        v.stopped_observed = True
        v.switch = switch

    def _pole_crossings(
        self, st: TripState, geom: Geom, prev: Fix, fix: Fix, tol: float, switch: bool
    ) -> None:
        """Interpolate every stop whose distance lies between two bracketing reports."""
        d = geom.trip.dists
        if fix.dist <= prev.dist:
            return
        for j in range(max(1, bisect.bisect_right(d, prev.dist)), bisect.bisect_right(d, fix.dist)):
            if j in st.visits or j in st.emitted:
                continue
            arrival = prev.ts + (d[j] - prev.dist) / (fix.dist - prev.dist) * (fix.ts - prev.ts)
            v = self._new_visit(st, geom, j, prev.ts, fix.ts, arrival, prev, fix)
            v.switch = switch
            if _stopped_at(fix, d, j, tol):
                v.first_stopped = v.last_stopped = fix.ts
                v.stopped_observed = True
            elif _past(fix, d, j, tol):
                v.left = True

    def _new_visit(
        self,
        st: TripState,
        geom: Geom,
        idx: int,
        earliest: int,
        latest: int,
        arrival: float,
        before: Fix | None,
        after: Fix | None,
        method: str | None = None,
    ) -> Visit:
        if method is None:
            if self.mode == "backfill":
                method = "backfill_shape_crossing"
            elif idx == 0:
                method = "origin_departure"
            else:
                method = (
                    "shape_crossing" if latest - earliest <= WITHIN_SEC else "shape_crossing_gap"
                )
        v = Visit(idx, self.now, method, arrival, earliest, latest, before, after)
        for f in (before, after):
            if f is not None:
                v.nearest = _min(v.nearest, self._offset(geom, idx, f))
        listed = st.listed.get(geom.trip.seqs[idx])
        if listed is not None and listed[2] == "SKIPPED":
            _skip(v)
        st.visits[idx] = v
        st.progress = max(st.progress, idx)
        return v

    def _mark_skipped(self, st: TripState, seq: int, feed_ts: int) -> None:
        geom = self._geom(st)
        idx = self._idx(st, geom, seq) if geom is not None else None
        if idx is None or idx in st.emitted:
            return
        v = st.visits.get(idx)
        if v is None:
            v = st.visits[idx] = Visit(idx, feed_ts, "skipped")
        _skip(v)

    def _switch(self, prev_key: tuple[str, str], r: Report) -> None:
        """The vehicle took a new trip: use its first report to close the old trip's terminal."""
        st = self.trips.get(prev_key)
        if st is None:
            return
        geom = self._geom(st)
        if geom is not None and st.fix is not None and st.fix.vehicle_id == r.vehicle_id:
            d = geom.trip.dists
            last = len(d) - 1
            tol = self._tol(geom.trip)
            if (
                last not in st.visits
                and last not in st.emitted
                and r.lat is not None
                and r.lon is not None
                and r.age is not None
                and r.age <= STALE_SEC[self.mode]
            ):
                x, y = to_xy(r.lat, r.lon)
                hit = project(
                    geom.shape, x, y, max(st.fix.dist - 50.0, d[last] - 300.0), d[last] + 100.0
                )
                if hit is not None and hit[1] <= LATERAL_MAX_M and hit[0] >= d[last] - tol:
                    fix = Fix(r.report_ts, hit[0], None, None, r.vehicle_id, x, y)
                    if hit[0] >= d[last]:
                        self._advance(st, geom, fix, switch=True)
                    elif fix.ts > st.fix.ts:
                        mid = (st.fix.ts + fix.ts) / 2
                        v = self._new_visit(st, geom, last, st.fix.ts, fix.ts, mid, st.fix, fix)
                        v.switch = True
        for v in st.visits.values():
            v.left = True

    # ------------------------------------------------------------------ lifecycle

    def _on_vanish(self, st: TripState, feed_ts: int) -> None:
        st.vanished_at = feed_ts
        geom = self._geom(st)
        if geom is None or len(st.listed) != 1:
            return  # many stops left at once: no visits for them unless a vehicle crosses them
        (seq,) = st.listed
        pred, published, _ = st.listed[seq]
        if seq == geom.trip.seqs[-1] and pred is not None and pred <= feed_ts + DUE_SLACK_SEC:
            st.dropped[seq] = feed_ts
            st.final_pred[seq] = (pred, published)

    def _sweep(self, force: bool = False) -> None:
        for key in list(self.trips):
            st = self.trips[key]
            geom = self._geom(st)
            closing = force or self.now - st.last_seen >= TRIP_CLOSE_SEC[self.mode]
            if geom is not None:
                self._resolve_predictions(st, geom, closing)
                self._finalize(st, geom, closing)
            if closing:
                self._close(key, st, geom)
        for key, ts in list(self.closed.items()):
            if self.now - ts > TOMBSTONE_SEC:
                del self.closed[key]

    def flush(self) -> None:
        """Close every open trip (end of a replay or backfill input)."""
        self._sweep(force=True)

    def _resolve_predictions(self, st: TripState, geom: Geom, closing: bool) -> None:
        ran = st.n_fixes > 0 or st.n_drops >= 2
        if not ran:
            return  # phantom guard: a trip never shown to run gets no prediction-based visits
        d = geom.trip.dists
        tol = self._tol(geom.trip)
        grace = FINAL_GRACE_SEC[self.mode]
        for seq, drop_ts in sorted(st.dropped.items()):
            idx = self._idx(st, geom, seq)
            if idx is None or idx in st.visits or idx in st.emitted:
                continue
            pred, published = st.final_pred.get(seq, (None, None))
            if pred is None or pred > drop_ts + DUE_SLACK_SEC:
                continue  # dropped before it was due: not evidence that the stop was served
            # A vehicle past the stop with no bracketing pair (its first fix was beyond it) settles
            # it now; otherwise wait out the grace so a late vehicle's crossing takes precedence.
            passed = st.fix is not None and st.fix.dist > d[idx] + tol
            if not (passed or closing or self.now - drop_ts >= grace):
                continue
            earliest = min(published, pred - PRED_GUARD_SEC)
            arrival = min(max(pred, earliest), drop_ts)
            method = "backfill_prediction" if self.mode == "backfill" else "last_prediction"
            v = self._new_visit(st, geom, idx, earliest, drop_ts, arrival, None, None, method)
            v.left = True

    def _finalize(self, st: TripState, geom: Geom, closing: bool) -> None:
        grace = FINAL_GRACE_SEC[self.mode]
        for idx in sorted(st.visits):
            v = st.visits[idx]
            if not (v.skipped or v.arrival is not None):
                continue
            if not closing:
                seq = geom.trip.seqs[idx]
                gone = seq in st.dropped or seq not in st.listed or st.vanished_at is not None
                if not gone or not (v.left or v.skipped or self.now - v.created >= grace):
                    continue
            self._emit(st, geom, v)
        for idx in st.emitted:
            st.visits.pop(idx, None)

    def _emit(self, st: TripState, geom: Geom, v: Visit) -> None:
        trip, d = geom.trip, geom.trip.dists
        seq = trip.seqs[v.idx]
        sidx = trip.stops[v.idx]
        last = len(d) - 1
        pred = st.final_pred.get(seq) or (st.listed[seq][:2] if seq in st.listed else (None, None))
        vehicle = (v.after or v.before).vehicle_id if (v.after or v.before) else st.vehicle_id
        window = None if v.earliest is None or v.latest is None else v.latest - v.earliest
        self.visit_rows.append(
            (
                service_date(st.start_date),
                st.trip_id,
                st.start_date,
                seq,
                geom.feed.stop_ids[sidx] if sidx >= 0 else None,
                "first" if v.idx == 0 else "last" if v.idx == last else "middle",
                trip.route_id,
                trip.direction_id,
                trip.headsign or None,
                vehicle,
                v.method,
                None if v.skipped else iso(v.arrival),
                None if v.skipped else iso(v.earliest),
                None if v.skipped else iso(v.latest),
                iso(v.dep_earliest),
                iso(v.dep_latest),
                _diff(v.last_stopped, v.first_stopped),
                _diff(v.dep_latest, v.first_stopped),
                v.skipped,
                v.stopped_observed,
                iso(v.before.ts) if v.before else None,
                round(v.before.dist, 1) if v.before else None,
                iso(v.after.ts) if v.after else None,
                round(v.after.dist, 1) if v.after else None,
                round(d[v.idx], 1),
                None if v.nearest is None else round(v.nearest, 1),
                iso(pred[0]),
                iso(pred[1]),
                v.switch,
                window is not None and window > LOW_CONFIDENCE_SEC,
                True,
                self.data_version,
                st.md5,
                iso(self.now),
            )
        )
        st.emitted.add(v.idx)
        family = (
            "skipped" if v.skipped else "prediction" if "prediction" in v.method else "crossing"
        )
        st.methods[family] = st.methods.get(family, 0) + 1
        if not v.skipped and v.idx == last:
            st.methods["terminal"] = 1

    def _close(self, key: tuple[str, str], st: TripState, geom: Geom | None) -> None:
        n_visits = st.methods.get("crossing", 0) + st.methods.get("prediction", 0)
        if geom is None:
            outcome = "no_static"
        elif st.relationship == "CANCELED" and n_visits == 0:
            outcome = "canceled"
        elif st.methods.get("terminal"):
            outcome = "completed"
        elif n_visits:
            outcome = "partial"
        else:
            outcome = "vanished"
        self.status_rows.append(
            (
                service_date(st.start_date),
                st.trip_id,
                st.start_date,
                geom.trip.route_id if geom else (st.route_id or None),
                geom.trip.direction_id if geom else st.direction_id,
                st.relationship,
                outcome,
                iso(st.first_seen),
                iso(st.last_seen),
                iso(st.first_vp),
                iso(st.last_vp),
                st.n_fixes > 0 or st.first_vp is not None,
                len(geom.trip.seqs) if geom else None,
                n_visits,
                st.methods.get("crossing", 0),
                st.methods.get("prediction", 0),
                st.methods.get("skipped", 0),
                self.data_version,
                st.md5,
                iso(self.now),
            )
        )
        del self.trips[key]
        self.closed[key] = self.now
        if self.trip_dates.get(key[0]) == key[1]:
            del self.trip_dates[key[0]]
        for vehicle in [v for v, k in self.vehicle_trip.items() if k == key]:
            del self.vehicle_trip[vehicle]

    # ------------------------------------------------------------------ helpers

    def _state(
        self, key: tuple[str, str], route_id: str, direction_id: int | None, feed_ts: int
    ) -> TripState:
        st = self.trips.get(key)
        if st is None:
            st = TripState(key[0], key[1], None, route_id, direction_id)
            st.first_seen = st.last_seen = feed_ts
            geom = self.lookup(key[0], None, key[1]) if self.lookup else None
            if geom is not None:
                st.md5 = geom.feed.md5
            self.trips[key] = st
        return st

    def _geom(self, st: TripState) -> Geom | None:
        if st.md5 is None or self.lookup is None:
            return None
        return self.lookup(st.trip_id, st.md5, st.start_date)

    def _idx(self, st: TripState, geom: Geom, seq: int) -> int | None:
        if not st.seq_idx:
            st.seq_idx = {s: i for i, s in enumerate(geom.trip.seqs)}
        return st.seq_idx.get(seq)

    @staticmethod
    def _tol(trip: Trip) -> float:
        return TOL_RAIL_M if trip.is_rail else TOL_BUS_M

    @staticmethod
    def _offset(geom: Geom, idx: int, fix: Fix) -> float | None:
        sidx = geom.trip.stops[idx]
        if sidx < 0:
            return None
        return math.hypot(fix.x - geom.feed.stop_xs[sidx], fix.y - geom.feed.stop_ys[sidx])


def _stopped_at(fix: Fix, d, idx: int, tol: float) -> bool:
    return fix.status == "STOPPED_AT" and fix.stop_idx == idx and abs(fix.dist - d[idx]) <= tol


def _past(fix: Fix, d, idx: int, tol: float) -> bool:
    return fix.dist > d[idx] + tol or (fix.stop_idx is not None and fix.stop_idx > idx)


def _skip(v: Visit) -> None:
    v.skipped = True
    v.method = "skipped"
    v.arrival = v.earliest = v.latest = None
    v.left = True


def _min(a: float | None, b: float | None) -> float | None:
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


def _diff(a: int | None, b: int | None) -> int | None:
    return None if a is None or b is None else a - b
