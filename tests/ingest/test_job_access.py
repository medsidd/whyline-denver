"""Jobs reachable by transit (WP12): LODES aggregation, windows, counting, and the CSV contract.

Routing itself (r5py, Java) runs only in the weekly workflow; here it is replaced by a fixed matrix.
"""

from __future__ import annotations

import gzip
import io
from datetime import date, datetime
from pathlib import Path
from unittest.mock import Mock

import pandas as pd

from whyline.ingest import job_access as ja
from whyline.load.registry import JOBS


def _wac(rows: list[tuple[str, int]]) -> bytes:
    csv = "w_geocode,C000,CA01\n" + "".join(f"{b},{n},0\n" for b, n in rows)
    return gzip.compress(csv.encode())


def test_jobs_sum_blocks_into_tracts():
    jobs = ja.jobs_by_tract(
        _wac([("080310029011000", 10), ("080310029012003", 5), ("080310030001000", 7)])
    )
    assert jobs.set_index("geoid").jobs.to_dict() == {"08031002901": 15, "08031003000": 7}


def test_windows_fall_on_the_next_tuesday_and_saturday():
    monday = ja.departures(date(2026, 11, 2))
    assert dict(monday) == {
        "weekday_am_peak": datetime(2026, 11, 3, 7),
        "weekday_midday": datetime(2026, 11, 3, 12),
        "weekday_evening": datetime(2026, 11, 3, 19),
        "saturday_midday": datetime(2026, 11, 7, 10),
    }
    tuesday = dict(ja.departures(date(2026, 11, 3)))
    assert tuesday["weekday_am_peak"] == datetime(2026, 11, 10, 7)  # never today


def test_jobs_reachable_by_threshold():
    tt = pd.DataFrame(
        {
            "from_id": ["A", "A", "A", "B", "B"],
            "to_id": ["A", "B", "C", "B", "C"],
            "travel_time": [0, 25, 50, None, 61],  # B can't reach C within the hour
        }
    )
    jobs = pd.DataFrame({"geoid": ["A", "B", "C"], "jobs": [100, 20, 3]})
    acc = ja.accessibility(tt, jobs, ["A", "B", "Z"]).set_index(
        ["origin_geoid", "minutes_threshold"]
    )
    assert acc.jobs_reachable.to_dict() == {
        ("A", 30): 120,
        ("A", 45): 120,
        ("A", 60): 123,
        ("B", 30): 0,
        ("B", 45): 0,
        ("B", 60): 0,
        ("Z", 30): 0,  # no row in the matrix at all
        ("Z", 45): 0,
        ("Z", 60): 0,
    }


def test_output_matches_the_registry(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ja, "MIN_TRACTS", 2)
    tracts = {
        "features": [
            {"attributes": {"GEOID": g, "INTPTLAT": "+39.74", "INTPTLON": "-104.99"}}
            for g in ("08031002901", "08031003000")
        ]
    }

    def get(url, **kwargs):
        if url == ja.TRACTS_URL:
            return Mock(json=lambda: tracts)
        return Mock(content=_wac([("080310029011000", 10), ("080310030001000", 7)]))

    monkeypatch.setattr(ja.io, "http_get_with_retry", get)
    matrix = pd.DataFrame(
        {"from_id": ["08031002901"], "to_id": ["08031003000"], "travel_time": [20]}
    )
    monkeypatch.setattr(
        ja, "route", lambda osm, gtfs, tracts, windows, mem: {n: matrix for n, _ in windows}
    )
    (tmp_path / "gtfs.zip").write_bytes(b"zip")
    args = ["--local", "--osm", "x.osm.pbf", "--gtfs", "gtfs.zip", "--extract-date", "2026-11-02"]
    assert ja.main(args) == 0

    out = tmp_path / "data/raw/job_access/extract_date=2026-11-02/job_access.csv.gz"
    frame = pd.read_csv(
        io.StringIO(gzip.decompress(out.read_bytes()).decode()), dtype={"origin_geoid": str}
    )
    job = {j.table: j for j in JOBS}["raw_job_access"]
    assert "job_access/extract_date=*/job_access.csv.gz" in job.patterns
    assert list(frame.columns) == [c.name for c in job.columns]
    assert len(frame) == 2 * 4 * 3  # tracts x windows x thresholds
    first = frame[(frame.origin_geoid == "08031002901") & (frame.minutes_threshold == 30)].iloc[0]
    assert (first.jobs_reachable, first.total_jobs_region, first.lodes_year) == (7, 17, 2023)
    assert Path(out.parent / "manifest.json").exists()
