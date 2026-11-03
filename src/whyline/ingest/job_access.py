"""CLI to compute how many jobs each census tract can reach by transit (metrics WP12).

Runs weekly in GitHub Actions (.github/workflows/weekly-access.yml), because routing needs Java and
a few GB of memory. For every tract in the RTD counties inside the RTD box, it routes by walking
and transit (r5py, on OpenStreetMap streets and RTD's current schedule) to every other tract, in
four departure windows on the next Tuesday and Saturday, takes the median travel time over each
window, and counts the jobs (LEHD LODES8 workplace counts, all jobs) in tracts reachable within 30,
45 and 60 minutes. Travel times come from the schedule, not from what ran.

The routing libraries are imported only when routing runs, so the rest of the project and its
tests don't need them: pip install r5py==1.1.7, with Java 21.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io as stdio
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from whyline.ingest import io
from whyline.ingest.rt_engine import LAT_MAX, LAT_MIN, LON_MAX, LON_MIN

TRACTS_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Tracts_Blocks/MapServer/0/query"
)
LODES_URL = "https://lehd.ces.census.gov/data/lodes/LODES8/co/wac/co_wac_S000_JT00_{year}.csv.gz"
# Adams, Arapahoe, Boulder, Broomfield, Denver, Douglas, Jefferson, Weld: the RTD district's counties.
RTD_COUNTIES = ("001", "005", "013", "014", "031", "035", "059", "123")
THRESHOLDS_MIN = (30, 45, 60)
# (name, weekday: 1 Tuesday / 5 Saturday, start hour); each window is two hours.
WINDOWS = (
    ("weekday_am_peak", 1, 7),
    ("weekday_midday", 1, 12),
    ("weekday_evening", 1, 19),
    ("saturday_midday", 5, 10),
)
WINDOW_HOURS = 2
MIN_TRACTS = 600  # 700-odd inside the box

# Column order must equal the loader registry (raw_job_access).
COLUMNS = [
    "origin_geoid",
    "window",
    "departure_date",
    "minutes_threshold",
    "jobs_reachable",
    "total_jobs_region",
    "lodes_year",
    "gtfs_md5",
]

LOGGER = io.get_logger(__name__)


def fetch_tracts(timeout: int) -> pd.DataFrame:
    """Tract internal points for the RTD counties, kept when inside the RTD box."""
    counties = ",".join(f"'{c}'" for c in RTD_COUNTIES)
    response = io.http_get_with_retry(
        TRACTS_URL,
        params={
            "where": f"STATE='08' AND COUNTY IN ({counties})",
            "outFields": "GEOID,INTPTLAT,INTPTLON",
            "returnGeometry": "false",
            "f": "json",
        },
        timeout=timeout,
        logger=LOGGER,
    )
    rows = [f["attributes"] for f in response.json().get("features", [])]
    df = pd.DataFrame(rows).rename(columns={"GEOID": "geoid", "INTPTLAT": "lat", "INTPTLON": "lon"})
    df["lat"], df["lon"] = df.lat.astype(float), df.lon.astype(float)
    inside = df.lon.between(LON_MIN, LON_MAX) & df.lat.between(LAT_MIN, LAT_MAX)
    return df[inside].reset_index(drop=True)


def jobs_by_tract(wac_csv_gz: bytes) -> pd.DataFrame:
    """All jobs (C000) per tract from LODES workplace-area block counts."""
    wac = pd.read_csv(
        stdio.BytesIO(gzip.decompress(wac_csv_gz)),
        usecols=["w_geocode", "C000"],
        dtype={"w_geocode": str},
    )
    wac["geoid"] = wac.w_geocode.str[:11]
    return wac.groupby("geoid", as_index=False).C000.sum().rename(columns={"C000": "jobs"})


def departures(today: date) -> list[tuple[str, datetime]]:
    """Window starts on the next Tuesday and Saturday after today, in local schedule time."""
    out = []
    for name, weekday, hour in WINDOWS:
        days = (weekday - today.weekday()) % 7 or 7
        day = today + timedelta(days=days)
        out.append((name, datetime(day.year, day.month, day.day, hour)))
    return out


def accessibility(
    travel_times: pd.DataFrame, jobs: pd.DataFrame, origins: Sequence[str]
) -> pd.DataFrame:
    """Jobs reachable per origin and threshold from a from_id, to_id, travel_time matrix.

    Unreachable pairs have a NULL travel time and count for no threshold. An origin with no
    reachable destination still gets rows, with 0 jobs.
    """
    tt = travel_times.merge(jobs, left_on="to_id", right_on="geoid", how="left")
    tt["jobs"] = tt.jobs.fillna(0)
    rows = []
    for minutes in THRESHOLDS_MIN:
        reached = tt[tt.travel_time <= minutes].groupby("from_id").jobs.sum()
        for origin in origins:
            rows.append((origin, minutes, int(reached.get(origin, 0))))
    return pd.DataFrame(rows, columns=["origin_geoid", "minutes_threshold", "jobs_reachable"])


def route(
    osm: Path,
    gtfs: Path,
    tracts: pd.DataFrame,
    windows: list[tuple[str, datetime]],
    max_memory: str,
) -> dict:
    """Median travel times per window (r5py), keyed by window name."""
    import sys

    sys.argv.extend(["--max-memory", max_memory])  # r5py reads its JVM settings from argv
    import geopandas
    import r5py

    points = geopandas.GeoDataFrame(
        {"id": tracts.geoid},
        geometry=geopandas.points_from_xy(tracts.lon, tracts.lat),
        crs="EPSG:4326",
    )
    network = r5py.TransportNetwork(str(osm), [str(gtfs)])
    out = {}
    for name, start in windows:
        LOGGER.info("Routing %s from %s.", name, start)
        matrix = r5py.TravelTimeMatrix(
            network,
            origins=points,
            destinations=points,
            departure=start,
            departure_time_window=timedelta(hours=WINDOW_HOURS),
            transport_modes=[r5py.TransportMode.TRANSIT, r5py.TransportMode.WALK],
            max_time=timedelta(minutes=max(THRESHOLDS_MIN)),
        )
        out[name] = pd.DataFrame(matrix)[["from_id", "to_id", "travel_time"]]
    return out


def run(args: argparse.Namespace) -> int:
    if args.mode == "gcs" and not args.bucket:
        raise SystemExit("--bucket is required when using --gcs")
    today = date.fromisoformat(args.extract_date) if args.extract_date else date.today()
    if args.mode == "local":
        root: Any = Path("data/raw")
    else:
        bucket = args.bucket[5:] if args.bucket.startswith("gs://") else args.bucket
        root = f"gs://{bucket.strip('/')}/raw"
    rel = f"job_access/extract_date={today.isoformat()}/job_access.csv.gz"
    out_path = root / rel if isinstance(root, Path) else f"{root}/{rel}"
    if io.exists(out_path) and not args.force:
        LOGGER.info("Skipping job access; %s exists.", out_path)
        return 0

    tracts = fetch_tracts(args.timeout_sec)
    if len(tracts) < MIN_TRACTS:
        raise SystemExit(
            f"only {len(tracts)} tracts inside the RTD box; expected at least {MIN_TRACTS}"
        )
    wac = io.http_get_with_retry(
        LODES_URL.format(year=args.lodes_year), timeout=args.timeout_sec, logger=LOGGER
    )
    jobs = jobs_by_tract(wac.content)
    jobs = jobs[jobs.geoid.isin(set(tracts.geoid))]
    gtfs_md5 = hashlib.md5(Path(args.gtfs).read_bytes(), usedforsecurity=False).hexdigest()
    windows = departures(today)
    matrices = route(Path(args.osm), Path(args.gtfs), tracts, windows, args.max_memory)

    frames = []
    for name, start in windows:
        acc = accessibility(matrices[name], jobs, tracts.geoid.tolist())
        acc.insert(1, "window", name)
        acc.insert(2, "departure_date", start.date().isoformat())
        frames.append(acc)
    df = pd.concat(frames, ignore_index=True)
    df["total_jobs_region"] = int(jobs.jobs.sum())
    df["lodes_year"] = args.lodes_year
    df["gtfs_md5"] = gtfs_md5
    df = df[COLUMNS]
    io.write_csv(df, out_path)
    io.write_manifest(
        out_path,
        {
            "extract_date": today.isoformat(),
            "tracts": int(len(tracts)),
            "jobs_region": int(jobs.jobs.sum()),
            "lodes_year": args.lodes_year,
            "gtfs_md5": gtfs_md5,
            "windows": {n: s.isoformat() for n, s in windows},
            "files": {"job_access.csv.gz": {"path": str(out_path), "row_count": int(len(df))}},
            "written_at_utc": io.utc_now_iso(),
        },
    )
    LOGGER.info("Wrote job access: %d rows for %d tracts.", len(df), len(tracts))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compute jobs reachable by transit per tract.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--local", dest="mode", action="store_const", const="local")
    mode.add_argument("--gcs", dest="mode", action="store_const", const="gcs")
    parser.set_defaults(mode="local")
    parser.add_argument("--bucket", help="GCS bucket name (required with --gcs).")
    parser.add_argument("--osm", required=True, help="OpenStreetMap .osm.pbf covering the RTD box.")
    parser.add_argument("--gtfs", required=True, help="RTD GTFS zip.")
    parser.add_argument("--lodes-year", type=int, default=2023)
    parser.add_argument("--extract-date", help="Override today's date (YYYY-MM-DD).")
    parser.add_argument("--max-memory", default="12G", help="JVM heap for r5py.")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--timeout-sec", type=int, default=120)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
