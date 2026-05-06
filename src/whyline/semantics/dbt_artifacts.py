from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable

from whyline.config import Settings
from whyline.sync.constants import (
    DOWNLOAD_MARTS,
    GUARDRAIL_MARTS,
    MART_BY_NAME,
    MART_REGISTRY,
    PROMPT_MARTS,
)

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class ColumnInfo:
    type: str | None
    description: str | None


@dataclass(slots=True)
class RelationshipHint:
    to_model: str
    join_on: str


@dataclass(slots=True)
class ModelInfo:
    name: str
    fq_name: str
    description: str | None
    layer: str | None = None  # "dim" | "fct" | "agg" | "mart"
    columns: Dict[str, ColumnInfo] = field(default_factory=dict)
    relationships: list[RelationshipHint] = field(default_factory=list)


class DbtArtifacts:
    """Load dbt manifest + catalog for registry-driven model sets."""

    def __init__(
        self, target_path: Path | str = "dbt/target", settings: Settings | None = None
    ) -> None:
        self.target_path = Path(target_path)
        self.settings = settings or Settings()
        self._manifest: dict[str, Any] | None = None
        self._catalog: dict[str, Any] | None = None
        self._all_models_cache: dict[str, ModelInfo] | None = None

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

    def _all_models(self) -> dict[str, ModelInfo]:
        """Load every model from manifest that appears in MART_BY_NAME.

        No allow_in_app filter — filtering is done by the caller via the
        three public methods below. Registry entries absent from the manifest
        are skipped with a warning (phased rollout; absent = not yet built).
        """
        if self._all_models_cache is not None:
            return self._all_models_cache

        manifest_nodes = self.manifest.get("nodes", {})
        catalog_nodes = self.catalog.get("nodes", {})
        catalog_by_name = {k.split(".")[-1]: v for k, v in catalog_nodes.items()}

        models: dict[str, ModelInfo] = {}
        registry_names = set(MART_BY_NAME.keys())

        for unique_id, node in manifest_nodes.items():
            if not unique_id.startswith("model."):
                continue
            model_name = node.get("name")
            if model_name not in registry_names:
                continue
            models[model_name] = self._build_model_info(node, catalog_by_name.get(model_name))

        missing = registry_names - set(models.keys())
        if missing:
            LOGGER.warning(
                "Registry entries absent from manifest (not yet built): %s",
                ", ".join(sorted(missing)),
            )

        self._all_models_cache = models
        return models

    def validate_registry_completeness(self) -> None:
        """Fail at startup if any prompt/sql model is absent from the manifest.

        Called only when STRICT_MODEL_VALIDATION=1 (Phase 5 cutover and beyond).
        """
        manifest_names = set(self._all_models().keys())
        required = {e.name for e in MART_REGISTRY if e.allow_prompt or e.allow_sql}
        missing = required - manifest_names
        if missing:
            raise RuntimeError(
                f"STRICT_MODEL_VALIDATION: required models absent from manifest: "
                f"{', '.join(sorted(missing))}. Run `dbt run` to build missing models."
            )

    def prompt_models(self) -> dict[str, ModelInfo]:
        """Models for LLM schema brief: allow_prompt=True, not deprecated."""
        prompt_set = set(PROMPT_MARTS)
        return {n: m for n, m in self._all_models().items() if n in prompt_set}

    def sql_models(self) -> dict[str, ModelInfo]:
        """Models for guardrails + BQ qualification: allow_sql=True (includes deprecated)."""
        guardrail_set = set(GUARDRAIL_MARTS)
        return {n: m for n, m in self._all_models().items() if n in guardrail_set}

    def download_models(self) -> dict[str, ModelInfo]:
        """Models for /api/downloads/options: allow_download=True, not deprecated."""
        download_set = set(DOWNLOAD_MARTS)
        return {n: m for n, m in self._all_models().items() if n in download_set}

    def allowed_models(self) -> dict[str, ModelInfo]:
        """Alias for sql_models() — retained for transition compatibility."""
        return self.sql_models()

    def _build_model_info(
        self, manifest_node: dict[str, Any], catalog_entry: dict[str, Any] | None
    ) -> ModelInfo:
        model_name = manifest_node.get("name")
        relation_name = manifest_node.get("relation_name")
        fq_name = relation_name or model_name
        if relation_name and relation_name.startswith("`") and relation_name.endswith("`"):
            fq_name = relation_name.strip("`")

        config_meta = manifest_node.get("config", {}).get("meta", {}) or {}

        # layer: YAML meta.layer is authoritative; registry is fallback for compat views
        layer = config_meta.get("layer")
        if not layer and model_name in MART_BY_NAME:
            layer = MART_BY_NAME[model_name].layer

        # relationships: read from meta.relationships list
        raw_rels = config_meta.get("relationships") or []
        relationships = [
            RelationshipHint(to_model=r["to"], join_on=r["join_on"])
            for r in raw_rels
            if isinstance(r, dict) and r.get("to") and r.get("join_on")
        ]

        columns = self._extract_columns(manifest_node, catalog_entry)
        description = manifest_node.get("description")
        return ModelInfo(
            name=model_name,
            fq_name=fq_name,
            description=description,
            layer=layer,
            columns=columns,
            relationships=relationships,
        )

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


__all__ = ["DbtArtifacts", "ModelInfo", "ColumnInfo", "RelationshipHint"]
