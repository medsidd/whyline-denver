"""ArcGIS reference layers: paging, weekly skip, failure isolation and the registry contract."""

from __future__ import annotations

import gzip
import io
import json
from unittest.mock import Mock

import pandas as pd

from whyline.ingest import arcgis_reference as ref
from whyline.load.registry import JOBS


def _server(features_by_layer: dict[str, list[dict]], calls: list):
    """Fake ArcGIS: counts, then pages of resultRecordCount from resultOffset."""

    def get(url, params=None, **kwargs):
        layer = next(n for n, spec in ref.LAYERS.items() if url == f"{spec.url}/query")
        calls.append((layer, params.get("resultOffset")))
        features = features_by_layer[layer]
        if params.get("returnCountOnly"):
            return Mock(json=lambda: {"count": len(features)})
        start = params["resultOffset"]
        return Mock(
            json=lambda: {"features": features[start : start + params["resultRecordCount"]]}
        )

    return get


def _features(n: int) -> list[dict]:
    return [
        {
            "type": "Feature",
            "id": i,
            "properties": {"OBJECTID": i, "Tier": "1", "StreetName": "Colfax Ave"},
            "geometry": {"type": "Point", "coordinates": [-104.99, 39.74]},
        }
        for i in range(1, n + 1)
    ]


def test_layers_page_and_match_the_registry(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ref, "PAGE_SIZE", 2)
    monkeypatch.setattr(
        ref, "LAYERS", {"denver_hin": ref.Layer(ref.LAYERS["denver_hin"].url, min_features=5)}
    )
    calls: list = []
    monkeypatch.setattr(ref.io, "http_get_with_retry", _server({"denver_hin": _features(5)}, calls))
    assert ref.main(["--local", "--extract-date", "2026-11-02"]) == 0
    assert [offset for _, offset in calls] == [None, 0, 2, 4]  # count, then three pages

    out = tmp_path / "data/raw/arcgis_reference/extract_date=2026-11-02"
    frame = pd.read_csv(
        io.StringIO(gzip.decompress((out / "denver_hin.csv.gz").read_bytes()).decode()), dtype=str
    )
    job = {j.table: j for j in JOBS}["raw_arcgis_reference"]
    assert "arcgis_reference/extract_date=*/*.csv.gz" in job.patterns
    assert list(frame.columns) == [c.name for c in job.columns]
    assert list(frame.object_id) == ["1", "2", "3", "4", "5"]
    assert json.loads(frame.properties_json[0])["StreetName"] == "Colfax Ave"
    assert json.loads(frame.geometry_geojson[0])["type"] == "Point"
    assert (
        json.loads((out / "manifest.json").read_text())["files"]["denver_hin.csv.gz"]["row_count"]
        == 5
    )

    # Within the week the layer is skipped, without a request.
    calls.clear()
    assert ref.main(["--local", "--extract-date", "2026-11-08"]) == 0
    assert calls == []
    assert ref.main(["--local", "--extract-date", "2026-11-09"]) == 0  # 7 days on: fetched again
    assert calls


def test_a_failing_layer_does_not_stop_the_others(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    layers = {
        "denver_hin": ref.Layer(ref.LAYERS["denver_hin"].url, min_features=3),
        "denver_transit_lanes": ref.Layer(ref.LAYERS["denver_transit_lanes"].url, min_features=1),
    }
    monkeypatch.setattr(ref, "LAYERS", layers)
    # The HIN returns too few features; transit lanes is fine.
    served = {"denver_hin": _features(2), "denver_transit_lanes": _features(1)}
    monkeypatch.setattr(ref.io, "http_get_with_retry", _server(served, []))
    assert ref.main(["--local", "--extract-date", "2026-11-02"]) == 1
    out = tmp_path / "data/raw/arcgis_reference/extract_date=2026-11-02"
    assert sorted(p.name for p in out.iterdir()) == ["denver_transit_lanes.csv.gz", "manifest.json"]


def test_a_layer_requests_only_its_fields(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    spec = ref.LAYERS["denver_sidewalk_assets"]
    monkeypatch.setattr(
        ref, "LAYERS", {"denver_sidewalk_assets": ref.Layer(spec.url, fields=spec.fields)}
    )
    requested = []

    def get(url, params=None, **kwargs):
        if params.get("returnCountOnly"):
            return Mock(json=lambda: {"count": 1})
        requested.append(params["outFields"])
        return Mock(json=lambda: {"features": _features(1)})

    monkeypatch.setattr(ref.io, "http_get_with_retry", get)
    assert ref.main(["--local", "--extract-date", "2026-11-07"]) == 0
    assert requested == [spec.fields] and "SIDEWALK_WIDTH" in spec.fields
