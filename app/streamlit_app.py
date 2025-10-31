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
    menu_items={
        "Get Help": "https://github.com/medsidd/whyline-denver",
        "Report a bug": "https://github.com/medsidd/whyline-denver/issues",
        "About": f"{branding.BRAND_NAME} - Ask questions about Denver transit in plain English",
    },
)

# ═══════════════════════════════════════════════════════════════════════════
# SEO OPTIMIZATION - Meta tags and structured data
# ═══════════════════════════════════════════════════════════════════════════
seo_meta_tags = """
<!-- Primary Meta Tags -->
<meta name="title" content="WhyLine Denver - Denver Transit Analytics & Real-Time Bus Data">
<meta name="description" content="Analyze Denver RTD bus data, delays, reliability, and equity gaps. Ask questions in plain English about transit reliability, crash exposure, weather impacts, and service quality.">
<meta name="keywords" content="Denver transit, RTD bus data, Denver public transportation, bus delays Denver, transit reliability, Denver RTD analytics, bus schedule Denver, transit equity, Denver transportation data, RTD real-time data">
<meta name="author" content="WhyLine Denver">
<meta name="robots" content="index, follow">
<meta name="language" content="English">
<link rel="canonical" href="https://www.whylinedenver.com/app/">

<!-- Open Graph / Facebook -->
<meta property="og:type" content="website">
<meta property="og:url" content="https://www.whylinedenver.com/">
<meta property="og:title" content="WhyLine Denver - Denver Transit Analytics">
<meta property="og:description" content="Analyze RTD bus reliability, delays, equity gaps, and service quality. Ask questions about Denver transit in plain English.">
<meta property="og:image" content="https://www.whylinedenver.com/assets/og-image.png">
<meta property="og:site_name" content="WhyLine Denver">

<!-- Twitter -->
<meta property="twitter:card" content="summary_large_image">
<meta property="twitter:url" content="https://www.whylinedenver.com/">
<meta property="twitter:title" content="WhyLine Denver - Denver Transit Analytics">
<meta property="twitter:description" content="Analyze RTD bus reliability, delays, equity gaps, and service quality with real-time data.">
<meta property="twitter:image" content="https://www.whylinedenver.com/assets/og-image.png">

<!-- Geo Tags -->
<meta name="geo.region" content="US-CO">
<meta name="geo.placename" content="Denver">
<meta name="geo.position" content="39.7392;-104.9903">
<meta name="ICBM" content="39.7392, -104.9903">

<!-- Schema.org structured data -->
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "WebApplication",
  "name": "WhyLine Denver",
  "url": "https://www.whylinedenver.com",
  "description": "Free analytics tool for Denver RTD transit data. Ask questions about bus reliability, delays, equity gaps, and service quality in plain English.",
  "applicationCategory": "Transportation Analytics",
  "operatingSystem": "Web Browser",
  "offers": {
    "@type": "Offer",
    "price": "0",
    "priceCurrency": "USD"
  },
  "provider": {
    "@type": "Organization",
    "name": "WhyLine Denver"
  },
  "areaServed": {
    "@type": "City",
    "name": "Denver",
    "address": {
      "@type": "PostalAddress",
      "addressLocality": "Denver",
      "addressRegion": "CO",
      "addressCountry": "US"
    }
  },
  "about": [
    {
      "@type": "Thing",
      "name": "Denver RTD Bus Service"
    },
    {
      "@type": "Thing",
      "name": "Public Transit Analytics"
    },
    {
      "@type": "Thing",
      "name": "Transportation Equity"
    }
  ]
}
</script>
"""

st.markdown(seo_meta_tags, unsafe_allow_html=True)

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
