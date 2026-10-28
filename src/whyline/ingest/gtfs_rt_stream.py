"""CLI: continuous RTD GTFS-RT capture.

Polls both feeds every 15 seconds, archives every refresh, and emits trip-update changes,
vehicle reports, stop visits and trip status as one batch per 15-minute window.
Live output goes to data/raw (local) or gs://<bucket>/raw (GCS) under rtd_gtfsrt_stream/;
the exact payloads go to a tar per window in the archive bucket. --replay rebuilds the same
outputs from archived tars with the same engine.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import pickle
import resource
import shutil
import signal
import sys
import tarfile
import time
from collections import Counter
from collections.abc import Iterator, Sequence
from datetime import UTC, date, datetime
from io import BytesIO
from pathlib import Path

import requests

from whyline.ingest import io, rt_static
from whyline.ingest.gtfs_realtime import DEFAULT_TRIP_UPDATES_URL, DEFAULT_VEHICLE_POSITIONS_URL
from whyline.ingest.gtfs_static import DEFAULT_GTFS_URL
from whyline.ingest.rt_engine import (
    TRIP_STATUS_COLUMNS,
    TU_CHANGE_COLUMNS,
    VISIT_COLUMNS,
    VP_COLUMNS,
    Geom,
    TripUpdateDiff,
    VisitEngine,
    iso,
    parse_trip_updates,
    parse_vehicle_positions,
    vp_row,
)

LOGGER = io.get_logger(__name__)

WINDOW_SEC = 900
STREAM_PREFIX = "rtd_gtfsrt_stream"
REPLAY_PREFIX = "rtd_gtfsrt_replay"
ARCHIVE_PREFIX = "rtd_gtfsrt"
STATIC_PREFIX = "static/rtd_gtfs"
OUTPUTS = {
    "tu_changes": TU_CHANGE_COLUMNS,
    "vp_reports": VP_COLUMNS,
    "stop_visits": VISIT_COLUMNS,
    "trip_status": TRIP_STATUS_COLUMNS,
}
STATIC_KEEP_SEC = 36 * 3600
HEARTBEAT_SEC = 300
OUTBOX_ALERT_WINDOWS = 50
OUTBOX_ALERT_BYTES = 1 << 30


def window_start(ts: float) -> int:
    return int(ts // WINDOW_SEC * WINDOW_SEC)


def window_label(start: int) -> str:
    return datetime.fromtimestamp(start, tz=UTC).strftime("%Y-%m-%dT%H:%M")


def peak_rss_mb() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(peak / (1 << 20) if sys.platform == "darwin" else peak / 1024, 1)


def _md5(data: bytes) -> str:
    return hashlib.md5(data, usedforsecurity=False).hexdigest()


def _cell(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


# --------------------------------------------------------------------------- window


class Window:
    """One open 15-minute batch on local disk: append-only CSVs and a tar of gzipped payloads."""

    def __init__(self, root: Path, start: int):
        self.start = start
        self.label = window_label(start)
        self.dir = root / "open" / self.label
        self.dir.mkdir(parents=True, exist_ok=True)
        self.rows = dict.fromkeys(OUTPUTS, 0)
        self.stats: Counter[str] = Counter()
        for name, cols in OUTPUTS.items():
            path = self._csv(name)
            if not path.exists() or path.stat().st_size == 0:
                with path.open("w", newline="") as handle:
                    csv.writer(handle).writerow(cols)

    def _csv(self, name: str) -> Path:
        return self.dir / f"{name}.csv"

    @property
    def tar_path(self) -> Path:
        return self.dir / "archive.tar"

    def write(self, name: str, rows: list[tuple]) -> None:
        if not rows:
            return
        with self._csv(name).open("a", newline="") as handle:
            writer = csv.writer(handle)
            for row in rows:
                writer.writerow([_cell(v) for v in row])
        self.rows[name] += len(rows)

    def archive(self, kind: str, header_ts: int, payload: bytes) -> None:
        data = gzip.compress(payload, mtime=0)
        info = tarfile.TarInfo(f"{kind}/{header_ts}.pb.gz")
        info.size = len(data)
        info.mtime = header_ts
        with self.tar_path.open("ab") as handle:
            handle.write(info.tobuf(format=tarfile.USTAR_FORMAT))
            handle.write(data)
            handle.write(b"\0" * (-len(data) % tarfile.BLOCKSIZE))

    def files(self) -> list[Path]:
        return [self._csv(name) for name in OUTPUTS] + [self.tar_path]

    def sync(self) -> dict[str, int]:
        """fsync the window files and return their sizes for the checkpoint."""
        sizes = {}
        for path in self.files():
            if path.exists():
                with path.open("rb+") as handle:
                    os.fsync(handle.fileno())
                sizes[path.name] = path.stat().st_size
        return sizes

    def truncate(self, sizes: dict[str, int]) -> None:
        for path in self.files():
            if path.exists():
                keep = sizes.get(path.name, 0)
                if path.stat().st_size > keep:
                    with path.open("rb+") as handle:
                        handle.truncate(keep)

    def seal(self, dest: Path, meta: dict) -> Path:
        """Gzip the CSVs, close the tar, write the manifest, and move the batch into dest."""
        out = dest / self.label
        out.mkdir(parents=True)  # never overwrite a sealed batch that may not be published yet
        files_meta = {}
        for name in OUTPUTS:
            payload = gzip.compress(self._csv(name).read_bytes(), mtime=0)
            (out / f"{name}.csv.gz").write_bytes(payload)
            files_meta[f"{name}.csv.gz"] = {
                "path": f"{meta['raw_root']}/snapshot_at={self.label}/{name}.csv.gz",
                "row_count": self.rows[name],
                "bytes": len(payload),
                "hash_md5": _md5(payload),
                "status": "ok",
                "error": None,
            }
        tar_meta = json.dumps(
            {"window_start_utc": iso(self.start), "static_md5": meta.get("static_md5")},
            sort_keys=True,
        ).encode()
        info = tarfile.TarInfo("meta.json")
        info.size = len(tar_meta)
        info.mtime = self.start
        with self.tar_path.open("ab") as handle:
            handle.write(info.tobuf(format=tarfile.USTAR_FORMAT))
            handle.write(tar_meta + b"\0" * (-len(tar_meta) % tarfile.BLOCKSIZE))
            handle.write(b"\0" * (2 * tarfile.BLOCKSIZE))  # end-of-archive marker
        shutil.move(str(self.tar_path), out / "archive.tar")
        manifest = {
            "source": meta["source"],
            "extract_date": self.label[:10],
            "written_at_utc": io.utc_now_iso(),
            "snapshot_label": self.label,
            "window_start_utc": iso(self.start),
            "window_end_utc": iso(self.start + WINDOW_SEC),
            "file_count": len(files_meta),
            "row_count": sum(f["row_count"] for f in files_meta.values()),
            "bytes": sum(f["bytes"] for f in files_meta.values()),
            "hash_md5": _md5("".join(f["hash_md5"] for f in files_meta.values()).encode()),
            "schema_version": "stream_v1",
            "files": files_meta,
            "stats": dict(sorted(self.stats.items())),
            "static": {"md5": meta.get("static_md5"), "feed_version": meta.get("feed_version")},
            "config": meta.get("config", {}),
        }
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
        shutil.rmtree(self.dir)
        return out


# --------------------------------------------------------------------------- sinks


class LocalSink:
    def __init__(self, root: Path):
        self.root = root
        self.raw_root = str(root / "raw" / STREAM_PREFIX)

    def publish(self, batch: Path) -> None:
        label = batch.name
        target = self.root / "raw" / STREAM_PREFIX / f"snapshot_at={label}"
        target.mkdir(parents=True, exist_ok=True)
        for name in OUTPUTS:
            shutil.copy2(batch / f"{name}.csv.gz", target / f"{name}.csv.gz")
        shutil.copy2(batch / "manifest.json", target / "manifest.json")
        archive = self.root / "archive" / ARCHIVE_PREFIX / f"date={label[:10]}"
        archive.mkdir(parents=True, exist_ok=True)
        shutil.copy2(batch / "archive.tar", archive / f"{label[11:13]}{label[14:16]}.tar")

    def put_static(self, md5: str, payload: bytes) -> None:
        path = self.root / "archive" / STATIC_PREFIX / f"{md5}.zip"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)


class GcsSink:
    def __init__(self, bucket: str, archive_bucket: str):
        self.bucket = bucket
        self.archive_bucket = archive_bucket
        self.raw_root = f"gs://{bucket}/raw/{STREAM_PREFIX}"

    def _put(self, bucket: str, path: str, data: bytes, content_type: str) -> None:
        from google.api_core.exceptions import PreconditionFailed

        try:
            io.upload_bytes_gcs(bucket, path, data, content_type, if_generation_match=0)
        except PreconditionFailed:
            # Create-only: the object exists, so an earlier attempt already uploaded this batch.
            LOGGER.info("Already uploaded gs://%s/%s", bucket, path)

    def publish(self, batch: Path) -> None:
        label = batch.name
        prefix = f"raw/{STREAM_PREFIX}/snapshot_at={label}"
        for name in OUTPUTS:
            data = (batch / f"{name}.csv.gz").read_bytes()
            self._put(self.bucket, f"{prefix}/{name}.csv.gz", data, "application/gzip")
        self._put(
            self.bucket,
            f"{prefix}/manifest.json",
            (batch / "manifest.json").read_bytes(),
            "application/json",
        )
        archive_path = f"{ARCHIVE_PREFIX}/date={label[:10]}/{label[11:13]}{label[14:16]}.tar"
        self._put(
            self.archive_bucket,
            archive_path,
            (batch / "archive.tar").read_bytes(),
            "application/x-tar",
        )

    def put_static(self, md5: str, payload: bytes) -> None:
        self._put(self.archive_bucket, f"{STATIC_PREFIX}/{md5}.zip", payload, "application/zip")


# --------------------------------------------------------------------------- static cache


class StaticCache:
    """Loaded static feeds by MD5; trips keep the version they started on for 36 hours."""

    def __init__(self, cache_dir: Path):
        self.dir = cache_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.feeds: dict[str, tuple[rt_static.StaticFeed, float]] = {}
        self.current: str | None = None

    def add(self, payload: bytes, now: float) -> tuple[str, bool]:
        md5 = _md5(payload)
        if md5 not in self.feeds:
            started = time.time()
            self.feeds[md5] = (rt_static.load_zip(payload), now)
            (self.dir / f"{md5}.zip").write_bytes(payload)
            LOGGER.info(
                "Loaded static %s (%s) in %.1fs",
                md5,
                self.feeds[md5][0].feed_version,
                time.time() - started,
            )
            changed = True
        else:
            changed = False
        self.current = md5
        for old, (_, loaded) in list(self.feeds.items()):
            if old != md5 and now - loaded > STATIC_KEEP_SEC:
                del self.feeds[old]
        return md5, changed

    def load_cached(self, md5: str | None = None) -> bool:
        paths = (
            [self.dir / f"{md5}.zip"]
            if md5
            else sorted(self.dir.glob("*.zip"), key=lambda p: p.stat().st_mtime)
        )
        for path in reversed(paths):
            if path.exists():
                self.add(path.read_bytes(), time.time())
                return True
        return False

    def lookup(self, trip_id: str, md5: str | None) -> Geom | None:
        for key in (md5, self.current):
            entry = self.feeds.get(key) if key else None
            if entry is None:
                continue
            feed = entry[0]
            trip = feed.trips.get(trip_id)
            if trip is not None:
                return Geom(trip, feed.shapes[trip.shape_id], feed)
        return None

    @property
    def feed_version(self) -> str | None:
        entry = self.feeds.get(self.current) if self.current else None
        return entry[0].feed_version if entry else None


# --------------------------------------------------------------------------- processing


class Processor:
    """Diff + engine + per-window bookkeeping shared by the live loop and replays."""

    def __init__(self, engine: VisitEngine, diff: TripUpdateDiff):
        self.engine = engine
        self.diff = diff
        self.last_header: dict[str, int] = {}

    def handle(
        self, kind: str, payload: bytes, window: Window, *, strip_vp_stops=False
    ) -> int | None:
        stats = window.stats
        if kind == "tu":
            header_ts, trips = parse_trip_updates(payload)
        else:
            header_ts, reports = parse_vehicle_positions(payload)
        if header_ts == self.last_header.get(kind):
            stats[f"{kind}_same_header"] += 1
            return None
        self.last_header[kind] = header_ts
        stats[f"{kind}_refreshes"] += 1
        stats["header_ts_min"] = min(stats.get("header_ts_min") or header_ts, header_ts)
        stats["header_ts_max"] = max(stats.get("header_ts_max", 0), header_ts)
        if kind == "tu":
            rows = self.diff.apply(header_ts, trips)
            for row in rows:
                stats[f"tu_{row[1]}"] += 1
            window.write("tu_changes", rows)
            self.engine.on_trip_updates(header_ts, trips)
        else:
            if strip_vp_stops:  # calibration: mimic the old snapshots, which had no stop fields
                for r in reports:
                    r.stop_id, r.status = "", None
            self.engine.on_reports(header_ts, reports)
            for r in reports:
                stats["vp_rows"] += 1
                stats["vp_repeat"] += r.is_repeat
                stats["vp_stale"] += bool(r.age is not None and r.age > 120 and not r.is_repeat)
                stats["vp_out_of_bbox"] += not r.in_bbox
                stats["vp_valid"] += r.valid
                stats["vp_stopped_at"] += r.status == "STOPPED_AT"
            window.write("vp_reports", [vp_row(header_ts, r) for r in reports])
        self.emit(window)
        return header_ts

    def emit(self, window: Window) -> None:
        visits, status = self.engine.drain()
        for v in visits:
            window.stats[f"visit_{v[10]}"] += 1
        for s in status:
            window.stats[f"trip_{s[6]}"] += 1
        window.write("stop_visits", visits)
        window.write("trip_status", status)


# --------------------------------------------------------------------------- live stream


class Stream:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.state_dir = Path(args.state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.outbox = self.state_dir / "outbox"
        self.outbox.mkdir(exist_ok=True)
        if args.mode == "gcs":
            self.sink: LocalSink | GcsSink = GcsSink(args.bucket, args.archive_bucket)
        else:
            self.sink = LocalSink(Path(args.local_root))
        self.static = StaticCache(self.state_dir / "static")
        self.processor = Processor(VisitEngine(self.static.lookup), TripUpdateDiff())
        self.etags: dict[str, str] = {}
        self.archived_static: set[str] = set()
        self.static_checked = 0.0
        self.window: Window | None = None
        self.next_upload = 0.0
        self.upload_backoff = 15.0
        self.stats: Counter[str] = Counter()

    @property
    def checkpoint_path(self) -> Path:
        return self.state_dir / "checkpoint.pkl"

    # --- state

    def restore(self) -> None:
        path = self.checkpoint_path
        if not path.exists():
            return
        with path.open("rb") as handle:
            state = pickle.load(handle)  # noqa: S301 - written by this process on local disk
        self.processor = state["processor"]
        self.processor.engine.lookup = self.static.lookup
        self.etags = state["etags"]
        self.archived_static = state["archived_static"]
        if state["static_md5"]:
            self.static.load_cached(state["static_md5"])
        saved = state["window"]
        # A window sealed after this checkpoint was written is already in the outbox.
        if saved is not None and (self.state_dir / "open" / window_label(saved["start"])).exists():
            window = Window(self.state_dir, saved["start"])
            window.truncate(saved["sizes"])
            window.rows, window.stats = saved["rows"], saved["stats"]
            self.window = window
        LOGGER.info("Restored checkpoint (window %s)", self.window and self.window.label)

    def checkpoint(self) -> None:
        started = time.time()
        sizes = self.window.sync() if self.window else None
        state = {
            "processor": self.processor,
            "etags": self.etags,
            "archived_static": self.archived_static,
            "static_md5": self.static.current,
            "window": (
                {
                    "start": self.window.start,
                    "sizes": sizes,
                    "rows": self.window.rows,
                    "stats": self.window.stats,
                }
                if self.window
                else None
            ),
        }
        tmp = self.checkpoint_path.with_suffix(".tmp")
        with tmp.open("wb") as handle:
            pickle.dump(state, handle, protocol=pickle.HIGHEST_PROTOCOL)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, self.checkpoint_path)
        self.stats["checkpoint_ms_max"] = max(
            self.stats["checkpoint_ms_max"], int((time.time() - started) * 1000)
        )

    # --- inputs

    def refresh_static(self, now: float) -> None:
        self.static_checked = now
        try:
            payload = io.http_get_with_retry(
                self.args.static_url, timeout=60, retries=2, logger=LOGGER
            ).content
        except requests.RequestException as exc:
            LOGGER.warning("Static GTFS download failed: %s", exc)
            if self.static.current is None and not self.static.load_cached():
                raise SystemExit("No static GTFS available (download failed, no cache)") from exc
            return
        md5, changed = self.static.add(payload, now)
        if md5 not in self.archived_static:
            try:
                self.sink.put_static(md5, payload)
                self.archived_static.add(md5)
            except Exception as exc:  # noqa: BLE001 - retried on the next refresh
                LOGGER.warning("Static archive upload failed: %s", exc)
        if changed:
            LOGGER.info("Static GTFS now %s", md5)

    def fetch(self, kind: str) -> bytes | None:
        url = self.args.trip_updates_url if kind == "tu" else self.args.vehicle_positions_url
        headers = {"If-None-Match": self.etags[kind]} if kind in self.etags else None
        try:
            response = io.http_get_with_retry(
                url, headers=headers, timeout=self.args.timeout_sec, retries=1, logger=LOGGER
            )
        except requests.RequestException as exc:
            self.window.stats[f"{kind}_fetch_errors"] += 1
            LOGGER.warning("Fetch failed for %s: %s", kind, exc)
            return None
        if response.status_code == 304:
            self.window.stats[f"{kind}_not_modified"] += 1
            return None
        if response.status_code != 200:
            self.window.stats[f"{kind}_fetch_errors"] += 1
            LOGGER.warning("Unexpected HTTP %s for %s", response.status_code, kind)
            return None
        if response.headers.get("ETag"):
            self.etags[kind] = response.headers["ETag"]
        return response.content

    def poll_once(self) -> bool:
        changed = False
        for kind in ("tu", "vp"):
            payload = self.fetch(kind)
            if payload is None:
                continue
            try:
                header_ts = self.processor.handle(kind, payload, self.window)
            except Exception:  # noqa: BLE001 - one bad payload must not stop capture
                LOGGER.exception("Failed to process %s payload", kind)
                self.window.stats[f"{kind}_parse_errors"] += 1
                continue
            if header_ts is not None:
                self.window.archive(kind, header_ts, payload)
                changed = True
        return changed

    # --- windows and uploads

    def ensure_window(self, now: float) -> None:
        start = window_start(now)
        if self.window is not None and self.window.start != start:
            self.seal()
        if self.window is None:
            self.window = Window(self.state_dir, start)

    def seal(self) -> None:
        window = self.window
        self.window = None
        window.stats["peak_rss_mb"] = peak_rss_mb()
        window.stats["checkpoint_ms_max"] = self.stats["checkpoint_ms_max"]
        window.seal(
            self.outbox,
            {
                "raw_root": self.sink.raw_root,
                "source": {
                    "trip_updates": self.args.trip_updates_url,
                    "vehicle_positions": self.args.vehicle_positions_url,
                    "static": self.args.static_url,
                },
                "static_md5": self.static.current,
                "feed_version": self.static.feed_version,
                "config": {"interval_sec": self.args.interval_sec},
            },
        )
        self.checkpoint()  # the checkpoint must never point at a window that is already sealed
        LOGGER.info("Sealed window %s rows=%s", window.label, window.rows)

    def drain_outbox(self, now: float) -> None:
        if now < self.next_upload:
            return
        batches = sorted(p for p in self.outbox.iterdir() if p.is_dir())
        for batch in batches:
            try:
                self.sink.publish(batch)
            except Exception as exc:  # noqa: BLE001 - keep the batch and retry later
                self.next_upload = now + self.upload_backoff
                self.upload_backoff = min(self.upload_backoff * 2, 900.0)
                LOGGER.warning("Upload of %s failed (%s); retrying later", batch.name, exc)
                break
            shutil.rmtree(batch)
            self.upload_backoff = 15.0
            LOGGER.info("Published window %s", batch.name)
        remaining = [p for p in self.outbox.iterdir() if p.is_dir()]
        size = sum(f.stat().st_size for p in remaining for f in p.iterdir())
        if len(remaining) > OUTBOX_ALERT_WINDOWS or size > OUTBOX_ALERT_BYTES:
            LOGGER.error("RT_STREAM_OUTBOX_BACKLOG windows=%d bytes=%d", len(remaining), size)

    def heartbeat(self) -> None:
        w = self.window
        LOGGER.info(
            "RT_STREAM_HEARTBEAT %s",
            json.dumps(
                {
                    "window": w.label if w else None,
                    "rows": w.rows if w else None,
                    "tu_refreshes": w.stats["tu_refreshes"] if w else 0,
                    "vp_refreshes": w.stats["vp_refreshes"] if w else 0,
                    "last_header_utc": iso(self.processor.last_header.get("tu")),
                    "open_trips": len(self.processor.engine.trips),
                    "outbox_windows": sum(1 for p in self.outbox.iterdir() if p.is_dir()),
                    "peak_rss_mb": peak_rss_mb(),
                    "static_md5": self.static.current,
                },
                sort_keys=True,
            ),
        )

    def run(self) -> int:
        stopping = []

        def stop(signum, _frame):
            LOGGER.info("Signal %s: stopping after this poll", signum)
            stopping.append(signum)

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        self.restore()
        started = time.time()
        self.refresh_static(started)
        last_beat = 0.0
        next_poll = started
        while not stopping:
            now = time.time()
            if self.args.max_runtime_sec and now - started >= self.args.max_runtime_sec:
                break
            self.ensure_window(now)
            if now - self.static_checked >= self.args.static_refresh_hours * 3600:
                self.refresh_static(now)
            if self.poll_once():
                self.checkpoint()
            self.drain_outbox(now)
            if now - last_beat >= HEARTBEAT_SEC:
                self.heartbeat()
                last_beat = now
            next_poll += self.args.interval_sec
            time.sleep(max(0.0, next_poll - time.time()))
        if self.args.seal_on_exit and self.window is not None:
            self.seal()
            self.drain_outbox(time.time())
        self.checkpoint()
        self.heartbeat()
        return 0


# --------------------------------------------------------------------------- replay


def _gcs_root(source: str) -> tuple[str, str]:
    bucket, _, prefix = source[5:].partition("/")
    return bucket, f"{prefix.strip('/')}/" if prefix.strip("/") else ""


def _archive_tars(
    source: str, start: date | None, until: date | None
) -> Iterator[tuple[str, bytes]]:
    def wanted(day: str) -> bool:
        d = date.fromisoformat(day)
        return (start is None or d >= start) and (until is None or d <= until)

    if source.startswith("gs://"):
        bucket, prefix = _gcs_root(source)
        blobs = io._get_gcs_client().list_blobs(bucket, prefix=f"{prefix}{ARCHIVE_PREFIX}/")
        for blob in sorted(blobs, key=lambda b: b.name):
            day = blob.name.split("date=", 1)[1][:10] if "date=" in blob.name else None
            if day and blob.name.endswith(".tar") and wanted(day):
                yield blob.name, blob.download_as_bytes()
    else:
        for path in sorted(Path(source, ARCHIVE_PREFIX).glob("date=*/*.tar")):
            if wanted(path.parent.name.split("=", 1)[1]):
                yield str(path), path.read_bytes()


def _static_payload(source: str, md5: str) -> bytes:
    if source.startswith("gs://"):
        bucket, prefix = _gcs_root(source)
        blob = io._get_gcs_client().bucket(bucket).blob(f"{prefix}{STATIC_PREFIX}/{md5}.zip")
        return blob.download_as_bytes()
    return Path(source, STATIC_PREFIX, f"{md5}.zip").read_bytes()


class Replay:
    """Rebuild stream outputs from archived payloads with the same engine (determinism checks,
    repairs, calibration). Windows follow feed header time, so batch edges can differ from live."""

    def __init__(self, args: argparse.Namespace):
        self.args = args
        out_root = Path(args.out)
        self.work = out_root / ".work"
        self.dest = out_root / REPLAY_PREFIX
        for scratch in (self.dest, self.work / "open"):  # a replay output is disposable
            if scratch.exists():
                shutil.rmtree(scratch)
        self.static = StaticCache(self.work / "static")
        version = args.data_version or (
            "calibration_v1" if args.engine_mode == "backfill" else "stream_v1"
        )
        engine = VisitEngine(self.static.lookup, mode=args.engine_mode, data_version=version)
        self.processor = Processor(engine, TripUpdateDiff())
        self.meta: dict = {
            "raw_root": str(self.dest),
            "source": {"replay": args.replay},
            "config": {"thin_minutes": args.thin_minutes, "engine_mode": args.engine_mode},
        }
        self.window: Window | None = None
        self.next_keep: dict[str, int] = {}

    def run(self) -> int:
        start = date.fromisoformat(self.args.start_date) if self.args.start_date else None
        until = date.fromisoformat(self.args.end_date) if self.args.end_date else None
        for name, blob in _archive_tars(self.args.replay, start, until):
            with tarfile.open(fileobj=BytesIO(blob)) as tar:
                self._tar(tar)
            LOGGER.info("Replayed %s", name)
        if self.window is not None:
            self.processor.engine.flush()
            self.processor.emit(self.window)
            self._seal()
        return 0

    def _tar(self, tar: tarfile.TarFile) -> None:
        members = {m.name: m for m in tar.getmembers()}
        if "meta.json" in members:
            md5 = json.loads(tar.extractfile(members["meta.json"]).read()).get("static_md5")
            if md5 and md5 not in self.static.feeds:
                self.static.add(_static_payload(self.args.replay, md5), time.time())
        entries = sorted(
            (int(n.split("/")[1].split(".")[0]), 0 if n.startswith("tu/") else 1, n)
            for n in members
            if n.endswith(".pb.gz")
        )
        for header_ts, _, name in entries:
            kind = name.split("/")[0]
            if self._thinned(kind, header_ts):
                continue
            start = window_start(header_ts)
            if self.window is not None and self.window.start != start:
                self._seal()
            if self.window is None:
                self.window = Window(self.work, start)
            payload = gzip.decompress(tar.extractfile(members[name]).read())
            self.processor.handle(
                kind, payload, self.window, strip_vp_stops=self.args.strip_vp_stop_fields
            )

    def _thinned(self, kind: str, header_ts: int) -> bool:
        """Calibration: keep only the first refresh at or after each N-minute boundary."""
        if not self.args.thin_minutes:
            return False
        if header_ts < self.next_keep.get(kind, 0):
            return True
        step = self.args.thin_minutes * 60
        self.next_keep[kind] = (header_ts // step + 1) * step
        return False

    def _seal(self) -> None:
        self.meta["static_md5"] = self.static.current
        self.window.seal(self.dest, self.meta)
        self.window = None


# --------------------------------------------------------------------------- CLI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Continuous RTD GTFS-RT capture.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--local",
        dest="mode",
        action="store_const",
        const="local",
        help="Write batches under data/ (default).",
    )
    mode.add_argument(
        "--gcs", dest="mode", action="store_const", const="gcs", help="Upload batches to GCS."
    )
    parser.set_defaults(mode="local")
    parser.add_argument("--bucket", help="Raw bucket for staging batches (required with --gcs).")
    parser.add_argument(
        "--archive-bucket", help="Coldline bucket for payload archives (with --gcs)."
    )
    parser.add_argument("--local-root", default="data", help="Local output root (--local).")
    parser.add_argument(
        "--state-dir",
        default="data/state/rt_stream",
        help="Checkpoint, open window, outbox and static cache.",
    )
    parser.add_argument("--interval-sec", type=float, default=15.0)
    parser.add_argument("--timeout-sec", type=float, default=10.0)
    parser.add_argument("--max-runtime-sec", type=float, default=0.0, help="0 runs until stopped.")
    parser.add_argument(
        "--seal-on-exit",
        action="store_true",
        help="Seal and publish the open window on exit (local test runs).",
    )
    parser.add_argument("--static-refresh-hours", type=float, default=6.0)
    parser.add_argument("--trip-updates-url", default=DEFAULT_TRIP_UPDATES_URL)
    parser.add_argument("--vehicle-positions-url", default=DEFAULT_VEHICLE_POSITIONS_URL)
    parser.add_argument("--static-url", default=DEFAULT_GTFS_URL)
    replay = parser.add_argument_group("replay")
    replay.add_argument("--replay", help="Archive root (local dir or gs://bucket) to rebuild from.")
    replay.add_argument("--from", dest="start_date", help="First UTC date to replay (YYYY-MM-DD).")
    replay.add_argument("--until", dest="end_date", help="Last UTC date to replay (YYYY-MM-DD).")
    replay.add_argument("--out", default="data/replay", help="Replay output root.")
    replay.add_argument(
        "--thin-minutes", type=int, default=0, help="Keep one refresh per N minutes (calibration)."
    )
    replay.add_argument(
        "--strip-vp-stop-fields",
        action="store_true",
        help="Drop vehicle stop_id/status, like the old snapshots (calibration).",
    )
    replay.add_argument("--engine-mode", choices=("stream", "backfill"), default="stream")
    replay.add_argument("--data-version", help="Override data_version on replayed rows.")
    return parser


def run(args: argparse.Namespace) -> int:
    if args.replay:
        return Replay(args).run()
    if args.mode == "gcs" and not (args.bucket and args.archive_bucket):
        raise SystemExit("--bucket and --archive-bucket are required with --gcs")
    if args.interval_sec <= 0:
        raise SystemExit("--interval-sec must be > 0")
    return Stream(args).run()


def main(argv: Sequence[str] | None = None) -> int:
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
