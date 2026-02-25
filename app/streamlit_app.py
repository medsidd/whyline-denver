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
import json

import streamlit as st
from PIL import Image

# Setup paths
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from whyline.config import settings
from whyline.llm import build_schema_brief
from whyline.sql_guardrails import GuardrailConfig

# Import components
from components import (
    branding,
    prebuilt_questions,
    question_input,
    results_viewer,
    sidebar,
    sql_editor,
)
from utils import widget_data, session

# ═══════════════════════════════════════════════════════════════════════════
# PAGE CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════
# Load favicon as PIL Image for better Streamlit compatibility
favicon_path = Path(__file__).parent / "assets" / "whylinedenver-logo@512.png"
page_icon = Image.open(favicon_path) if favicon_path.exists() else "🚌"

st.set_page_config(
    page_title=f"{branding.BRAND_NAME} | RTD Reliability Analytics",
    page_icon=page_icon,
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": "https://github.com/medsidd/whyline-denver",
        "Report a bug": "https://github.com/medsidd/whyline-denver/issues",
        "About": f"{branding.BRAND_NAME} - Ask questions about Denver transit in plain English",
    },
)

primary_domain = "https://www.whylinedenver.com"
app_url = f"{primary_domain}/app/"
docs_url = f"{primary_domain}/docs/"
data_url = f"{primary_domain}/data/"
brand_name = branding.BRAND_NAME
brand_tagline = branding.BRAND_TAGLINE
brand_primary_color = branding.BRAND_PRIMARY
primary_description = (
    f"{brand_name} — {brand_tagline}. Analyze Denver RTD transit reliability, delays, "
    "safety, and equity gaps. The app turns natural language questions into trusted SQL, "
    "streamlined charts, and downloadable datasets powered by DuckDB and BigQuery."
)
seo_keywords = [
    "WhyLine Denver",
    "whyline denver",
    "why line denver",
    "transit denver",
    "rtd denver",
    "Denver transit analytics",
    "RTD bus delays",
    "Denver public transportation",
    "Denver public transportation data",
    "transit reliability dashboard",
    "Denver bus equity analysis",
    "RTD real-time GTFS",
    "Denver transit maps",
    "Denver RTD data",
    "Denver bus tracking",
    "Denver transit reliability",
]
og_image_url = f"{primary_domain}/assets/og-image.png"  # Social media preview (1200x630)
logo_url = f"{primary_domain}/assets/whylinedenver-logo.svg"  # Google search logo
icon_png_url = f"{primary_domain}/assets/whylinedenver-logo@512.png"  # Favicon
mask_icon_url = f"{primary_domain}/assets/whylinedenver-pinned-tab.svg"  # Safari pinned tab icon

schema_organization = {
    "@context": "https://schema.org",
    "@type": "Organization",
    "name": brand_name,
    "url": primary_domain,
    "logo": logo_url,
    "description": primary_description,
    "sameAs": [
        "https://github.com/medsidd/whyline-denver",
        "https://medsidd.github.io/whyline-denver/",
    ],
    "founder": {
        "@type": "Person",
        "name": "Ahmed Siddiqui",
    },
    "areaServed": {
        "@type": "City",
        "name": "Denver",
        "address": {
            "@type": "PostalAddress",
            "addressLocality": "Denver",
            "addressRegion": "CO",
            "addressCountry": "US",
        },
    },
}

schema_web_site = {
    "@context": "https://schema.org",
    "@type": "WebSite",
    "name": brand_name,
    "url": primary_domain,
    "description": primary_description,
    "publisher": {"@type": "Organization", "name": brand_name, "logo": logo_url},
    "inLanguage": "en-US",
    "potentialAction": {
        "@type": "SearchAction",
        "target": f"{app_url}?q={{search_term_string}}",
        "query-input": "required name=search_term_string",
    },
}

schema_web_app = {
    "@context": "https://schema.org",
    "@type": "WebApplication",
    "name": brand_name,
    "url": app_url,
    "operatingSystem": "Web Browser",
    "applicationCategory": "BusinessApplication",
    "description": primary_description,
    "offers": {"@type": "Offer", "price": "0.00", "priceCurrency": "USD"},
}

schema_faq = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    "mainEntity": [
        {
            "@type": "Question",
            "name": "Is WhyLine Denver free to use?",
            "acceptedAnswer": {
                "@type": "Answer",
                "text": "Yes. The analytics app is completely free to use with no login required.",
            },
        },
        {
            "@type": "Question",
            "name": "Which transit data sources power WhyLine Denver?",
            "acceptedAnswer": {
                "@type": "Answer",
                "text": "The app blends RTD GTFS realtime feeds, schedule data, Denver crash records, sidewalk infrastructure, NOAA weather, and U.S. Census ACS demographics.",
            },
        },
        {
            "@type": "Question",
            "name": "Can I download the results?",
            "acceptedAnswer": {
                "@type": "Answer",
                "text": "Yes. Every query result can be exported as CSV from the Results panel for additional analysis.",
            },
        },
    ],
}

json_ld_payloads = "\n".join(
    f'<script type="application/ld+json">{json.dumps(obj, separators=(",", ":"))}</script>'
    for obj in (schema_organization, schema_web_site, schema_web_app, schema_faq)
)

seo_meta_tags = f"""
<!-- Primary Meta Tags -->
<title>{brand_name} | RTD Reliability Analytics</title>
<meta name="title" content="{brand_name} | RTD Reliability Analytics">
<meta name="description" content="{primary_description}">
<meta name="keywords" content="{', '.join(seo_keywords)}">
<meta name="author" content="{brand_name}">
<meta name="application-name" content="{brand_name}">
<meta name="robots" content="index, follow">
<meta name="language" content="English">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="{brand_primary_color}">
<link rel="canonical" href="{app_url}">
<link rel="alternate" href="{app_url}" hreflang="en-US">

<!-- Icons and Manifest -->
<link rel="icon" type="image/x-icon" href="{primary_domain}/favicon.ico">
<link rel="shortcut icon" type="image/x-icon" href="{primary_domain}/favicon.ico">
<link rel="icon" type="image/png" sizes="512x512" href="{icon_png_url}">
<link rel="mask-icon" href="{mask_icon_url}" color="#87a7b3">
<link rel="apple-touch-icon" href="{icon_png_url}">
<link rel="apple-touch-icon" sizes="512x512" href="{icon_png_url}">
<link rel="manifest" href="{primary_domain}/manifest.json">

<!-- Open Graph / Facebook -->
<meta property="og:type" content="website">
<meta property="og:url" content="{app_url}">
<meta property="og:title" content="{brand_name} | RTD Reliability Analytics">
<meta property="og:description" content="{primary_description}">
<meta property="og:image" content="{og_image_url}">
<meta property="og:image:alt" content="{brand_name} dashboard preview">
<meta property="og:image:type" content="image/png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:site_name" content="{brand_name}">
<meta property="og:locale" content="en_US">

<!-- Twitter -->
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:url" content="{app_url}">
<meta name="twitter:title" content="{brand_name} | RTD Reliability Analytics">
<meta name="twitter:description" content="{primary_description}">
<meta name="twitter:image" content="{og_image_url}">
<meta name="twitter:image:alt" content="{brand_name} dashboard preview">

<!-- Geo Tags -->
<meta name="geo.region" content="US-CO">
<meta name="geo.placename" content="Denver">
<meta name="geo.position" content="39.7392;-104.9903">
<meta name="ICBM" content="39.7392, -104.9903">

<!-- Apple Web App -->
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="{brand_name}">

{json_ld_payloads}
"""

st.markdown(seo_meta_tags, unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════
# INITIALIZATION
# ═══════════════════════════════════════════════════════════════════════════
branding.inject_custom_css()
branding.render_header()
session.initialize()

# Load allowed models and build guardrail config
models = widget_data.load_allowed_models()
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
