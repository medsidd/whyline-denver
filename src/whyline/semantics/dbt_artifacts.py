from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable

from whyline.config import Settings
from whyline.sync import ALLOWLISTED_MARTS


@dataclass(slots=True)
class ColumnInfo:
    type: str | None
    description: str | None


@dataclass(slots=True)
class ModelInfo:
    name: str
    fq_name: str
    description: str | None
    columns: Dict[str, ColumnInfo] = field(default_factory=dict)


class DbtArtifacts:
    """Load dbt manifest + catalog for allow-listed marts."""

    def __init__(
        self, target_path: Path | str = "dbt/target", settings: Settings | None = None
    ) -> None:
        self.target_path = Path(target_path)
        self.settings = settings or Settings()
        self._manifest: dict[str, Any] | None = None
        self._catalog: dict[str, Any] | None = None

    def load_artifacts(self) -> None:
        manifest_path = self.target_path / "manifest.json"
        catalog_path = self.target_path / "catalog.json"
        self._manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self._catalog = json.loads(catalog_path.read_text(encoding="utf-8"))

    @property
    def manifest(self) -> dict[str, Any]:
        if self._manifest is None:
            self.load_artifacts()
        assert self._manifest is not None
        return self._manifest

    @property
    def catalog(self) -> dict[str, Any]:
        if self._catalog is None:
            self.load_artifacts()
        assert self._catalog is not None
        return self._catalog

    def allowed_models(self) -> Dict[str, ModelInfo]:
        models: Dict[str, ModelInfo] = {}
        manifest_nodes = self.manifest.get("nodes", {})
        catalog_nodes = self.catalog.get("nodes", {})
        for unique_id, node in manifest_nodes.items():
            if not unique_id.startswith("model."):
                continue
            config_meta = node.get("config", {}).get("meta", {})
            if not config_meta.get("allow_in_app"):
                continue
            model_name = node.get("name")
            if ALLOWLISTED_MARTS and model_name not in ALLOWLISTED_MARTS:
                continue
            models[model_name] = self._build_model_info(node, catalog_nodes.get(unique_id))
        return models

    def _build_model_info(
        self, manifest_node: dict[str, Any], catalog_entry: dict[str, Any] | None
    ) -> ModelInfo:
        model_name = manifest_node.get("name")
        relation_name = manifest_node.get("relation_name")
        fq_name = relation_name or model_name
        if relation_name and relation_name.startswith("`") and relation_name.endswith("`"):
            fq_name = relation_name.strip("`")
        columns = self._extract_columns(manifest_node, catalog_entry)
        description = manifest_node.get("description")
        return ModelInfo(name=model_name, fq_name=fq_name, description=description, columns=columns)

    def _extract_columns(
        self,
        manifest_node: dict[str, Any],
        catalog_entry: dict[str, Any] | None,
    ) -> Dict[str, ColumnInfo]:
        manifest_columns = manifest_node.get("columns", {}) or {}
        catalog_columns = catalog_entry.get("columns", {}) if catalog_entry else {}

        column_names = self._merge_column_names(manifest_columns, catalog_columns)
        columns: Dict[str, ColumnInfo] = {}
        for col_name in column_names:
            manifest_col = manifest_columns.get(col_name, {})
            catalog_col = catalog_columns.get(col_name, {})
            columns[col_name] = ColumnInfo(
                type=catalog_col.get("type") or manifest_col.get("data_type"),
                description=manifest_col.get("description") or catalog_col.get("description"),
            )
        return columns

    @staticmethod
    def _merge_column_names(*column_dicts: Iterable[dict[str, Any]]) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        for columns in column_dicts:
            for name in columns:
                if name not in seen:
                    seen.add(name)
                    names.append(name)
        return names


__all__ = ["DbtArtifacts", "ModelInfo", "ColumnInfo"]
