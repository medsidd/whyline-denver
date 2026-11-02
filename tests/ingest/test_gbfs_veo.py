"""Veo GBFS: vehicle parsing, sanity checks and the snapshot file the loader reads."""

from __future__ import annotations

import gzip
import io
import json
import re

import pandas as pd

from whyline.ingest import gbfs_veo
from whyline.load import bq_load
from whyline.load.registry import JOBS

CELL = {
    "TIMESTAMP": re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"),
    "BOOL": re.compile(r"true|false"),
    "INT64": re.compile(r"-?\d+"),
    "FLOAT64": re.compile(r"-?\d+(\.\d+)?"),
    "STRING": re.compile(r".*"),
}
TYPES = {
    "data": {
        "vehicle_types": [
            {
                "vehicle_type_id": "2",
                "form_factor": "bicycle",
                "propulsion_type": "electric_assist",
            },
            {"vehicle_type_id": "5", "form_factor": "scooter", "propulsion_type": "electric"},
        ]
    }
}


def _status(n: int, lon: float = -104.99) -> dict:
    bike = {
        "bike_id": "cde6986b",
        "lat": 39.75,
        "lon": lon,
        "is_reserved": False,
        "is_disabled": False,
        "rental_uris": {"ios": "https://example.test/?number=1036820"},
        "vehicle_type_id": "5",
        "current_range_meters": 21078.4,
    }
    bikes = [dict(bike) for _ in range(n)]
    bikes[0].update(vehicle_type_id="2", is_reserved=True)
    bikes[1].update(vehicle_type_id="9")  # unknown type
    return {"last_updated": 1793638110, "data": {"bikes": bikes}}


def _serve(monkeypatch, status, types=TYPES):
    pages = {"free_bike_status": status, "vehicle_types": types}
    monkeypatch.setattr(
        gbfs_veo,
        "fetch_feed",
        lambda url, timeout: (json.dumps(pages[url.rsplit("/", 1)[1]]).encode(), None),
    )


def test_vehicles_parse_without_identifiers():
    df = gbfs_veo.parse_vehicles(_status(3), TYPES)
    assert list(df.columns) == gbfs_veo.VEHICLE_COLUMNS  # no bike_id, no rental URI
    first = df.iloc[0]
    assert (first.form_factor, first.propulsion, first.is_reserved) == (
        "bicycle",
        "electric_assist",
        "true",
    )
    assert first.snapshot_ts_utc == "2026-11-02T16:48:30Z" and first.current_range_m == 21078
    assert pd.isna(df.iloc[1].form_factor)


def test_snapshot_matches_the_registry(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _serve(monkeypatch, _status(gbfs_veo.MIN_VEHICLES))
    assert gbfs_veo.main(["--local", "--now-utc", "2026-11-02T16:47:30+00:00"]) == 0
    snapshot = tmp_path / "data/raw/gbfs_veo/snapshot_at=2026-11-02T16:47"
    job = {j.table: j for j in JOBS}["raw_gbfs_veo_vehicles"]
    assert "gbfs_veo/snapshot_at=*/vehicles.csv.gz" in job.patterns
    data = (snapshot / "vehicles.csv.gz").read_bytes()
    manifest = json.loads((snapshot / "manifest.json").read_text())
    assert manifest["files"]["vehicles.csv.gz"]["hash_md5"] == bq_load.md5_bytes(data)
    assert manifest["quality"] == {"in_box_share": 1.0, "n_unknown_type": 1}
    frame = pd.read_csv(io.StringIO(gzip.decompress(data).decode()), dtype=str)
    assert list(frame.columns) == [c.name for c in job.columns]
    for column in job.columns:
        for value in frame[column.name].dropna():
            assert CELL[column.field_type].fullmatch(value), (column.name, value)


def test_suspect_feeds_are_not_written(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    args = ["--local", "--now-utc", "2026-11-02T16:47:30+00:00"]
    _serve(monkeypatch, _status(gbfs_veo.MIN_VEHICLES - 1))  # too few vehicles
    assert gbfs_veo.main(args) == 1
    _serve(monkeypatch, _status(gbfs_veo.MIN_VEHICLES, lon=-87.6))  # outside Denver
    assert gbfs_veo.main(args) == 1
    monkeypatch.setattr(gbfs_veo, "fetch_feed", lambda url, timeout: (b"<html>", None))
    assert gbfs_veo.main(args) == 1
    assert not (tmp_path / "data").exists()
