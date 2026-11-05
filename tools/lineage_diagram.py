"""Write docs/diagrams/data_model_overview.mmd from a dbt manifest.

Usage: python -m tools.lineage_diagram <manifest.json> [output.mmd]

Bronze lists the raw sources at least one enabled model reads; edges come from each model's
source() and ref() calls.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

LAYERS = (
    ("silver", "Silver: stg_denver", "staging"),
    ("gold_core", "Gold core: core_denver (Kimball)", "core"),
    ("gold_serving", "Gold serving: mart_denver", "marts"),
)


def render(manifest: dict) -> str:
    models = {
        node["unique_id"]: node
        for node in manifest["nodes"].values()
        if node["resource_type"] == "model" and node["config"].get("enabled", True)
    }
    sources = manifest["sources"]
    name = {uid: node["name"] for uid, node in models.items()}
    name.update({uid: src["name"] for uid, src in sources.items()})
    edges = sorted(
        {
            f"{name[dep]} --> {node['name']}"
            for node in models.values()
            for dep in node["depends_on"]["nodes"]
            if dep in name
        }
    )
    bronze = sorted(
        {
            sources[dep]["name"]
            for node in models.values()
            for dep in node["depends_on"]["nodes"]
            if dep in sources
        }
    )
    lines = [
        "flowchart LR",
        "  accTitle: Current dbt model lineage",
        f"  accDescr: {len(bronze)} bronze tables and {len(models)} SQL models in silver, gold-core, "
        "and gold-serving layers, with edges extracted from source and ref calls.",
        '  subgraph bronze["Bronze: raw_denver"]',
        "    direction TB",
        *(f'    {t}["{t}"]' for t in bronze),
        "  end",
    ]
    for key, label, folder in LAYERS:
        members = sorted(n["name"] for n in models.values() if n["fqn"][1] == folder)
        lines += [f'  subgraph {key}["{label}"]', "    direction TB"]
        lines += [f'    {m}["{m}"]' for m in members] + ["  end"]
    lines += [f"  {edge}" for edge in edges]
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    manifest = json.loads(Path(argv[0]).read_text())
    out = Path(argv[1]) if len(argv) > 1 else Path("docs/diagrams/data_model_overview.mmd")
    out.write_text(render(manifest))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
