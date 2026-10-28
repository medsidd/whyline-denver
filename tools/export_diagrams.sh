#!/usr/bin/env bash
# Export current Mermaid sources; run from the repository root.
set -euo pipefail

MERMAID_CLI="${MERMAID_CLI:-mmdc}"
if ! command -v "$MERMAID_CLI" >/dev/null 2>&1; then
    echo "Mermaid CLI not found: $MERMAID_CLI. See docs/diagrams/README.md." >&2
    exit 1
fi

mkdir -p docs/diagrams/exports
for source in docs/diagrams/*.mmd; do
    name="$(basename "$source" .mmd)"
    for format in svg png; do
        "$MERMAID_CLI" -i "$source" -o "docs/diagrams/exports/$name.$format" -w 2400
    done
done
