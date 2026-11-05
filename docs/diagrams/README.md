# Current diagrams

| Source | Purpose |
|---|---|
| [pipeline.mmd](pipeline.mmd) | Current ingestion, storage, transformation, serving, and orchestration boundaries |
| [app_guardrails.mmd](app_guardrails.mmd) | SQL generation, editing, validation, execution, and display |
| [data_model_overview.mmd](data_model_overview.mmd) | Lineage of every enabled model, reconciled to current SQL `ref()`/`source()` calls and raw registry; the three legacy models disabled at the stop-visit cutover are omitted |

The seven older draw.io diagrams and their fourteen SVG/PNG exports were removed because they duplicated each other and showed removed models, Streamlit/Hugging Face hosting, obsolete schedules, and an obsolete DuckDB hot/cold split. Useful domain logic is in the current model lineage and [metrics glossary](../public/METRICS_GLOSSARY.md).

Mermaid source is authoritative. After model changes, regenerate the lineage from a fresh parse:

```bash
dbt parse --project-dir dbt --target-path /tmp/whyline-parse --no-partial-parse
python -m tools.lineage_diagram /tmp/whyline-parse/manifest.json
```

The generator lists the raw sources at least one enabled model reads, every enabled model by layer, and one edge per `source()` or `ref()` call. On 2026-11-02 it reproduced the committed diagram from `main` exactly. Planned models never appear, because only parsed SQL is drawn. `pipeline.mmd` and `app_guardrails.mmd` are still edited by hand.

For optional SVG/PNG exports, provide an installed [Mermaid CLI](https://github.com/mermaid-js/mermaid-cli) (`mmdc`) and run from the repository root:

```bash
make export-diagrams
```

The script exports every `.mmd` into `docs/diagrams/exports/`, stops on rendering errors, and does not install packages or download tools. `MERMAID_CLI` can select a different installed executable. Generated exports are for sharing and must be regenerated after source changes; this repository keeps the editable sources instead of stale checked-in render copies.
