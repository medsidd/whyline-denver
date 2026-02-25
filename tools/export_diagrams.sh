#!/usr/bin/env bash
set -euo pipefail

# Export draw.io diagrams to SVG and PNG
# Usage: ./scripts/export_diagrams.sh

DIAGRAMS_DIR="docs/diagrams"
EXPORTS_DIR="${DIAGRAMS_DIR}/exports"
DRAWIO_CLI="${DRAWIO_CLI:-drawio}"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}WhyLine Denver - Diagram Export Script${NC}"
echo "=========================================="
echo ""

# Check if draw.io CLI is available
if ! command -v "${DRAWIO_CLI}" &> /dev/null; then
    echo -e "${YELLOW}⚠️  draw.io CLI not found.${NC}"
    echo ""
    echo "Please install draw.io CLI to use automated export:"
    echo ""
    echo "  macOS:   brew install --cask drawio"
    echo "  Linux:   Download from https://github.com/jgraph/drawio-desktop/releases"
    echo ""
    echo "Or export manually using app.diagrams.net:"
    echo "  See docs/diagrams/EXPORT_INSTRUCTIONS.md for details"
    echo ""
    exit 1
fi

echo -e "${GREEN}✓ draw.io CLI found: $(which ${DRAWIO_CLI})${NC}"
echo ""

# Create exports directory
mkdir -p "${EXPORTS_DIR}"

# List of diagrams to export
DIAGRAMS=(
    "pipeline"
    "app_guardrails"
    "data_lineage_comprehensive"
    "reliability_domain_lineage"
    "safety_domain_lineage"
    "equity_domain_lineage"
    "access_domain_lineage"
)

# Export each diagram
for diagram in "${DIAGRAMS[@]}"; do
    SOURCE_FILE="${DIAGRAMS_DIR}/${diagram}.drawio"

    if [ ! -f "${SOURCE_FILE}" ]; then
        echo -e "${RED}✗ Source file not found: ${SOURCE_FILE}${NC}"
        continue
    fi

    echo -e "${BLUE}Exporting: ${diagram}${NC}"

    # Export to SVG
    echo "  → SVG..."
    "${DRAWIO_CLI}" --export \
        --format svg \
        --transparent \
        --embed-svg-images \
        --output "${EXPORTS_DIR}/${diagram}.svg" \
        "${SOURCE_FILE}"

    # Export to PNG
    echo "  → PNG..."
    "${DRAWIO_CLI}" --export \
        --format png \
        --width 2000 \
        --transparent \
        --border 10 \
        --output "${EXPORTS_DIR}/${diagram}.png" \
        "${SOURCE_FILE}"

    echo -e "${GREEN}  ✓ Exported${NC}"
    echo ""
done

echo ""
echo -e "${GREEN}=========================================="
echo "✓ Export complete!${NC}"
echo ""
echo "Exported files:"
ls -lh "${EXPORTS_DIR}"
echo ""
echo "Next steps:"
echo "  1. Review exported images in ${EXPORTS_DIR}/"
echo "  2. Commit to git: git add ${EXPORTS_DIR}/*.svg ${EXPORTS_DIR}/*.png"
echo "  3. Verify in README and ARCHITECTURE.md"
echo ""
