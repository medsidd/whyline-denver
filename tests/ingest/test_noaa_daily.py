from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest
import yaml

from whyline.ingest import noaa_daily as noaa
from whyline.load import bq_load
from whyline.load.registry import JOBS


def test_weather_station_matches_dbt():
    project = Path(__file__).resolve().parents[2] / "dbt/dbt_project.yml"
    assert noaa.DEFAULT_STATION == yaml.safe_load(project.read_text())["vars"]["weather_station"]


def test_metric_values_and_missing_days_are_preserved():
    df = noaa.build_dataframe(
        [{"date": "2026-10-01", "PRCP": 210.5, "SNOW": 250, "TMIN": -2, "TMAX": 8}],
        "2026-10-01",
        "2026-10-02",
        noaa.DEFAULT_STATION,
    )
    assert df.loc[0, "precip_mm"] == 210.5
    assert df.loc[0, "snow_mm"] == 250
    assert df.loc[0, "tavg_c"] == 3
    assert df.loc[0, "precip_bin"] == "heavy"
    assert pd.isna(df.loc[1, "precip_mm"])
    assert pd.isna(df.loc[1, "precip_bin"])
    assert pd.isna(df.loc[1, "snow_day"])


def test_empty_precipitation_is_not_published(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(noaa, "fetch_noaa_cdo", lambda **kwargs: [])
    monkeypatch.setattr(noaa, "fetch_open_meteo", lambda **kwargs: {})
    args = noaa.build_parser().parse_args(
        [
            "--start",
            "2026-10-01",
            "--end",
            "2026-10-02",
            "--token",
            "test-token",
        ]
    )
    with pytest.raises(RuntimeError, match="No precipitation observations"):
        noaa.run(args)
    assert not list(tmp_path.rglob("weather.csv.gz"))
    assert not list(tmp_path.rglob("manifest.json"))


def test_station_extract_preserves_legacy_data_and_is_discovered_once(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    legacy = tmp_path / "data/raw/noaa_daily/extract_date=2026-10-15/weather.csv.gz"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"preserved legacy extract")
    monkeypatch.setattr(
        noaa,
        "fetch_noaa_cdo",
        lambda **kwargs: [{"date": "2026-10-01", "PRCP": 2.5, "SNOW": 0, "TMIN": 5, "TMAX": 15}],
    )
    args = noaa.build_parser().parse_args(
        [
            "--start",
            "2026-10-01",
            "--end",
            "2026-10-02",
            "--token",
            "test-token",
            "--extract-date",
            "2026-10-15",
        ]
    )
    assert noaa.run(args) == 0
    assert legacy.read_bytes() == b"preserved legacy extract"
    job = next(j for j in JOBS if j.name == "noaa_daily")
    monkeypatch.setattr(bq_load, "RAW_ROOT_LOCAL", tmp_path / "data/raw")
    local = list(bq_load.discover_local_files(job))
    assert len(local) == 2
    client = Mock()
    blobs = []
    for ref in local:
        blob = Mock()
        blob.name = "raw/" + ref.relative_path
        blob.size = 1
        blobs.append(blob)
    client.list_blobs.return_value = blobs
    remote = list(
        bq_load.discover_gcs_files(
            job,
            client,
            "test-bucket",
            start_date=None,
            end_date=None,
        )
    )
    assert sorted(r.relative_path for r in remote) == sorted(r.relative_path for r in local)


def test_fetch_retries_transient_timeout(monkeypatch):
    import requests

    ok = Mock(status_code=200)
    ok.json.return_value = {
        "results": [
            {
                "date": "2026-10-27T00:00:00",
                "datatype": "PRCP",
                "value": 1.2,
                "station": "GHCND:USW00003017",
            }
        ]
    }
    calls = Mock(side_effect=[requests.exceptions.ReadTimeout("slow"), ok])
    monkeypatch.setattr(noaa.io.requests, "get", calls)
    monkeypatch.setattr(noaa.io.time, "sleep", lambda _: None)

    rows = noaa.fetch_noaa_cdo(
        token="t",  # noqa: S106
        station="USW00003017",
        start="2026-10-27",
        end="2026-10-27",
        timeout=1,
    )

    assert calls.call_count == 2
    assert rows[0]["PRCP"] == 1.2


def test_open_meteo_fills_only_days_without_noaa_precipitation(monkeypatch):
    monkeypatch.setattr(
        noaa,
        "fetch_open_meteo",
        lambda **kwargs: {
            "2026-10-01": {"PRCP": 9.0, "SNOW": 0.0, "TMAX": 9, "TMIN": 1, "TAVG": 5},
            "2026-10-02": {"PRCP": 2.5, "SNOW": 30.0, "TMAX": 3, "TMIN": -4, "TAVG": -1},
        },
    )
    noaa_rows = [{"date": "2026-10-01", "station": "USW00003017", "PRCP": 0.0, "TMAX": 10}]

    records, filled = noaa.fill_missing_days(
        noaa_rows, station=noaa.DEFAULT_STATION, start="2026-10-01", end="2026-10-02", timeout=1
    )
    df = noaa.build_dataframe(records, "2026-10-01", "2026-10-02", noaa.DEFAULT_STATION)

    assert filled == ["2026-10-02"]
    assert df.loc[0, "precip_mm"] == 0.0  # NOAA observation kept
    assert df.loc[0, "tmax_c"] == 10
    assert df.loc[1, "precip_mm"] == 2.5
    assert df.loc[1, "snow_day"] == 1
    assert df.loc[1, "station"] == noaa.DEFAULT_STATION


def test_noaa_outage_publishes_open_meteo_extract(monkeypatch, tmp_path):
    import requests

    monkeypatch.chdir(tmp_path)

    def down(**kwargs):
        raise requests.exceptions.ReadTimeout("down")

    monkeypatch.setattr(noaa, "fetch_noaa_cdo", down)
    om = Mock(status_code=200)
    om.json.return_value = {
        "daily": {
            "time": ["2026-10-01"],
            "precipitation_sum": [1.5],
            "snowfall_sum": [0.4],
            "temperature_2m_max": [12.0],
            "temperature_2m_min": [2.0],
            "temperature_2m_mean": [7.0],
        }
    }
    monkeypatch.setattr(noaa.io.requests, "get", Mock(return_value=om))
    args = noaa.build_parser().parse_args(
        ["--start", "2026-10-01", "--end", "2026-10-01", "--token", "test-token"]
    )

    assert noaa.run(args) == 0
    (out,) = tmp_path.rglob("weather.csv.gz")
    df = pd.read_csv(out)
    assert df.loc[0, "precip_mm"] == 1.5
    assert df.loc[0, "snow_mm"] == 4.0  # cm converted to mm
    assert "open_meteo_fallback" in next(tmp_path.rglob("manifest.json")).read_text()
