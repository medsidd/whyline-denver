"""Static GTFS geometry for the realtime stream engine: compact stop distances and shapes."""

from __future__ import annotations

import bisect
import csv
import hashlib
import io
import math
import zipfile
from array import array
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

# Equirectangular metres around Denver; scale error stays under 1% across the RTD bbox,
# and along-route distances come from shape_dist_traveled, not from these coordinates.
LAT0 = 39.74
LON0 = -104.99
_KX = 111_320.0 * math.cos(math.radians(LAT0))
_KY = 110_950.0
RAIL_ROUTE_TYPES = frozenset({"0", "1", "2"})


def to_xy(lat: float, lon: float) -> tuple[float, float]:
    return (lon - LON0) * _KX, (lat - LAT0) * _KY


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin((p2 - p1) / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * 6_371_008.8 * math.asin(math.sqrt(a))


@dataclass(slots=True)
class Shape:
    xs: array
    ys: array
    ds: array  # metres along the shape, non-decreasing


@dataclass(slots=True)
class Trip:
    route_id: str
    route_type: str
    direction_id: int | None
    shape_id: str
    headsign: str
    seqs: array  # stop_sequence, ascending
    stops: array  # index into StaticFeed.stop_ids (-1 when the stop is unknown)
    dists: array  # metres along the shape, per stop

    @property
    def is_rail(self) -> bool:
        return self.route_type in RAIL_ROUTE_TYPES


@dataclass
class StaticFeed:
    md5: str
    feed_version: str | None
    stop_ids: list[str]
    stop_xs: array
    stop_ys: array
    stop_index: dict[str, int]
    trips: dict[str, Trip]
    shapes: dict[str, Shape]

    def shape_for(self, trip: Trip) -> Shape | None:
        return self.shapes.get(trip.shape_id)


def project(shape: Shape, x: float, y: float, lo: float, hi: float) -> tuple[float, float] | None:
    """Nearest point on the shape between along-route distances lo and hi: (dist, lateral metres)."""
    xs, ys, ds = shape.xs, shape.ys, shape.ds
    n = len(ds)
    if n < 2 or hi < lo:
        return None
    best_d2 = math.inf
    best_dist = None
    for i in range(
        max(0, bisect.bisect_right(ds, lo) - 1), min(n - 1, bisect.bisect_right(ds, hi))
    ):
        d0, d1 = ds[i], ds[i + 1]
        if d1 < lo or d0 > hi:
            continue
        ax, ay = xs[i], ys[i]
        dx, dy = xs[i + 1] - ax, ys[i + 1] - ay
        seg2 = dx * dx + dy * dy
        t = 0.0 if seg2 == 0 else ((x - ax) * dx + (y - ay) * dy) / seg2
        span = d1 - d0
        # Only the part of the segment inside [lo, hi] may be matched.
        t_lo = (lo - d0) / span if span > 0 and lo > d0 else 0.0
        t_hi = (hi - d0) / span if span > 0 and hi < d1 else 1.0
        t = max(t_lo, min(t_hi, t))
        d2 = (x - ax - t * dx) ** 2 + (y - ay - t * dy) ** 2
        if d2 < best_d2:
            best_d2 = d2
            best_dist = d0 + t * span
    if best_dist is None:
        return None
    return best_dist, math.sqrt(best_d2)


def load_zip(payload: bytes) -> StaticFeed:
    """Build geometry from an RTD google_transit.zip payload."""
    md5 = hashlib.md5(payload, usedforsecurity=False).hexdigest()
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = set(archive.namelist())

        def open_text(name: str) -> TextIO | None:
            if name not in names:
                return None
            return io.TextIOWrapper(archive.open(name), encoding="utf-8-sig")

        return build(md5, open_text)


def load_dir(path: str | Path, md5: str) -> StaticFeed:
    """Build geometry from extracted GTFS text files (backfill exports)."""
    root = Path(path)

    def open_text(name: str) -> TextIO | None:
        file = root / name
        return file.open(encoding="utf-8-sig", newline="") if file.exists() else None

    return build(md5, open_text)


def _table(open_text: Callable[[str], TextIO | None], name: str, *cols: str) -> Iterator[tuple]:
    """Yield the requested columns of a GTFS file as tuples ('' when a column is absent)."""
    handle = open_text(name)
    if handle is None:
        return
    with handle:
        reader = csv.reader(handle)
        header = [h.strip() for h in next(reader, [])]
        pos = [header.index(c) if c in header else None for c in cols]
        for row in reader:
            yield tuple(row[p] if p is not None and p < len(row) else "" for p in pos)


def build(md5: str, open_text: Callable[[str], TextIO | None]) -> StaticFeed:
    feed_version = next(
        (v for (v,) in _table(open_text, "feed_info.txt", "feed_version") if v), None
    )
    route_types = dict(_table(open_text, "routes.txt", "route_id", "route_type"))

    stop_ids: list[str] = []
    stop_index: dict[str, int] = {}
    stop_xs, stop_ys = array("d"), array("d")
    for sid, lat, lon in _table(open_text, "stops.txt", "stop_id", "stop_lat", "stop_lon"):
        try:
            x, y = to_xy(float(lat), float(lon))
        except ValueError:
            continue
        stop_index[sid] = len(stop_ids)
        stop_ids.append(sid)
        stop_xs.append(x)
        stop_ys.append(y)

    # Rows are appended straight into per-shape and per-trip arrays to keep peak memory low.
    shape_acc: dict[str, tuple[array, array, array, array]] = {}
    for sid, lat, lon, seq, dist in _table(
        open_text,
        "shapes.txt",
        "shape_id",
        "shape_pt_lat",
        "shape_pt_lon",
        "shape_pt_sequence",
        "shape_dist_traveled",
    ):
        acc = shape_acc.get(sid)
        if acc is None:
            acc = shape_acc[sid] = (array("i"), array("d"), array("d"), array("d"))
        acc[0].append(int(seq))
        acc[1].append(float(lat))
        acc[2].append(float(lon))
        acc[3].append(float(dist) if dist else math.nan)
    shapes = {sid: _finish_shape(*acc) for sid, acc in shape_acc.items()}
    del shape_acc

    stop_acc: dict[str, tuple[array, array, array]] = {}
    for tid, seq, sid, dist in _table(
        open_text, "stop_times.txt", "trip_id", "stop_sequence", "stop_id", "shape_dist_traveled"
    ):
        acc = stop_acc.get(tid)
        if acc is None:
            acc = stop_acc[tid] = (array("i"), array("i"), array("d"))
        acc[0].append(int(seq))
        acc[1].append(stop_index.get(sid, -1))
        acc[2].append(float(dist) if dist else math.nan)

    trips: dict[str, Trip] = {}
    for tid, rid, did, shape_id, headsign in _table(
        open_text, "trips.txt", "trip_id", "route_id", "direction_id", "shape_id", "trip_headsign"
    ):
        acc = stop_acc.pop(tid, None)
        shape = shapes.get(shape_id)
        if acc is None or shape is None:
            continue
        seqs, stops, dists = _sorted_by_seq(*acc)
        if any(math.isnan(d) for d in dists):
            dists = _project_stops(shape, stops, stop_xs, stop_ys)
        trips[tid] = Trip(
            route_id=rid,
            route_type=route_types.get(rid, ""),
            direction_id=int(did) if did in ("0", "1") else None,
            shape_id=shape_id,
            headsign=headsign,
            seqs=seqs,
            stops=stops,
            dists=dists,
        )
    return StaticFeed(md5, feed_version, stop_ids, stop_xs, stop_ys, stop_index, trips, shapes)


def _finish_shape(seq: array, lat: array, lon: array, dist: array) -> Shape:
    order = sorted(range(len(seq)), key=seq.__getitem__)
    xs, ys, ds = array("d"), array("d"), array("d")
    missing = any(math.isnan(d) for d in dist)
    run = 0.0
    prev = None
    for i in order:
        x, y = to_xy(lat[i], lon[i])
        if missing:  # feeds without shape_dist_traveled (late 2025): cumulative geodesic metres
            if prev is not None:
                run += haversine_m(lat[prev], lon[prev], lat[i], lon[i])
            ds.append(run)
        else:
            ds.append(dist[i])
        xs.append(x)
        ys.append(y)
        prev = i
    return Shape(xs, ys, ds)


def _sorted_by_seq(seqs: array, stops: array, dists: array) -> tuple[array, array, array]:
    if all(seqs[i] < seqs[i + 1] for i in range(len(seqs) - 1)):
        return seqs, stops, dists
    order = sorted(range(len(seqs)), key=seqs.__getitem__)
    return (
        array("i", (seqs[i] for i in order)),
        array("i", (stops[i] for i in order)),
        array("d", (dists[i] for i in order)),
    )


def _project_stops(shape: Shape, stops: array, stop_xs: array, stop_ys: array) -> array:
    """Stop distances for feeds without shape_dist_traveled: project in order, never backwards."""
    out = array("d")
    floor = 0.0
    end = shape.ds[-1]
    for idx in stops:
        if idx < 0:
            out.append(floor)
            continue
        x, y = stop_xs[idx], stop_ys[idx]
        # Search a few km ahead first so a loop's later pass cannot capture an earlier stop.
        hit = project(shape, x, y, floor, min(end, floor + 3000.0))
        if hit is None or hit[1] > 200.0:
            hit = project(shape, x, y, floor, end) or (floor, 0.0)
        floor = hit[0]
        out.append(floor)
    return out
