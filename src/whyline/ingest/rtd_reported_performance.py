"""CLI to extract RTD's own monthly on-time performance from its Bus and Rail Operations reports.

RTD posts one Bus Operations and one Rail Operations PDF a month, linked from its board briefing
documents page. This reads that page, downloads every linked report and extracts:
- bus: service availability and on-time performance for all bus (month), and on-time performance
  for Local, Regional and Regional BRT (month and year to date);
- rail: service availability and on-time performance (month and year to date) for light rail,
  the A, B and G commuter lines, and the N Line.
A report whose layout no longer matches logs RTD_REPORT_PARSE_FAILED and is skipped; the others
still load. Each extract is the full history, refreshed at most weekly.
"""

from __future__ import annotations

import argparse
import io as stdio
import re
from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pdfplumber

from whyline.ingest import io

INDEX_URL = "https://www.rtd-denver.com/board-briefing-documents"
LINK = re.compile(
    r"https://cdn\.rtd-denver\.com/[^\"'\s<>]*(?:Bus|Rail)_Operations[^\"'\s<>]*\.pdf"
)
MONTHS = {
    m: i + 1
    for i, names in enumerate(
        [
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ]
    )
    for m in names
}
MONTH_YEAR = re.compile(
    r"(?i)\b(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")[\s_-]+(\d{4}|\d{2})\b"
)
RAIL_ROW = re.compile(
    r"^(Light Rail Operations|A, B, G Line . Commuter Rail|N Line . Commuter Rail)\s+\w+\s+"
    r"([\d.]+)%\*?\s+([\d.]+)%\*?\s+([\d.]+)%"  # an asterisk marks a footnote
)
RAIL_SERVICES = {
    "Light Rail": "light_rail",
    "A, B, G": "commuter_rail_abg",
    "N Line": "commuter_rail_n",
}
BUS_SERVICES = ("local", "regional", "regional_brt")
REFRESH_DAYS = 7
MIN_REPORTS = 20  # 40 linked on 2026-11-02

COLUMNS = ["report_month", "mode", "service", "metric", "value_pct", "source_url"]

LOGGER = io.get_logger(__name__)


def report_month(name: str, text: str) -> date:
    """Month and year from the report title, else from its file name."""
    for source in (text[:300], name.replace("_", " ")):
        m = MONTH_YEAR.search(source)
        if m:
            year = int(m[2]) + (2000 if len(m[2]) == 2 else 0)
            return date(year, MONTHS[m[1].lower()], 1)
    raise ValueError("no month and year in the title or file name")


def parse_rail(text: str) -> list[tuple[str, str, float]]:
    rows = []
    for line in text.splitlines():
        m = RAIL_ROW.match(line.strip())
        if m:
            service = next(v for k, v in RAIL_SERVICES.items() if m[1].startswith(k))
            rows += [
                (service, "service_availability", float(m[2])),
                (service, "otp_month", float(m[3])),
                (service, "otp_ytd", float(m[4])),
            ]
    if {r[0] for r in rows} != set(RAIL_SERVICES.values()):
        raise ValueError(f"rail rows found: {sorted({r[0] for r in rows})}")
    return rows


def _bus_columns(words: list[dict]) -> dict[str, float]:
    """x positions of the four value columns, from the header words above the table."""
    head: dict[str, float] = {}
    for w in (w for w in words if w["top"] <= 200):
        middle = (w["x0"] + w["x1"]) / 2
        if w["text"] == "OTP":
            head["all_otp"] = middle
        elif w["text"] == "Availability":
            head["all_availability"] = middle
        elif w["text"] == "YTD":
            head["ytd"] = middle
        elif w["text"] == "Time" and "month" not in head:
            head["month"] = w["x0"]
    if len(head) != 4:
        raise ValueError(f"bus header columns found: {sorted(head)}")
    return head


def _bus_labels(words: list[dict]) -> list[tuple[float, str]]:
    """Row positions of the Local, Regional and Regional BRT labels."""
    labels = []
    for w in (w for w in words if w["x0"] < 120 and w["top"] < 300):
        if w["text"] == "Local":
            labels.append((w["top"], "local"))
        elif w["text"] == "Regional":
            brt = any(v["text"] == "BRT" and abs(v["top"] - w["top"]) < 2 for v in words)
            labels.append((w["top"], "regional_brt" if brt else "regional"))
    if sorted(s for _, s in labels) != sorted(BUS_SERVICES):
        raise ValueError(f"bus row labels found: {sorted(s for _, s in labels)}")
    return labels


def parse_bus(page: Any) -> list[tuple[str, str, float]]:
    """Bus reports lay two tables side by side, so text order is unreliable; use positions.

    Header words fix four columns: all-bus "Report Month OTP" and "Service Availability", then
    "On Time Performance" (month) and "YTD On-Time Performance" by service type, whose rows are
    the Local, Regional and Regional BRT labels.
    """
    words = page.extract_words()
    head, labels = _bus_columns(words), _bus_labels(words)
    top, bottom = min(t for t, _ in labels) - 12, max(t for t, _ in labels) + 12
    rows = []
    for w in words:
        token = w["text"].rstrip("*")  # an asterisk marks a footnote
        if not token.endswith("%") or not top <= w["top"] <= bottom:
            continue
        value = float(token.rstrip("%"))
        column = min(head, key=lambda k: abs(head[k] - (w["x0"] + w["x1"]) / 2))
        if column == "all_otp":
            rows.append(("all_bus", "otp_month", value))
        elif column == "all_availability":
            rows.append(("all_bus", "service_availability", value))
        else:
            service = min(labels, key=lambda lab: abs(lab[0] - w["top"]))[1]
            rows.append((service, "otp_month" if column == "month" else "otp_ytd", value))
    expected = {("all_bus", "otp_month"), ("all_bus", "service_availability")} | {
        (s, m) for s in BUS_SERVICES for m in ("otp_month", "otp_ytd")
    }
    if {(s, m) for s, m, _ in rows} != expected or len(rows) != len(expected):
        raise ValueError(f"bus values found: {sorted((s, m) for s, m, _ in rows)}")
    return rows


def parse_report(url: str, payload: bytes) -> pd.DataFrame:
    with pdfplumber.open(stdio.BytesIO(payload)) as pdf:
        page = pdf.pages[0]
        text = page.extract_text() or ""
        month = report_month(url.rsplit("/", 1)[-1], text)
        mode = "rail" if "Rail_Operations" in url else "bus"
        rows = parse_rail(text) if mode == "rail" else parse_bus(page)
    for _, metric, value in rows:
        if not 0 <= value <= 100:
            raise ValueError(f"{metric} {value} is not a percentage")
    return pd.DataFrame(
        [(month.isoformat(), mode, s, m, v, url) for s, m, v in rows], columns=COLUMNS
    )


def run(args: argparse.Namespace) -> int:
    if args.mode == "gcs" and not args.bucket:
        raise SystemExit("--bucket is required when using --gcs")
    today = date.fromisoformat(args.extract_date) if args.extract_date else date.today()
    if args.mode == "local":
        root: Any = Path("data/raw")
    else:
        bucket = args.bucket[5:] if args.bucket.startswith("gs://") else args.bucket
        root = f"gs://{bucket.strip('/')}/raw"

    def path(d: date) -> Any:
        rel = (
            f"rtd_reported_performance/extract_date={d.isoformat()}/rtd_reported_performance.csv.gz"
        )
        return root / rel if isinstance(root, Path) else f"{root}/{rel}"

    if not args.force and any(
        io.exists(path(today - timedelta(days=d))) for d in range(REFRESH_DAYS)
    ):
        LOGGER.info("Skipping RTD reports; extracted within %d days.", REFRESH_DAYS)
        return 0

    page = io.http_get_with_retry(args.index_url, timeout=args.timeout_sec, logger=LOGGER).text
    urls = sorted(set(LINK.findall(page)))
    frames, failed = [], []
    for url in urls:
        try:
            response = io.http_get_with_retry(url, timeout=args.timeout_sec, logger=LOGGER)
            frames.append(parse_report(url, response.content))
        except Exception as exc:  # one changed layout must not stop the rest
            LOGGER.warning("RTD_REPORT_PARSE_FAILED %s: %s", url, exc)
            failed.append(url)
    if len(frames) < MIN_REPORTS:
        LOGGER.warning(
            "RTD_REPORTS_SUSPECT parsed %d of %d linked reports; not written",
            len(frames),
            len(urls),
        )
        return 1
    df = pd.concat(frames, ignore_index=True)
    out = path(today)
    io.write_csv(df, out)
    io.write_manifest(
        out,
        {
            "source": args.index_url,
            "extract_date": today.isoformat(),
            "reports_linked": len(urls),
            "reports_parsed": len(frames),
            "reports_failed": failed,
            "files": {
                "rtd_reported_performance.csv.gz": {"path": str(out), "row_count": int(len(df))}
            },
            "written_at_utc": io.utc_now_iso(),
        },
    )
    LOGGER.info("Wrote %d values from %d of %d reports.", len(df), len(frames), len(urls))
    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract RTD's reported monthly on-time performance."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--local", dest="mode", action="store_const", const="local")
    mode.add_argument("--gcs", dest="mode", action="store_const", const="gcs")
    parser.set_defaults(mode="local")
    parser.add_argument("--bucket", help="GCS bucket name (required with --gcs).")
    parser.add_argument("--index-url", default=INDEX_URL)
    parser.add_argument("--extract-date", help="Override today's date (YYYY-MM-DD).")
    parser.add_argument("--force", action="store_true", help="Fetch even if extracted this week.")
    parser.add_argument("--timeout-sec", type=int, default=60)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
