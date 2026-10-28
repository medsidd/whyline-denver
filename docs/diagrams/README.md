# Current diagrams

| Source | Purpose |
|---|---|
| [pipeline.mmd](pipeline.mmd) | Current ingestion, storage, transformation, serving, and orchestration boundaries |
| [app_guardrails.mmd](app_guardrails.mmd) | SQL generation, editing, validation, execution, and display |
| [data_model_overview.mmd](data_model_overview.mmd) | Complete model lineage reconciled to current SQL `ref()`/`source()` calls and raw registry |

The seven older draw.io diagrams and their fourteen SVG/PNG exports were removed because they duplicated each other and showed removed models, Streamlit/Hugging Face hosting, obsolete schedules, and an obsolete DuckDB hot/cold split. Useful domain logic is in the current model lineage and [metrics glossary](../public/METRICS_GLOSSARY.md).

Mermaid source is authoritative. After model changes, check every node and dependency against `dbt/models/**/*.sql` and `src/whyline/load/registry.py`; do not add planned models to current lineage. Raw shapes are registered/loaded but currently have no dbt model consumer.

For optional SVG/PNG exports, provide an installed [Mermaid CLI](https://github.com/mermaid-js/mermaid-cli) (`mmdc`) and run from the repository root:

```bash
make export-diagrams
```

The script exports every `.mmd` into `docs/diagrams/exports/`, stops on rendering errors, and does not install packages or download tools. `MERMAID_CLI` can select a different installed executable. Generated exports are for sharing and must be regenerated after source changes; this repository keeps the editable sources instead of stale checked-in render copies.
