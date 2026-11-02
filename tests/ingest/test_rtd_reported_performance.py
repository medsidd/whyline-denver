"""RTD operations reports: PDF parsing on saved reports, and the registry contract."""

from __future__ import annotations

import gzip
import io
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

pytest.importorskip("pdfplumber")  # in requirements.txt; a global test env may lack it

from whyline.ingest import rtd_reported_performance as rtd  # noqa: E402
from whyline.load.registry import JOBS  # noqa: E402

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "rtd_reports"
BASE = "https://cdn.rtd-denver.com/image/upload/v1/"


def _values(name: str) -> dict[tuple[str, str], float]:
    df = rtd.parse_report(BASE + name, (FIXTURES / name).read_bytes())
    return {(r.service, r.metric): r.value_pct for r in df.itertuples()}, df


def test_bus_report_values_by_position():
    # Two tables sit side by side, so the text runs together: "Local 84.35% 84.22% / 84.30% 99.44%".
    values, df = _values("Bus_Operations_April_2026_emliql.pdf")
    assert set(df.report_month) == {"2026-04-01"} and set(df["mode"]) == {"bus"}
    assert values == {
        ("all_bus", "otp_month"): 84.30,
        ("all_bus", "service_availability"): 99.44,
        ("local", "otp_month"): 84.35,
        ("local", "otp_ytd"): 84.22,
        ("regional", "otp_month"): 84.15,
        ("regional", "otp_ytd"): 84.54,
        ("regional_brt", "otp_month"): 82.49,
        ("regional_brt", "otp_ytd"): 83.62,
    }


def test_older_bus_layout_puts_the_all_bus_row_beside_regional():
    values, df = _values("Bus_Operations_Report_January_2025_eyoa6w.pdf")
    assert set(df.report_month) == {"2025-01-01"}
    assert values[("all_bus", "otp_month")] == 82.53
    assert values[("all_bus", "service_availability")] == 99.55
    assert values[("regional", "otp_month")] == 81.73 and values[("local", "otp_ytd")] == 82.47


def test_rail_report_with_a_footnote_marker():
    values, df = _values("Rail_Operations_January_2025_kkjowd.pdf")  # "62.58%*"
    assert set(df.report_month) == {"2025-01-01"} and set(df["mode"]) == {"rail"}
    assert values[("light_rail", "otp_month")] == 62.58
    assert values[("light_rail", "service_availability")] == 96.71
    assert values[("commuter_rail_n", "otp_ytd")] == 95.37
    assert len(values) == 9


def test_month_comes_from_the_file_name_when_the_title_has_none():
    assert (
        rtd.report_month("Bus_Operations_Report_-_Feb_25_xbralg.pdf", "")
        == pd.Timestamp("2025-02-01").date()
    )
    with pytest.raises(ValueError):
        rtd.report_month("report.pdf", "no date here")


def test_index_links_are_downloaded_and_match_the_registry(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(rtd, "MIN_REPORTS", 2)
    names = sorted(p.name for p in FIXTURES.glob("*.pdf"))
    index = (
        " ".join(f'<a href="{BASE}{n}">x</a>' for n in names)
        + f' <a href="{BASE}Rail_Operations_Broken_x.pdf">'
    )

    def get(url, **kwargs):
        if url == rtd.INDEX_URL:
            return Mock(text=index)
        name = url.rsplit("/", 1)[1]
        return Mock(
            content=(FIXTURES / name).read_bytes() if (FIXTURES / name).exists() else b"not a pdf"
        )

    monkeypatch.setattr(rtd.io, "http_get_with_retry", get)
    assert (
        rtd.main(["--local", "--extract-date", "2026-11-02"]) == 1
    )  # the broken report fails alone
    out = (
        tmp_path
        / "data/raw/rtd_reported_performance/extract_date=2026-11-02/rtd_reported_performance.csv.gz"
    )
    frame = pd.read_csv(io.StringIO(gzip.decompress(out.read_bytes()).decode()))
    job = {j.table: j for j in JOBS}["raw_rtd_reported_performance"]
    assert list(frame.columns) == [c.name for c in job.columns]
    assert len(frame) == 8 + 8 + 9 and frame.value_pct.between(0, 100).all()
