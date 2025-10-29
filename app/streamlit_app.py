# ruff: noqa: E402,I001
"""
WhyLine Denver - Streamlit Application

A governed, dual-engine analytics experience where anyone can ask questions
in natural language and receive cost-capped SQL answers, visualizations,
and downloadable datasets.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Setup paths
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from whylinedenver.config import settings
from whylinedenver.llm import build_schema_brief
from whylinedenver.sql_guardrails import GuardrailConfig

# Import components
from components import (
    branding,
    prebuilt_questions,
    question_input,
    results_viewer,
    sidebar,
    sql_editor,
)
from utils import data_loaders, session

# ═══════════════════════════════════════════════════════════════════════════
# PAGE CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title=f"{branding.BRAND_NAME} — Transit Analytics",
    page_icon=str(Path(__file__).parent / "assets" / "favicon.ico"),
    layout="wide",
    initial_sidebar_state="expanded",
)

# ═══════════════════════════════════════════════════════════════════════════
# INITIALIZATION
# ═══════════════════════════════════════════════════════════════════════════
branding.inject_custom_css()
branding.render_header()
session.initialize()

# Load allowed models and build guardrail config
models = data_loaders.load_allowed_models()
allowlist = set(models.keys())

# Build allowed projects and datasets for BigQuery
_allowed_projects: set[str] = set()
_allowed_datasets: set[str] = set()
for info in models.values():
    parts = [segment.strip("`") for segment in info.fq_name.split(".") if segment]
    if len(parts) >= 3:
        _allowed_projects.add(parts[-3])
    if len(parts) >= 2:
        _allowed_datasets.add(parts[-2])
if not _allowed_projects and settings.GCP_PROJECT_ID:
    _allowed_projects.add(settings.GCP_PROJECT_ID)
if not _allowed_datasets and settings.BQ_DATASET_MART:
    _allowed_datasets.add(settings.BQ_DATASET_MART)


def build_guardrail_config(engine_name: str) -> GuardrailConfig:
    """Build guardrail configuration for the selected engine."""
    extra: dict[str, set[str]] = {}
    if engine_name == "bigquery":
        extra["allowed_projects"] = _allowed_projects
        extra["allowed_datasets"] = _allowed_datasets
    return GuardrailConfig(allowed_models=allowlist, engine=engine_name, **extra)


schema_brief = build_schema_brief(models)

# ═══════════════════════════════════════════════════════════════════════════
# SIDEBAR - Filters and Controls
# ═══════════════════════════════════════════════════════════════════════════
engine, filters = sidebar.render()
guardrail_config = build_guardrail_config(engine)

# ═══════════════════════════════════════════════════════════════════════════
# MAIN CONTENT
# ═══════════════════════════════════════════════════════════════════════════

# Prebuilt Questions
prebuilt_questions.render(engine, models, guardrail_config)

# Step 1: Ask Your Question
question = question_input.render(engine, filters, schema_brief, models, guardrail_config)

# Step 2: Review & Edit SQL
sql_editor.render(engine, models, guardrail_config)

# Step 3: Results
results_viewer.render(engine, question, models, guardrail_config, allowlist)

# ═══════════════════════════════════════════════════════════════════════════
# FOOTER
# ═══════════════════════════════════════════════════════════════════════════
branding.render_footer()
