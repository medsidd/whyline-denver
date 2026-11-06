"""Priority ranking: the unreliability part weights stop-hours by visits and needs 30 of them."""

from __future__ import annotations

from _render import connect, render_model  # tests/sql is on sys.path (pytest prepend mode)


def test_unreliability_is_visit_weighted_and_needs_enough_visits():
    con = connect()
    # BIG: 90 visits all on time and 10 all late -> 10% not on time (an hour average would say 50%).
    # SMALL: six early visits only. OLD: a legacy row, which never counts.
    con.execute(
        """create table mart_reliability_by_stop_hour as select * from (values
            ('BIG', current_date - 1, 'stream_v1', 1.0, 90),
            ('BIG', current_date - 1, 'stream_v1', 0.0, 10),
            ('SMALL', current_date - 1, 'stream_v1', 0.0, 6),
            ('OLD', current_date - 1, null, 0.0, 500)
        ) as t(stop_id, service_date_mst, data_version, pct_on_time, n_reported_events)"""
    )
    con.execute(
        "create table mart_crash_proximity_by_stop as select * from (values "
        "('BIG', 0), ('SMALL', 10), ('OLD', 5)) as t(stop_id, crash_250m_cnt)"
    )
    con.execute(
        "create table mart_vulnerability_by_stop as select * from (values "
        "('BIG', 50.0), ('SMALL', 50.0), ('OLD', 50.0)) as t(stop_id, vuln_score_0_100)"
    )
    con.execute(
        "create table dim_stop as select stop_id, stop_id as stop_name, 39.7 as lat, -105.0 as lon, "
        "true as is_latest_version from (values ('BIG'), ('SMALL'), ('OLD')) as t(stop_id)"
    )
    scores = (
        con.execute(
            render_model(
                "marts/equity/mart_priority_hotspots.sql",
                replacements=((" as float64", " as double"),),
            )
        )
        .df()
        .set_index("stop_id")["reliability_score_0_100"]
    )
    assert abs(scores["BIG"] - 10.0) < 1e-9
    assert scores.isna()["SMALL"] and scores.isna()["OLD"]
