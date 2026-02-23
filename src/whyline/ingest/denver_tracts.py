"""CLI to ingest Denver census tracts with geometry."""

from __future__ import annotations

import argparse
import gzip
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from whyline.ingest import io

# Denver open-data census tracts (2020) hosted on ArcGIS Online.
DEFAULT_SOURCE_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/" "TIGERweb/Tracts_Blocks/MapServer/0"
)
DEFAULT_STATE_FIPS = "08"
DEFAULT_COUNTY_FIPS = "031"

OUTPUT_FILENAME = "tracts.csv.gz"
COLUMNS = ["geoid", "name", "aland_m2", "awater_m2", "geometry_geojson"]

LOGGER = io.get_logger(__name__)

GEOID_CANDIDATES = ["GEOID", "GEOID20", "geoid", "GEOID10"]
NAME_CANDIDATES = ["NAME", "NAMELSAD", "NAMELSAD20", "name"]
ALAND_CANDIDATES = ["ALAND", "ALAND20", "AREA_LAND", "AREALAND"]
AWATER_CANDIDATES = ["AWATER", "AWATER20", "AREA_WATER", "AREAWATER"]
STATE_CANDIDATES = ["STATEFP", "STATEFP20", "STATE", "STATE_FIPS"]
COUNTY_CANDIDATES = ["COUNTYFP", "COUNTYFP20", "COUNTY", "COUNTY_FIPS"]


def run(args: argparse.Namespace) -> int:
    if args.mode == "gcs" and not args.bucket:
        raise SystemExit("--bucket is required when using --gcs")

    extract_date = args.extract_date or date.today().isoformat()
    _validate_iso_date(extract_date, "--extract-date")

    if args.mode == "local":
        root: str | Path = Path("data/raw")
    else:
        bucket = args.bucket[5:] if args.bucket.startswith("gs://") else args.bucket
        root = f"gs://{bucket.strip('/')}/raw"

    date_dir = _join_path(root, "denver_tracts", f"extract_date={extract_date}")
    output_path = _join_path(date_dir, OUTPUT_FILENAME)

    if io.exists(output_path):
        if _output_has_records(output_path):
            LOGGER.info("Skipping ingest; %s already populated.", output_path)
            return 0
        LOGGER.warning("Existing output %s is empty; regenerating.", output_path)

    LOGGER.info(
        "Fetching tracts for state=%s county=%s from %s",
        args.state_fips,
        args.county_fips,
        args.source_url,
    )

    try:
        field_map = detect_field_mapping(
            source_url=args.source_url,
            timeout=args.timeout_sec,
        )
    except Exception as exc:  # pragma: no cover - metadata failure
        LOGGER.error("Unable to inspect tract layer metadata: %s", exc)
        return 1

    LOGGER.debug("Resolved field mapping: %s", field_map)

    try:
        features = list(
            fetch_features(
                source_url=args.source_url,
                state_fips=args.state_fips,
                county_fips=args.county_fips,
                timeout=args.timeout_sec,
                field_map=field_map,
            )
        )
    except Exception as exc:  # pragma: no cover - network failure path
        LOGGER.error("Failed to fetch remote tracts: %s", exc)
        return 1

    if not features:
        LOGGER.error(
            "No features returned for state=%s county=%s from %s. "
            "Verify the endpoint and query parameters.",
            args.state_fips,
            args.county_fips,
            args.source_url,
        )
        return 1

    LOGGER.info("Retrieved %d raw feature records.", len(features))

    records, stats = normalize_records(features, field_map)
    if not records:
        LOGGER.error("Normalized dataset is empty; aborting ingest.")
        return 1

    LOGGER.info("Normalized tracts: %d rows; missing_geom=%d", stats.total, stats.missing_geometry)

    df = pd.DataFrame(records, columns=COLUMNS)
    io.write_csv(df, output_path, compression="gzip")

    manifest = build_manifest(
        extract_date=extract_date,
        args=args,
        record_count=len(df),
        stats=stats,
        source_url=args.source_url,
        output_path=output_path,
    )
    io.write_manifest(_ensure_dir_target(date_dir), manifest)
    LOGGER.info("Wrote %d tracts to %s", len(df), output_path)
    return 0


def fetch_features(
    *,
    source_url: str,
    state_fips: str,
    county_fips: str,
    timeout: int,
    field_map: FieldMapping,
    page_size: int = 2000,
) -> list[dict[str, Any]]:
    """Paginate over the ArcGIS feature service and return raw feature dicts."""
    features: list[dict[str, Any]] = []
    offset = 0
    where_clause = "1=1"
    if field_map.state_field and field_map.county_field:
        where_clause = (
            f"{field_map.state_field}='{state_fips}' AND {field_map.county_field}='{county_fips}'"
        )

    base_params = {
        "where": where_clause,
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": 4326,
        "f": "json",
    }

    while True:
        params = {**base_params, "resultOffset": offset, "resultRecordCount": page_size}
        response = io.http_get_with_retry(
            f"{source_url}/query", params=params, timeout=timeout, logger=LOGGER
        )
        payload = response.json()
        if "error" in payload:
            LOGGER.warning(
                "Tract query error (code=%s): %s",
                payload["error"].get("code"),
                payload["error"].get("message"),
            )
            LOGGER.debug("Tract query details: %s", payload["error"].get("details"))
            break
        batch = payload.get("features") or []
        if not batch:
            break
        features.extend(batch)
        if not payload.get("exceededTransferLimit"):
            break
        offset += len(batch)

    # Defensive filter when layer-level filtering isn't available.
    if field_map.state_field and field_map.county_field:
        return features

    filtered: list[dict[str, Any]] = []
    for feature in features:
        attrs = feature.get("attributes") or {}
        if field_map.state_field and attrs.get(field_map.state_field) != state_fips:
            continue
        if field_map.county_field and attrs.get(field_map.county_field) != county_fips:
            continue
        filtered.append(feature)
    return filtered


@dataclass
class FieldMapping:
    geoid_field: str
    name_field: str
    aland_field: str | None
    awater_field: str | None
    state_field: str | None
    county_field: str | None


@dataclass
class Stats:
    total: int
    missing_geometry: int


def normalize_records(
    features: list[dict[str, Any]], field_map: FieldMapping
) -> tuple[list[dict[str, Any]], Stats]:
    """Convert raw ArcGIS features into flat CSV records."""
    records: list[dict[str, Any]] = []
    missing_geom = 0

    for feature in features:
        attrs = feature.get("attributes") or {}
        geoid = attrs.get(field_map.geoid_field)
        if not geoid:
            continue
        geometry = feature.get("geometry") or {}
        geometry_geojson = arcgis_geometry_to_geojson(geometry)
        if geometry_geojson is None:
            missing_geom += 1
            continue
        record = {
            "geoid": geoid,
            "name": attrs.get(field_map.name_field) or attrs.get(field_map.geoid_field),
            "aland_m2": attrs.get(field_map.aland_field) if field_map.aland_field else None,
            "awater_m2": attrs.get(field_map.awater_field) if field_map.awater_field else None,
            "geometry_geojson": geometry_geojson,
        }
        records.append(record)

    stats = Stats(total=len(records), missing_geometry=missing_geom)
    return records, stats


def arcgis_geometry_to_geojson(geometry: dict[str, Any]) -> str | None:
    """Convert an ArcGIS polygon geometry dict into a GeoJSON string."""
    rings = geometry.get("rings")
    if not rings:
        return None

    polygons: list[list[list[list[float]]]] = []
    current: list[list[list[float]]] | None = None
    for ring in rings:
        if len(ring) < 4:
            continue
        area = _ring_area(ring)
        is_outer = area <= 0 or current is None
        oriented_ring = _orient_ring(ring, area, is_outer)
        if is_outer:
            current = [oriented_ring]
            polygons.append(current)
        else:
            current.append(oriented_ring)

    if not polygons:
        return None

    if len(polygons) == 1:
        geo = {"type": "Polygon", "coordinates": polygons[0]}
    else:
        geo = {"type": "MultiPolygon", "coordinates": polygons}
    return json.dumps(geo, separators=(",", ":"))


def _ring_area(ring: list[list[float]]) -> float:
    """Compute planar area of a linear ring; sign indicates orientation."""
    area = 0.0
    for idx in range(len(ring) - 1):
        x1, y1 = ring[idx]
        x2, y2 = ring[idx + 1]
        area += (x1 * y2) - (x2 * y1)
    return area / 2.0


def _orient_ring(ring: list[list[float]], area: float, is_outer: bool) -> list[list[float]]:
    """Ensure outer rings are CCW and holes are CW."""
    if area == 0:
        return ring
    desired_sign = 1 if is_outer else -1
    if area * desired_sign < 0:
        oriented = list(reversed(ring))
        if oriented[0] != oriented[-1]:
            oriented.append(oriented[0])
        return oriented
    return ring


def build_manifest(
    *,
    extract_date: str,
    args: argparse.Namespace,
    record_count: int,
    stats: Stats,
    source_url: str,
    output_path: str | Path,
) -> dict[str, Any]:
    """Return manifest metadata for the current ingest."""
    return {
        "dataset": "denver_tracts",
        "extract_date": extract_date,
        "source_url": source_url,
        "state_fips": args.state_fips,
        "county_fips": args.county_fips,
        "record_count": record_count,
        "missing_geometry": stats.missing_geometry,
        "output": str(output_path),
        "generated_at": io.utc_now_iso(),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest Denver census tracts.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--local",
        dest="mode",
        action="store_const",
        const="local",
        help="Write outputs to data/raw (default).",
    )
    mode.add_argument(
        "--gcs",
        dest="mode",
        action="store_const",
        const="gcs",
        help="Write outputs to a GCS bucket.",
    )
    parser.set_defaults(mode="local")

    parser.add_argument("--bucket", help="Target GCS bucket when using --gcs.")
    parser.add_argument("--extract-date", help="Extraction date YYYY-MM-DD (defaults to today).")
    parser.add_argument(
        "--source-url",
        default=DEFAULT_SOURCE_URL,
        help="ArcGIS MapServer layer providing census tract polygons.",
    )
    parser.add_argument(
        "--state-fips", default=DEFAULT_STATE_FIPS, help="State FIPS code (default 08)."
    )
    parser.add_argument(
        "--county-fips", default=DEFAULT_COUNTY_FIPS, help="County FIPS code (default 031)."
    )
    parser.add_argument(
        "--timeout-sec", type=int, default=60, help="HTTP timeout when fetching data."
    )
    return parser


def _join_path(root: str | Path, *parts: str) -> str:
    root_str = str(root)
    if root_str.startswith("gs://"):
        return "/".join([root_str.rstrip("/"), *parts])
    return str(Path(root, *parts))


def _ensure_dir_target(path: str | Path) -> str | Path:
    if isinstance(path, str) and path.startswith("gs://"):
        return path
    Path(path).mkdir(parents=True, exist_ok=True)
    return path


def _output_has_records(path: str | Path) -> bool:
    target = str(path)
    if target.startswith("gs://"):
        return True
    path_obj = Path(target)
    if not path_obj.exists() or path_obj.stat().st_size == 0:
        return False
    try:
        with gzip.open(path_obj, "rt", encoding="utf-8") as handle:
            handle.readline()
            return bool(handle.readline())
    except OSError:
        return False


def detect_field_mapping(*, source_url: str, timeout: int) -> FieldMapping:
    """Inspect the layer to determine attribute field names."""
    params = {
        "where": "1=1",
        "outFields": "*",
        "returnGeometry": "false",
        "resultRecordCount": 1,
        "f": "json",
    }
    response = io.http_get_with_retry(
        f"{source_url}/query", params=params, timeout=timeout, logger=LOGGER
    )
    payload = response.json()
    features = payload.get("features") or []
    if not features:
        raise RuntimeError("Layer returned no rows for metadata inspection.")

    attrs: dict[str, Any] = features[0].get("attributes", {})
    if not attrs:
        raise RuntimeError("Layer feature missing attributes during inspection.")

    def pick(candidates: Sequence[str], *, required: bool) -> str | None:
        for candidate in candidates:
            if candidate in attrs:
                return candidate
        if required:
            raise RuntimeError(f"Unable to resolve required field from candidates: {candidates}")
        return None

    return FieldMapping(
        geoid_field=pick(GEOID_CANDIDATES, required=True),
        name_field=pick(NAME_CANDIDATES, required=True),
        aland_field=pick(ALAND_CANDIDATES, required=False),
        awater_field=pick(AWATER_CANDIDATES, required=False),
        state_field=pick(STATE_CANDIDATES, required=False),
        county_field=pick(COUNTY_CANDIDATES, required=False),
    )


def _validate_iso_date(value: str, flag: str) -> None:
    try:
        date.fromisoformat(value)
    except ValueError as exc:  # pragma: no cover - defensive validation
        raise SystemExit(f"{flag} must be YYYY-MM-DD: {exc}") from exc


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
