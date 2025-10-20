import gzip
import json
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


def _load_manifest(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_csv_gz(path: Path) -> pd.DataFrame:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return pd.read_csv(handle)


def test_manifests_align_with_csv():
    datasets = [
        {
            "label": "rtd_gtfsrt",
            "bases": [Path("data/raw/rtd_gtfsrt"), FIXTURES_ROOT / "rtd_gtfsrt"],
            "files": ["trip_updates.csv.gz", "vehicle_positions.csv.gz"],
        },
        {
            "label": "denver_crashes",
            "bases": [Path("data/raw/denver_crashes"), FIXTURES_ROOT / "denver_crashes"],
            "files": ["crashes.csv.gz"],
        },
        {
            "label": "denver_sidewalks",
            "bases": [Path("data/raw/denver_sidewalks"), FIXTURES_ROOT / "denver_sidewalks"],
            "files": ["sidewalks.csv.gz"],
        },
        {
            "label": "noaa_daily",
            "bases": [Path("data/raw/noaa_daily"), FIXTURES_ROOT / "noaa_daily"],
            "files": ["weather.csv.gz"],
        },
        {
            "label": "acs",
            "bases": [Path("data/raw/acs"), FIXTURES_ROOT / "acs"],
            "files": ["acs_tract.csv.gz"],
        },
    ]

    for ds in datasets:
        latest = _latest_partition(*ds["bases"])
        manifest = _load_manifest(latest / "manifest.json")
        files_meta = manifest.get("files", {})
        assert files_meta, f"Manifest missing files block for {ds['label']}"

        for filename in ds["files"]:
            csv_path = latest / filename
            assert csv_path.exists(), f"CSV missing: {csv_path}"
            df = _load_csv_gz(csv_path)
            actual_rows = len(df)

            meta = files_meta.get(filename)
            assert meta is not None, f"Manifest missing entry for {filename}"
            assert "hash_md5" in meta and meta["hash_md5"], "Manifest missing hash"
            manifest_rows = int(meta.get("row_count", -1))
            assert manifest_rows == actual_rows
            assert actual_rows >= 0
