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
