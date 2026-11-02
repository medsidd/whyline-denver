"""Hourly weather: archive and forecast split, unit conversion, and the registry contract."""

from __future__ import annotations

import gzip
import io
import re
from unittest.mock import Mock

import pandas as pd

from whyline.ingest import noaa_daily
from whyline.ingest import weather_hourly as wx
from whyline.load.registry import JOBS

CELL = {
    "TIMESTAMP": re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:00:00Z"),
    "FLOAT64": re.compile(r"-?\d+(\.\d+)?"),
    "STRING": re.compile(r".+"),
}


def _serve(monkeypatch, calls):
    def get(url, params=None, **kwargs):
        calls.append((url, params["start_date"], params["end_date"]))
        hours = pd.date_range(params["start_date"], f"{params['end_date']} 23:00", freq="h")
        archive = url == noaa_daily.OPEN_METEO_ARCHIVE_URL
        n = len(hours)
        hourly = {
            "time": [h.strftime("%Y-%m-%dT%H:%M") for h in hours],
            "precipitation": [0.5 if archive else 0.1] * n,
            "snowfall": [0.3] * n,
            "temperature_2m": [-2.0] * n,
            "wind_speed_10m": [12.0] * n,
        }
        if archive:  # the archive's last day isn't published yet
            for key in ("precipitation", "temperature_2m"):
                hourly[key][-24:] = [None] * 24
        return Mock(json=lambda: {"hourly": hourly}, raise_for_status=lambda: None)

    monkeypatch.setattr(wx.io, "http_get_with_retry", get)


def test_hours_come_from_archive_then_forecast(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    calls: list = []
    _serve(monkeypatch, calls)
    assert wx.main(["--local", "--now-utc", "2026-11-02T17:30:00+00:00"]) == 0
    assert [c[0] for c in calls] == [noaa_daily.OPEN_METEO_ARCHIVE_URL, noaa_daily.OPEN_METEO_URL]
    assert calls[0][1:] == ("2026-10-23", "2026-10-27") and calls[1][1:] == (
        "2026-10-27",
        "2026-11-02",
    )

    path = tmp_path / "data/raw/weather_hourly/extract_date=2026-11-02/weather_hourly.csv.gz"
    frame = pd.read_csv(io.StringIO(gzip.decompress(path.read_bytes()).decode()), dtype=str)
    job = {j.table: j for j in JOBS}["raw_weather_hourly"]
    assert list(frame.columns) == [c.name for c in job.columns]
    for column in job.columns:
        assert frame[column.name].map(CELL[column.field_type].fullmatch).all(), column.name
    hours = frame.set_index("ts_utc")
    assert hours.index.is_unique
    assert hours.loc["2026-10-26T12:00:00Z", "source"] == "open_meteo_archive"
    # The archive had no values for 2026-10-27, so the forecast fills it.
    assert hours.loc["2026-10-27T12:00:00Z", "source"] == "open_meteo_forecast"
    assert hours.index.max() == "2026-11-02T17:00:00Z"  # no future hours
    assert hours.snowfall_mm.iloc[0] == "3.0"  # 0.3 cm


def test_short_extracts_are_not_written(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        wx.io,
        "http_get_with_retry",
        lambda *a, **k: Mock(json=lambda: {"hourly": {}}, raise_for_status=lambda: None),
    )
    assert wx.main(["--local", "--now-utc", "2026-11-02T17:30:00+00:00"]) == 1
    assert not (tmp_path / "data").exists()
