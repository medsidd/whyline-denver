"""The poller's CSVs must match the loader registry column for column (loads map by position)."""

from __future__ import annotations

import csv
import gzip
import io
import re

from test_gtfs_rt_stream import FEED, static_zip

from whyline.ingest import gtfs_rt_stream as stream
from whyline.ingest.rt_engine import TripUpdateDiff, VisitEngine
from whyline.load.registry import JOBS

TABLES = {
    "tu_changes": "raw_gtfsrt_tu_changes",
    "vp_reports": "raw_gtfsrt_vp_stream",
    "stop_visits": "raw_gtfsrt_stop_visits",
    "trip_status": "raw_gtfsrt_trip_status",
}
CELL = {
    "TIMESTAMP": re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"),
    "DATE": re.compile(r"\d{4}-\d{2}-\d{2}"),
    "BOOL": re.compile(r"true|false"),
    "INT64": re.compile(r"-?\d+"),
    "FLOAT64": re.compile(r"-?\d+(\.\d+)?(e-?\d+)?"),
    "STRING": re.compile(r".*", re.S),
}


def test_stream_batches_match_the_registry(tmp_path):
    cache = stream.StaticCache(tmp_path / "static")
    cache.add(static_zip(), 0)
    processor = stream.Processor(VisitEngine(cache.lookup), TripUpdateDiff())
    window = stream.Window(tmp_path, 0)
    for kind, payload in FEED:
        processor.handle(kind, payload, window)
    processor.engine.flush()  # closes the trip, so trip_status has a row too
    processor.emit(window)
    batch = window.seal(tmp_path / "outbox", {"raw_root": "r", "source": {}})

    specs = {job.table: job for job in JOBS}
    for name, table in TABLES.items():
        job = specs[table]
        assert job.patterns == (f"rtd_gtfsrt_stream/snapshot_at=*/{name}.csv.gz",)
        rows = list(
            csv.reader(
                io.StringIO(gzip.decompress((batch / f"{name}.csv.gz").read_bytes()).decode())
            )
        )
        assert rows[0] == [c.name for c in job.columns], table
        assert len(rows) > 1, f"{table}: scenario produced no rows"
        for row in rows[1:]:
            assert len(row) == len(job.columns)
            for value, column in zip(row, job.columns, strict=True):
                assert value == "" or CELL[column.field_type].fullmatch(value), (
                    table,
                    column.name,
                    value,
                )
