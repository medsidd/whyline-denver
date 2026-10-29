"""Run fct_stop_visit's incremental SQL offline (DuckDB) against representative visit rows."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
from jinja2 import Environment, StrictUndefined

MODEL = Path(__file__).resolve().parents[2] / "dbt/models/core/fct_stop_visit.sql"

# BigQuery functions the model uses, as DuckDB macros (same argument order).
MACROS = """
create macro farm_fingerprint(s) as hash(s);
create macro timestamp_diff(a, b, unit) as date_diff('second', b, a);
create macro date_sub(d, i) as cast(d - i as date);
create macro timestamp_sub(t, i) as t - i;
"""


def render() -> str:
    sql = (
        Environment(autoescape=False, undefined=StrictUndefined)  # noqa: S701 - SQL, not HTML
        .from_string(MODEL.read_text())
        .render(
            config=lambda **kwargs: "",
            var=lambda name, default: default,
            is_incremental=lambda: True,
            ref=lambda name: name,
            this="fct_stop_visit",
            as_mst=lambda c: f"timezone('America/Denver', {c})",
            hour_mst=lambda c: f"extract(hour from timezone('America/Denver', {c}))",
        )
    )
    return (
        sql.replace("current_date('America/Denver')", "current_date")
        .replace("current_timestamp()", "now()")
        .replace(", second)", ", 'second')")
    )


VISIT_COLUMNS = (
    "service_date date, trip_id varchar, start_date varchar, stop_sequence int, stop_id varchar, "
    "stop_role varchar, route_id varchar, direction_id int, trip_headsign varchar, vehicle_id varchar, "
    "arrival_method varchar, arrival_ts_utc timestamptz, arrival_earliest_ts timestamptz, "
    "arrival_latest_ts timestamptz, departure_earliest_ts timestamptz, departure_latest_ts timestamptz, "
    "dwell_min_sec int, dwell_max_sec int, skipped boolean, stopped_observed boolean, "
    "before_report_ts timestamptz, before_dist_along_m double, after_report_ts timestamptz, "
    "after_dist_along_m double, stop_dist_m double, nearest_offset_m double, "
    "last_predicted_arrival_ts timestamptz, last_prediction_published_ts timestamptz, "
    "trip_switch_at_terminal boolean, low_confidence boolean, is_final boolean, data_version varchar, "
    "static_md5 varchar, emitted_at timestamptz, _ingested_at timestamptz"
)


def visit(
    seq,
    role="middle",
    method="shape_crossing",
    arrival="10:05:20",
    window=30,
    trip="T1",
    version="stream_v1",
    emitted="10:10:00",
    ingested_hours_ago=1,
    service_days_ago=0,
    skipped=False,
    predicted="10:05:40",
):
    day = f"current_date - interval {service_days_ago} day"
    ts = lambda t: f"cast({day} as timestamp) + interval '{t}'" if t else "null"  # noqa: E731
    latest = f"{ts(arrival)} + interval {window // 2} second" if arrival else "null"
    earliest = f"{ts(arrival)} - interval {window - window // 2} second" if arrival else "null"
    return (
        f"select cast({day} as date), '{trip}', '20261102', {seq}, 'S{seq}', '{role}', '15', 0, 'Downtown', "
        f"'V1', '{method}', {ts(arrival)}, {earliest}, {latest}, null, null, null, null, {skipped}, false, "
        f"null, null, null, null, 100.0 * {seq}, 5.0, {ts(predicted)}, null, false, false, true, "
        f"'{version}', 'md5', {ts(emitted)}, now() - interval {ingested_hours_ago} hour"
    )


def test_incremental_stop_visits_conform_to_schedule():
    with duckdb.connect() as con:
        con.execute("set timezone = 'UTC'")
        con.execute(MACROS)
        con.execute(f"create table stg_rt_stop_visits ({VISIT_COLUMNS})")
        rows = [
            visit(1, role="first", method="origin_departure", arrival="10:00:30"),
            visit(2),  # crossing: delay vs scheduled arrival, prediction error, within 30 s
            visit(2, arrival="10:05:50", emitted="10:09:00"),  # older emission of the same visit
            visit(3, arrival="10:09:00", window=120, method="shape_crossing_gap"),
            visit(4, method="last_prediction", arrival="10:12:00"),
            visit(5, method="skipped", arrival=None, skipped=True, window=0),
            visit(6, trip="T_unscheduled"),  # no schedule row: unknown delay, unknown keys
            visit(7),  # already in the fact: must not be inserted again
            visit(8, version="backfill_v1"),  # backfill rows only load in the backfill run
            visit(9, ingested_hours_ago=10),  # older than the 6-hour load lookback
            visit(10, service_days_ago=3),  # service date outside the merge bound
        ]
        con.execute("insert into stg_rt_stop_visits " + " union all ".join(rows))
        con.execute(
            "create table fct_scheduled_stop_time as select * from (values "
            "(current_date, 'T1', 1, 'S1', '15', 0, 11, 21, 31, current_date + interval '09:59:00', current_date + interval '10:00:00'), "
            "(current_date, 'T1', 2, 'S2', '15', 0, 11, 21, 32, current_date + interval '10:05:00', current_date + interval '10:05:00'), "
            "(current_date, 'T0', 2, 'S2', '15', 0, 10, 21, 32, current_date + interval '09:55:00', current_date + interval '09:55:00'), "
            "(current_date, 'T1', 3, 'S3', '15', 0, 11, 21, 33, current_date + interval '10:08:00', current_date + interval '10:08:00'), "
            "(current_date, 'T1', 4, 'S4', '15', 0, 11, 21, 34, current_date + interval '10:11:00', current_date + interval '10:11:00')"
            ") s(service_date_mst, trip_id, stop_sequence, stop_id, route_id, direction_id, trip_key, "
            "route_key, stop_key, sched_arrival_ts_mst, sched_departure_ts_mst)"
        )
        con.execute(
            "create table fct_stop_visit as select current_date as service_date, 'T1' as trip_id, 7 as stop_sequence"
        )
        result = con.execute(render()).fetchdf().set_index("stop_sequence")

    assert sorted(result.index) == [1, 2, 3, 4, 5, 6]
    assert result.loc[1, "delay_sec"] == 30  # origin: departure 10:00:30 vs scheduled departure
    assert result.loc[2, "delay_sec"] == 20 and result.loc[2, "within_30s"]
    assert result.loc[2, "prediction_error_sec"] == 20  # newest emission won the dedup
    assert result.loc[2, "scheduled_headway_sec"] == 600  # T0 at 09:55, T1 at 10:05
    assert result.loc[3, "arrival_window_sec"] == 120 and not result.loc[3, "within_30s"]
    assert result.loc[4, "delay_sec"] == 60 and pd.isna(result.loc[4, "prediction_error_sec"])
    assert pd.isna(result.loc[5, "arrival_ts_utc"])
    assert pd.isna(result.loc[5, "delay_sec"])  # unknown, not zero
    assert result.loc[6, "trip_key"] == -1 and pd.isna(result.loc[6, "delay_sec"])
    assert result.loc[2, "trip_key"] == 11 and result.loc[2, "stop_key"] == 32
