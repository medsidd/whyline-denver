import gzip
from pathlib import Path

import pandas as pd

FIXTURES_ROOT = Path(__file__).resolve().parent.parent / "fixtures"


def _latest_partition(*paths: Path) -> Path:
    for base in paths:
        if not base.exists():
            continue
        partitions = sorted([p for p in base.iterdir() if p.is_dir()])
        if partitions:
            return partitions[-1]
    raise FileNotFoundError(f"No partitions found in {[str(p) for p in paths]}")


def _load_csv_gz(path: Path) -> pd.DataFrame:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return pd.read_csv(handle)


def _assert_no_all_null(df: pd.DataFrame, *, allow: set[str] | None = None) -> None:
    allow = allow or set()
    all_null = df.isna().all()
    offenders = [col for col, is_null in all_null.items() if is_null and col not in allow]
    assert not offenders, f"Columns entirely null: {offenders}"


def test_gtfs_realtime_contracts(tmp_path: Path):
    base = Path("data/raw/rtd_gtfsrt")
    fixture = FIXTURES_ROOT / "rtd_gtfsrt"
    latest = _latest_partition(base, fixture)
    trip_updates = _load_csv_gz(latest / "trip_updates.csv.gz")
    vehicle_positions = _load_csv_gz(latest / "vehicle_positions.csv.gz")

    trip_expected = {
        "feed_ts_utc",
        "entity_id",
        "trip_id",
        "route_id",
        "stop_id",
        "stop_sequence",
        "arrival_delay_sec",
        "departure_delay_sec",
        "schedule_relationship",
        "event_ts_utc",
        "start_date",
        "start_time",
    }
    assert set(trip_updates.columns) == trip_expected
    assert trip_updates.columns.is_unique
    _assert_no_all_null(
        trip_updates,
        allow={"start_date", "start_time", "arrival_delay_sec", "departure_delay_sec"},
    )
    assert pd.api.types.is_integer_dtype(trip_updates["stop_sequence"].dropna())

    vehicle_expected = {
        "feed_ts_utc",
        "entity_id",
        "trip_id",
        "route_id",
        "vehicle_id",
        "vehicle_label",
        "lon",
        "lat",
        "bearing",
        "speed_mps",
        "event_ts_utc",
    }
    assert set(vehicle_positions.columns) == vehicle_expected
    assert vehicle_positions.columns.is_unique
    _assert_no_all_null(vehicle_positions, allow={"speed_mps"})
    assert pd.api.types.is_float_dtype(vehicle_positions["lon"].dropna())


def test_denver_crashes_contract():
    base = Path("data/raw/denver_crashes")
    fixture = FIXTURES_ROOT / "denver_crashes"
    latest = _latest_partition(base, fixture)
    df = _load_csv_gz(latest / "crashes.csv.gz")
    expected = {
        "crash_id",
        "event_ts_utc",
        "severity",
        "severity_text",
        "lat",
        "lon",
        "roadway_name",
        "on_route",
        "off_route",
        "bike_involved",
        "ped_involved",
    }
    assert set(df.columns) == expected
    assert df.columns.is_unique
    _assert_no_all_null(df)
    assert pd.api.types.is_integer_dtype(df["bike_involved"].dropna())


def test_denver_sidewalks_contract():
    base = Path("data/raw/denver_sidewalks")
    fixture = FIXTURES_ROOT / "denver_sidewalks"
    latest = _latest_partition(base, fixture)
    df = _load_csv_gz(latest / "sidewalks.csv.gz")
    expected = {
        "sidewalk_id",
        "class",
        "status",
        "material",
        "year_built",
        "lon_start",
        "lat_start",
        "lon_end",
        "lat_end",
        "length_m",
        "centroid_lon",
        "centroid_lat",
    }
    assert set(df.columns) == expected
    assert df.columns.is_unique
    _assert_no_all_null(df, allow={"year_built"})
    assert pd.api.types.is_float_dtype(df["length_m"].dropna())


def test_noaa_daily_contract():
    base = Path("data/raw/noaa_daily")
    fixture = FIXTURES_ROOT / "noaa_daily"
    latest = _latest_partition(base, fixture)
    df = _load_csv_gz(latest / "weather.csv.gz")
    expected = {
        "date",
        "station",
        "snow_mm",
        "precip_mm",
        "tmin_c",
        "tmax_c",
        "tavg_c",
        "snow_day",
        "precip_bin",
    }
    assert set(df.columns) == expected
    assert df.columns.is_unique
    _assert_no_all_null(df)
    assert pd.api.types.is_float_dtype(df["precip_mm"].dropna())


def test_acs_contract():
    base = Path("data/raw/acs")
    fixture = FIXTURES_ROOT / "acs"
    latest = _latest_partition(base, fixture)
    df = _load_csv_gz(latest / "acs_tract.csv.gz")
    expected = {
        "geoid",
        "name",
        "year",
        "hh_no_vehicle",
        "hh_total",
        "workers_transit",
        "workers_total",
        "persons_poverty",
        "pop_total",
        "pct_hh_no_vehicle",
        "pct_transit_commute",
        "pct_poverty",
    }
    assert set(df.columns) == expected
    assert df.columns.is_unique
    _assert_no_all_null(df)
    assert pd.api.types.is_float_dtype(df["pct_hh_no_vehicle"].dropna())
