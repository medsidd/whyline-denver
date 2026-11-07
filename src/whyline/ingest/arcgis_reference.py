"""CLI to snapshot reference layers from Denver's and CDPHE's ArcGIS services.

Street-safety layers (metrics WP7), the sidewalk asset inventory and equity layers (WP9) change rarely, so each layer is fetched
at most once a week: a layer is skipped when an extract from the last 7 days exists. Every layer
lands in one raw table with its attributes as JSON and its geometry as GeoJSON (WGS84); staging
picks the fields it needs, so a renamed source field doesn't break the load.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from whyline.ingest import io

DENVER = "https://services1.arcgis.com/zdB7qR0BtYrg0Xpl/arcgis/rest/services/"
CDPHE = "https://services3.arcgis.com/66aUo8zsujfVXRIT/arcgis/rest/services/"
DENVER_COUNTY = "GEOID LIKE '08031%'"


@dataclass(frozen=True)
class Layer:
    url: str
    where: str = "1=1"
    min_features: int = 1
    fields: str = "*"


# Counts on 2026-11-02 guard against an empty or truncated response.
LAYERS = {
    "denver_hin": Layer(DENVER + "ODC_TRANS_HIN_L/FeatureServer/326", min_features=400),
    "denver_transit_lanes": Layer(
        DENVER + "ODC_TRANS_TRANSITLANES_L/FeatureServer/349", min_features=20
    ),
    "denver_transit_signals": Layer(
        DENVER + "ODC_TRANS_TRANSITSIGNALS_P/FeatureServer/350", min_features=20
    ),
    "denver_curb_ramps": Layer(
        DENVER + "ODC_TRANS_CURBRAMPS_P/FeatureServer/228", min_features=60000
    ),
    "denver_traffic_signals": Layer(
        DENVER + "ODC_TRANS_TRAFFICSIGNAL_P/FeatureServer/147", min_features=1000
    ),
    "denver_bike_facilities": Layer(
        DENVER + "Denver_Bicycle_Facilities_ODC/FeatureServer/450", min_features=1500
    ),
    # Condition, width and missing frontage: the sidewalk layer (denver_sidewalks) leaves them empty.
    "denver_sidewalk_assets": Layer(
        DENVER + "ODC_ASSET_SIDEWALKS_L/FeatureServer/416",
        min_features=170000,
        fields="OBJECTID,SIDEWALK_TYPE,BASELINE_CONDITION,SIDEWALK_WIDTH,SurfaceType,DETACHED",
    ),
    "denver_doti_equity": Layer(
        DENVER + "ODC_ADMN_DOTI_EQUITY_INDEX/FeatureServer/151", min_features=500
    ),
    "enviroscreen_tract": Layer(
        CDPHE + "ColoradoEnviroScreen_v2_Tract_24118_Final/FeatureServer/0",
        where=DENVER_COUNTY,
        min_features=150,
    ),
    "enviroscreen_block_group": Layer(
        CDPHE + "EJP_Main_English_v2_BlockGroup_71124_Final_view/FeatureServer/0",
        where=DENVER_COUNTY,
        min_features=400,
    ),
}
COLUMNS = ["layer", "object_id", "properties_json", "geometry_geojson"]
PAGE_SIZE = 2000
REFRESH_DAYS = 7

LOGGER = io.get_logger(__name__)


def fetch_layer(layer: Layer, timeout: int) -> list[dict[str, Any]]:
    count = io.http_get_with_retry(
        f"{layer.url}/query",
        params={"where": layer.where, "returnCountOnly": "true", "f": "json"},
        timeout=timeout,
        logger=LOGGER,
    ).json()["count"]
    features: list[dict[str, Any]] = []
    while len(features) < count:
        page = io.http_get_with_retry(
            f"{layer.url}/query",
            params={
                "where": layer.where,
                "outFields": layer.fields,
                "outSR": 4326,
                "f": "geojson",
                "orderByFields": "OBJECTID",
                "resultOffset": len(features),
                "resultRecordCount": PAGE_SIZE,
            },
            timeout=timeout,
            logger=LOGGER,
        ).json()
        batch = page.get("features") or []
        if not batch:
            break
        features.extend(batch)
    if len(features) != count:
        raise RuntimeError(f"{layer.url}: got {len(features)} of {count} features")
    return features


def to_frame(name: str, features: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for f in features:
        props = f.get("properties") or {}
        object_id = f.get("id", props.get("OBJECTID", props.get("FID")))
        rows.append(
            [
                name,
                None if object_id is None else str(object_id),
                json.dumps(props, sort_keys=True, ensure_ascii=False),
                (
                    None
                    if f.get("geometry") is None
                    else json.dumps(f["geometry"], separators=(",", ":"))
                ),
            ]
        )
    return pd.DataFrame(rows, columns=COLUMNS)


def _path(root: Any, extract_date: str, name: str) -> Any:
    if isinstance(root, Path):
        return root / "arcgis_reference" / f"extract_date={extract_date}" / f"{name}.csv.gz"
    return f"{root}/arcgis_reference/extract_date={extract_date}/{name}.csv.gz"


def recently_extracted(root: Any, name: str, today: date) -> bool:
    return any(
        io.exists(_path(root, (today - timedelta(days=d)).isoformat(), name))
        for d in range(REFRESH_DAYS)
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
    names = args.layers.split(",") if args.layers else list(LAYERS)

    files: dict[str, dict[str, Any]] = {}
    failed = []
    for name in names:
        layer = LAYERS[name]
        if not args.force and recently_extracted(root, name, today):
            LOGGER.info("Skipping %s; extracted within %d days.", name, REFRESH_DAYS)
            continue
        try:
            df = to_frame(name, fetch_layer(layer, args.timeout_sec))
            if len(df) < layer.min_features:
                raise RuntimeError(
                    f"only {len(df)} features, expected at least {layer.min_features}"
                )
        except Exception as exc:  # one broken layer must not stop the others
            LOGGER.warning("ARCGIS_LAYER_FAILED %s: %s", name, exc)
            failed.append(name)
            continue
        path = _path(root, today.isoformat(), name)
        io.write_csv(df, path)
        files[f"{name}.csv.gz"] = {
            "path": str(path),
            "row_count": int(len(df)),
            "source": layer.url,
        }
        LOGGER.info("Wrote %s: %d features.", name, len(df))

    if files:
        io.write_manifest(  # next to the files written this run
            next(iter(files.values()))["path"],
            {"extract_date": today.isoformat(), "files": files, "written_at_utc": io.utc_now_iso()},
        )
    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Snapshot ArcGIS reference layers weekly.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--local", dest="mode", action="store_const", const="local")
    mode.add_argument("--gcs", dest="mode", action="store_const", const="gcs")
    parser.set_defaults(mode="local")
    parser.add_argument("--bucket", help="GCS bucket name (required with --gcs).")
    parser.add_argument("--extract-date", help="Override today's date (YYYY-MM-DD).")
    parser.add_argument("--layers", help=f"Comma-separated subset of: {', '.join(LAYERS)}.")
    parser.add_argument("--force", action="store_true", help="Fetch even if extracted this week.")
    parser.add_argument("--timeout-sec", type=int, default=60)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
