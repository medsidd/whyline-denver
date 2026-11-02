"""Prediction accuracy (WP1): the prediction on screen at each horizon, run in DuckDB."""

from __future__ import annotations

from _render import connect, render_model  # tests/sql is on sys.path (pytest prepend mode)

FACT_SQL = (
    (
        "select horizon_min from unnest([1, 3, 5, 10, 15, 20, 30]) as horizon_min",
        "select unnest([1, 3, 5, 10, 15, 20, 30]) as horizon_min",
    ),
    ("interval h.horizon_min minute", "to_minutes(h.horizon_min)"),
    ("timestamp(date_", "(date_"),
)
MART_SQL = tuple(
    (f"approx_quantiles(error_sec, 100)[offset({q})]", f"quantile_disc(error_sec, {q / 100})")
    for q in (5, 50, 95)
)


def _ts(clock: str, days_ago: int = 1) -> str:
    return f"cast(current_date - {days_ago} as timestamp) + interval '{clock}'"


def _inputs(con):
    visits = [
        # (trip, seq, method, arrival, within_30s, days_ago)
        ("T1", 5, "shape_crossing", "10:30:00", True, 1),
        ("T2", 5, "shape_crossing_gap", "11:00:00", True, 1),  # nothing predicted for it
        ("T3", 5, "last_prediction", "10:30:00", True, 1),  # arrival not measured
        ("T4", 5, "shape_crossing_gap", "10:30:00", False, 1),  # too imprecise
        ("T5", 5, "shape_crossing", "10:30:00", True, 5),  # outside the rebuild window
    ]
    con.execute(
        "create table fct_stop_visit as "
        + " union all ".join(
            f"select cast(current_date - {d} as date) as service_date, '{t}' as trip_id, {s} as stop_sequence, "
            f"'S{s}' as stop_id, '15' as route_id, 0 as direction_id, '{m}' as arrival_method, "
            f"{_ts(a, d)} as arrival_ts_utc, {w} as within_30s"
            for t, s, m, a, w, d in visits
        )
    )
    changes = [
        # (trip, seq, feed_ts, change_type, predicted)
        ("T1", 5, "10:00:00", "new", "10:28:00"),  # on screen at 30 and 20 min out: 2 min late
        ("T1", 5, "10:12:00", "changed", "10:34:30"),  # 15 min out: 4.5 min early, outside
        ("T1", 5, "10:18:00", "changed", "10:27:30"),  # 10 min out, shown as 7.5: 2.5 min late
        ("T1", 5, "10:24:00", "dropped", "10:27:30"),  # nothing on screen at 5 min out
        ("T1", 5, "10:26:30", "new", "10:29:00"),  # 3 min out: 1 min late, the band's edge
        ("T1", 5, "10:28:30", "changed", "10:28:50"),  # 1 min out, shown as due: 70 s late
        ("T1", None, "10:28:40", "changed", None),  # trip-level row, ignored
        ("T1", 6, "10:28:40", "changed", "10:40:00"),  # another stop
        ("T1", 5, "10:31:00", "changed", "10:31:00"),  # after the arrival
        ("T2", 5, "10:59:00", "new", None),  # stop marked skipped: no time shown
    ]
    con.execute(
        "create table stg_rt_prediction_changes as "
        + " union all ".join(
            f"select cast(current_date - 1 as date) as service_date, '{t}' as trip_id, "
            f"cast({'null' if s is None else s} as int) as stop_sequence, {_ts(f)} as feed_ts_utc, "
            f"'{c}' as change_type, {'null' if p is None else _ts(p)} as predicted_ts_utc, "
            f"{s is None} as is_trip_level"
            for t, s, f, c, p in changes
        )
    )


def test_prediction_on_screen_at_each_horizon():
    con = connect()
    _inputs(con)
    sql = render_model("core/fct_prediction_accuracy.sql", incremental=True, replacements=FACT_SQL)
    rows = con.execute(sql).df()

    assert set(rows.trip_id) == {"T1", "T2"}
    t1 = rows[rows.trip_id == "T1"].set_index("horizon_min")
    # error = actual - predicted; at 20 min out the 10:12 change was not yet made.
    assert t1.error_sec.dropna().astype(int).to_dict() == {
        1: 70,
        3: 60,
        10: 150,
        15: -270,
        20: 120,
        30: 120,
    }
    assert not t1.loc[5, "has_prediction"]  # the latest change before then was a drop
    # Buckets follow the countdown shown; with none shown, the true time to arrival.
    assert t1.countdown_sec.dropna().astype(int).to_dict() == {
        1: -10,
        3: 120,
        10: 450,
        15: 1170,
        20: 1080,
        30: 1680,
    }
    assert t1.horizon_bucket.to_dict() == {
        1: "0-3",
        3: "0-3",
        5: "3-6",
        10: "6-12",
        15: "12-30",
        20: "12-30",
        30: "12-30",
    }
    assert t1.within_band.dropna().to_dict() == {
        1: False,
        3: True,
        10: True,
        15: False,
        20: True,
        30: True,
    }
    assert not rows[rows.trip_id == "T2"].has_prediction.any()

    con.execute(f"create table fct_prediction_accuracy as {sql}")
    mart = render_model(
        "marts/realtime/mart_prediction_accuracy_by_route_day.sql", replacements=MART_SQL
    )
    far = con.execute(mart).df().set_index("horizon_bucket").loc["12-30"]
    assert (far.n_visits, far.n_predictions, far.n_no_prediction) == (6, 3, 3)
    assert abs(far.pct_within_band - 2 / 3) < 1e-9
    assert (far.p05_error_sec, far.median_error_sec, far.padding_sec) == (-270, 120, 270)
    assert far.pct_earlier_by_1min == 1 / 3 and far.pct_later_by_2min == 0
