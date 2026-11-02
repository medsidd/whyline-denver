"""NTD monthly: paging, typing, the weekly skip and the registry contract."""

from __future__ import annotations

import gzip
import io
import re
from unittest.mock import Mock

import pandas as pd

from whyline.ingest import ntd_monthly as ntd
from whyline.load.registry import JOBS

CELL = {
    "DATE": re.compile(r"\d{4}-\d{2}-\d{2}"),
    "INT64": re.compile(r"\d+"),
    "STRING": re.compile(r".+"),
}


def _rows(n: int) -> list[dict]:
    return [
        {
            "date": f"20{2 + i // 12:02d}-{1 + i % 12:02d}-01T00:00:00.000",
            "mode": "MB",
            "tos": "DO",
            "_3_mode": "Bus",
            "upt": "2656573",
            "vrm": "1453907",
            "vrh": "122787.4",
            "voms": "341",
        }
        for i in range(n)
    ]


def _serve(monkeypatch, rows, calls):
    def get(url, params=None, **kwargs):
        calls.append(params["$offset"])
        assert params["ntd_id"] == ntd.RTD_NTD_ID
        return Mock(json=lambda: rows[params["$offset"] : params["$offset"] + params["$limit"]])

    monkeypatch.setattr(ntd.io, "http_get_with_retry", get)


def test_full_history_pages_and_matches_the_registry(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ntd, "PAGE_SIZE", 1000)
    calls: list = []
    _serve(monkeypatch, _rows(ntd.MIN_ROWS), calls)
    assert ntd.main(["--local", "--extract-date", "2026-11-02"]) == 0
    assert calls == [0, 1000]

    path = tmp_path / "data/raw/ntd_monthly/extract_date=2026-11-02/ntd_monthly.csv.gz"
    frame = pd.read_csv(io.StringIO(gzip.decompress(path.read_bytes()).decode()), dtype=str)
    job = {j.table: j for j in JOBS}["raw_ntd_monthly"]
    assert "ntd_monthly/extract_date=*/ntd_monthly.csv.gz" in job.patterns
    assert list(frame.columns) == [c.name for c in job.columns]
    for column in job.columns:
        assert frame[column.name].map(CELL[column.field_type].fullmatch).all(), column.name
    assert (frame.month[0], frame.mode_group[0], frame.vrh[0]) == ("2002-01-01", "Bus", "122787")

    calls.clear()
    assert ntd.main(["--local", "--extract-date", "2026-11-08"]) == 0  # same week: skipped
    assert calls == []


def test_short_responses_are_not_written(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _serve(monkeypatch, _rows(ntd.MIN_ROWS - 1), [])
    assert ntd.main(["--local", "--extract-date", "2026-11-02"]) == 1
    assert not (tmp_path / "data").exists()
