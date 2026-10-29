"""CLI: approximate stop visits from the old 15-minute snapshots (2025-10-23 to stream start).

Reads the Parquet export written by dbt/analyses/backfill_export.sql (old raw trip updates and
vehicle positions, one directory per UTC day, plus the static GTFS extract valid on each service
date) and runs the stream engine in backfill mode: methods backfill_shape_crossing and
backfill_prediction, about 900 s windows, low_confidence past 20-minute gaps, and the same
phantom-visit and cancellation rules. Writes one loadable batch per UTC day under
<out>/snapshot_at=YYYY-MM-DDT00:00/ for gs://<bucket>/raw/rtd_gtfsrt_backfill/.
"""

from __future__ import annotations

import argparse
import shutil
from collections import defaultdict
from collections.abc import Iterator, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pyarrow.compute as pc
import pyarrow.parquet as pq

from whyline.ingest import io, rt_static
from whyline.ingest.gtfs_rt_stream import Window
from whyline.ingest.rt_engine import Geom, Report, StopUpdate, TripListing, VisitEngine

LOGGER = io.get_logger(__name__)
DAY_SEC = 86_400
# GTFS file the static builder asks for -> (export directory, raw table named in version_files)
STATIC_FILES = {
    "stops.txt": ("stops", "raw_gtfs_stops"),
    "routes.txt": ("routes", "raw_gtfs_routes"),
    "trips.txt": ("trips", "raw_gtfs_trips"),
    "stop_times.txt": ("stop_times", "raw_gtfs_stop_times"),
    "shapes.txt": ("shapes", "raw_gtfs_shapes"),
}
FEEDS_KEPT = 3


def _read(export: str, sub: str):
    return pq.read_table(f"{export.rstrip('/')}/{sub}")


def _epoch(value: datetime | None) -> int | None:
    return int(value.replace(tzinfo=value.tzinfo or UTC).timestamp()) if value else None


class StaticVersions:
    """Static GTFS per service date, built lazily from the exported extracts."""

    def __init__(self, export: str):
        self.service = {
            r["service_date"]: r["static_version"]
            for r in _read(export, "service_static").to_pylist()
        }
        self.files = {
            (r["static_version"], r["tbl"]): r["file_extract"]
            for r in _read(export, "version_files").to_pylist()
        }
        self.tables = {name: _read(export, f"static/{name}") for name, _ in STATIC_FILES.values()}
        self.feeds: dict[str, rt_static.StaticFeed] = {}

    def _rows(self, version: date, name: str, cols: tuple[str, ...]) -> Iterator[tuple]:
        if name not in STATIC_FILES:
            return
        export_name, table = STATIC_FILES[name]
        extract = self.files.get((version, table))
        if extract is None:
            return
        rows = self.tables[export_name]
        rows = rows.filter(pc.equal(rows["_extract_date"], extract))
        present = [c for c in cols if c in rows.column_names]
        for row in rows.select(present).to_pylist():
            yield tuple("" if row.get(c) is None else str(row[c]) for c in cols)

    def feed(self, version: date) -> rt_static.StaticFeed:
        key = version.isoformat()
        if key not in self.feeds:
            while len(self.feeds) >= FEEDS_KEPT:
                del self.feeds[next(iter(self.feeds))]
            self.feeds[key] = rt_static.build(
                key, lambda name, *cols: self._rows(version, name, cols)
            )
            LOGGER.info("Built static version %s (%d trips)", key, len(self.feeds[key].trips))
        return self.feeds[key]

    def lookup(self, trip_id: str, md5: str | None, start_date: str = "") -> Geom | None:
        if md5:
            feed = self.feed(date.fromisoformat(md5))
        else:
            try:
                version = self.service.get(datetime.strptime(start_date, "%Y%m%d").date())
            except ValueError:
                return None
            if version is None:
                return None
            feed = self.feed(version)
        trip = feed.trips.get(trip_id)
        return Geom(trip, feed.shapes[trip.shape_id], feed) if trip else None


def snapshots(export: str, day: date) -> list[tuple[int, dict, list[Report]]]:
    """One day's old snapshots as (feed_ts, trip listings, vehicle reports), in time order."""
    listings: dict[int, dict] = defaultdict(dict)
    reports: dict[int, list[Report]] = defaultdict(list)
    for name in ("tu", "vp"):
        try:
            table = _read(export, f"{name}/date={day.isoformat()}")
        except (FileNotFoundError, OSError):
            continue
        for row in table.to_pylist():
            feed_ts = _epoch(row["feed_ts_utc"])
            if name == "tu":
                if not row["trip_id"] or row["stop_sequence"] is None or not row["start_date"]:
                    continue
                key = (row["trip_id"], row["start_date"])
                listing = listings[feed_ts].get(key)
                if listing is None:
                    listing = listings[feed_ts][key] = TripListing(
                        key[0],
                        key[1],
                        row["route_id"] or "",
                        None,
                        row["schedule_relationship"] or "SCHEDULED",
                        None,
                        None,
                        {},
                    )
                # Old rows hold the predicted time in event_ts_utc and the trip's relationship.
                listing.stops[int(row["stop_sequence"])] = StopUpdate(
                    row["stop_id"] or "", _epoch(row["event_ts_utc"]), None, None, None, "SCHEDULED"
                )
            elif row["event_ts_utc"] and row["lat"] is not None:
                reports[feed_ts].append(
                    Report(
                        _epoch(row["event_ts_utc"]),
                        "",
                        row["vehicle_id"] or "",
                        "",
                        row["trip_id"] or "",
                        "",
                        row["route_id"] or "",
                        None,
                        None,
                        "",
                        None,
                        row["lat"],
                        row["lon"],
                        None,
                        None,
                        None,
                    )
                )
    return [
        (ts, listings.get(ts, {}), reports.get(ts, []))
        for ts in sorted(listings.keys() | reports.keys())
    ]


def run(args: argparse.Namespace) -> int:
    start, until = date.fromisoformat(args.start_date), date.fromisoformat(args.end_date)
    versions = StaticVersions(args.export)
    engine = VisitEngine(versions.lookup, mode="backfill", data_version="backfill_v1")
    out = Path(args.out)
    work = out / ".work"
    if (work / "open").exists():
        shutil.rmtree(work / "open")
    meta = {"raw_root": args.raw_root, "source": {"backfill_export": args.export}}
    day = start
    while day <= until:
        window = Window(
            work, int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp()), DAY_SEC
        )
        taken = snapshots(args.export, day)
        for feed_ts, listings, reports in taken:
            if listings:
                engine.on_trip_updates(feed_ts, listings)
            if reports:
                engine.on_reports(feed_ts, reports)
            visits, status = engine.drain()
            window.write("stop_visits", visits)
            window.write("trip_status", status)
        if day == until:
            engine.flush()
            visits, status = engine.drain()
            window.write("stop_visits", visits)
            window.write("trip_status", status)
        window.stats["snapshots"] = len(taken)
        if window.rows["stop_visits"] or window.rows["trip_status"]:
            window.seal(out, meta, f"snapshot_at={window.label}")
        else:
            shutil.rmtree(window.dir)
        LOGGER.info("Backfilled %s: %d snapshots, %s", day, len(taken), window.rows)
        day += timedelta(days=1)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill stop visits from 15-minute snapshots.")
    parser.add_argument("--export", required=True, help="Export root (local dir or gs://).")
    parser.add_argument(
        "--from", dest="start_date", required=True, help="First UTC day (YYYY-MM-DD)."
    )
    parser.add_argument(
        "--until", dest="end_date", required=True, help="Last UTC day (YYYY-MM-DD)."
    )
    parser.add_argument("--out", default="data/backfill", help="Output root for daily batches.")
    parser.add_argument(
        "--raw-root",
        default="gs://whylinedenver-raw/raw/rtd_gtfsrt_backfill",
        help="Where the batches will be copied (recorded in each manifest).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
