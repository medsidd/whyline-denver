"""Branding components: custom CSS, header, footer."""

from __future__ import annotations

import base64
import os
from pathlib import Path

import streamlit as st

# ═══════════════════════════════════════════════════════════════════════════
# BRAND IDENTITY - Vintage Transit Palette
# ═══════════════════════════════════════════════════════════════════════════
BRAND_PRIMARY = os.getenv("APP_PRIMARY_COLOR", "#87a7b3")  # Dusty Sky Blue
BRAND_ACCENT = os.getenv("APP_ACCENT_COLOR", "#d4a574")  # Vintage Gold
BRAND_SUCCESS = os.getenv("APP_SUCCESS_COLOR", "#a3b88c")  # Sage Green
BRAND_WARNING = os.getenv("APP_WARNING_COLOR", "#e8b863")  # Soft Amber
BRAND_ERROR = os.getenv("APP_ERROR_COLOR", "#c77f6d")  # Terra Cotta
BRAND_NAME = os.getenv("APP_BRAND_NAME", "WhyLine Denver")
BRAND_TAGLINE = os.getenv("APP_TAGLINE", "Ask anything about Denver transit — in your own words")

# Chart color palette (5-color sequential for data viz)
CHART_COLORS = [BRAND_PRIMARY, BRAND_SUCCESS, BRAND_ACCENT, BRAND_WARNING, BRAND_ERROR]


def inject_custom_css() -> None:
    """Apply heavy custom CSS to override Streamlit defaults and create retro aesthetic."""
    st.markdown(
        f"""
        <style>
        /* Import Google Fonts - Space Grotesk (headers) & Inter (body) */
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700;800&family=Inter:wght@300;400;500;600;700&display=swap');

        /* ═══ GLOBAL RESETS & BASE STYLES ═══ */
        html, body, [class*="css"] {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            color: #e8d5c4;
            background: #232129;
        }}

        /* Hide Streamlit branding */
        #MainMenu {{visibility: hidden;}}
        footer {{visibility: hidden;}}
        header {{visibility: hidden;}}

        /* Remove extra padding */
        .block-container {{
            padding-top: 2rem;
            padding-bottom: 2rem;
            max-width: 100%;
        }}

        /* ═══ TYPOGRAPHY - STRONGER RETRO ═══ */
        h1, h2, h3, h4, h5, h6 {{
            font-family: 'Space Grotesk', sans-serif !important;
            font-weight: 700;
            letter-spacing: -0.03em;
            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.3);
        }}

        h1 {{
            font-size: 3rem;
            color: {BRAND_PRIMARY};
            margin-bottom: 0.5rem;
            font-weight: 800;
        }}

        h2 {{
            font-size: 2rem;
            color: {BRAND_ACCENT};
            margin-top: 2rem;
            margin-bottom: 1rem;
            font-weight: 700;
        }}

        h3 {{
            font-size: 1.5rem;
            color: {BRAND_ACCENT};
            margin-top: 1.5rem;
            margin-bottom: 0.75rem;
            font-weight: 700;
        }}

        /* ═══ BUTTONS - MORE RETRO PUNCH ═══ */
        .stButton > button {{
            background: linear-gradient(135deg, {BRAND_PRIMARY} 0%, {BRAND_ACCENT} 100%);
            color: #1a171d;
            border: 3px solid rgba(255, 255, 255, 0.15);
            border-radius: 12px;
            padding: 0.75rem 2rem;
            font-family: 'Space Grotesk', sans-serif;
            font-weight: 700;
            font-size: 1.1rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            white-space: nowrap;
            transition: all 0.3s ease;
            box-shadow:
                0 6px 20px rgba(135, 167, 179, 0.3),
                inset 0 1px 0 rgba(255, 255, 255, 0.2);
        }}

        .stButton > button:hover {{
            transform: translateY(-3px);
            color: #0a0609 !important;
            box-shadow:
                0 10px 30px rgba(135, 167, 179, 0.5),
                inset 0 1px 0 rgba(255, 255, 255, 0.3);
            border-color: rgba(255, 255, 255, 0.3);
        }}

        .stButton > button:active {{
            transform: translateY(-1px);
            box-shadow:
                0 4px 12px rgba(135, 167, 179, 0.4),
                inset 0 1px 0 rgba(255, 255, 255, 0.2);
        }}

        /* Primary button (Generate SQL, Run Query) - EXTRA RETRO */
        .stButton > button[kind="primary"] {{
            background: linear-gradient(135deg, {BRAND_ACCENT} 0%, {BRAND_WARNING} 100%);
            color: #1a171d;
            font-weight: 800;
            border: 3px solid rgba(255, 255, 255, 0.25);
            box-shadow:
                0 8px 24px rgba(212, 165, 116, 0.4),
                inset 0 2px 0 rgba(255, 255, 255, 0.3),
                inset 0 -2px 0 rgba(0, 0, 0, 0.2);
        }}

        .stButton > button[kind="primary"]:hover {{
            box-shadow:
                0 12px 36px rgba(212, 165, 116, 0.6),
                inset 0 2px 0 rgba(255, 255, 255, 0.4),
                inset 0 -2px 0 rgba(0, 0, 0, 0.2);
        }}

        /* ═══ INPUT FIELDS - RETRO STYLE ═══ */
        .stTextInput > div > div > input,
        .stTextArea > div > div > textarea,
        .stSelectbox > div > div > select,
        .stMultiselect > div > div {{
            background-color: #322e38 !important;
            border: 3px solid #433f4c !important;
            border-radius: 10px !important;
            color: #e8d5c4 !important;
            font-family: 'Inter', sans-serif !important;
            font-weight: 500;
            transition: all 0.2s ease;
            box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.2);
        }}

        .stTextInput > div > div > input:focus,
        .stTextArea > div > div > textarea:focus {{
            border-color: {BRAND_PRIMARY} !important;
            box-shadow:
                0 0 0 4px rgba(135, 167, 179, 0.2) !important,
                inset 0 2px 4px rgba(0, 0, 0, 0.2) !important;
        }}

        /* ═══ SIDEBAR - CONSISTENT INPUT STYLING ═══ */
        [data-testid="stSidebar"] {{
            background-color: #1a171d;
            border-right: 1px solid #433f4c;
        }}

        [data-testid="stSidebar"] h2 {{
            color: {BRAND_ACCENT};
            font-size: 1.5rem;
            margin-bottom: 1.5rem;
        }}

        /* Make all sidebar inputs look like text boxes */
        [data-testid="stSidebar"] .stSelectbox > div > div,
        [data-testid="stSidebar"] .stMultiSelect > div > div,
        [data-testid="stSidebar"] .stDateInput > div > div,
        [data-testid="stSidebar"] .stTextInput > div > div {{
            background-color: #322e38 !important;
        }}

        [data-testid="stSidebar"] .stSelectbox > div > div > div,
        [data-testid="stSidebar"] .stMultiSelect > div > div > div,
        [data-testid="stSidebar"] .stDateInput > div > div > div,
        [data-testid="stSidebar"] .stTextInput > div > div > input {{
            background-color: #322e38 !important;
            border: 3px solid #433f4c !important;
            border-radius: 10px !important;
            color: #e8d5c4 !important;
            padding: 0.75rem 1rem !important;
            font-weight: 500 !important;
            box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.2) !important;
        }}

        /* Style the dropdown arrows and icons */
        [data-testid="stSidebar"] .stSelectbox svg,
        [data-testid="stSidebar"] .stMultiSelect svg,
        [data-testid="stSidebar"] .stDateInput svg {{
            color: {BRAND_PRIMARY} !important;
        }}

        /* Style multiselect tags */
        [data-testid="stSidebar"] .stMultiSelect span[data-baseweb="tag"] {{
            background-color: {BRAND_PRIMARY} !important;
            color: #1a171d !important;
            border-radius: 6px !important;
            padding: 0.25rem 0.5rem !important;
            font-weight: 600 !important;
        }}

        /* Radio buttons */
        [data-testid="stSidebar"] .stRadio > div {{
            background-color: #322e38 !important;
            border: 3px solid #433f4c !important;
            border-radius: 10px !important;
            padding: 0.75rem 1rem !important;
            box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.2) !important;
        }}

        /* ═══ METRICS & STATUS ═══ */
        .stAlert {{
            border-radius: 8px;
            border-left: 4px solid;
            font-family: 'Inter', sans-serif;
        }}

        .stSuccess {{
            background-color: rgba(163, 184, 140, 0.1);
            border-left-color: {BRAND_SUCCESS};
            color: {BRAND_SUCCESS};
        }}

        .stWarning {{
            background-color: rgba(232, 184, 99, 0.1);
            border-left-color: {BRAND_WARNING};
            color: {BRAND_WARNING};
        }}

        .stError {{
            background-color: rgba(199, 127, 109, 0.1);
            border-left-color: {BRAND_ERROR};
            color: {BRAND_ERROR};
        }}

        .stInfo {{
            background-color: rgba(135, 167, 179, 0.1);
            border-left-color: {BRAND_PRIMARY};
            color: {BRAND_PRIMARY};
        }}

        /* ═══ DATAFRAMES ═══ */
        .stDataFrame {{
            border-radius: 8px;
            overflow: hidden;
        }}

        /* ═══ EXPANDERS ═══ */
        .streamlit-expanderHeader {{
            background-color: #322e38;
            border-radius: 8px;
            font-family: 'Space Grotesk', sans-serif;
            font-weight: 500;
            color: {BRAND_ACCENT};
        }}

        /* ═══ DIVIDERS ═══ */
        hr {{
            border-color: #433f4c;
            margin: 2rem 0;
        }}

        /* ═══ CODE BLOCKS (SQL) ═══ */
        code {{
            background-color: #1a171d;
            color: {BRAND_SUCCESS};
            padding: 0.2rem 0.4rem;
            border-radius: 4px;
            font-family: 'JetBrains Mono', 'Courier New', monospace;
        }}

        pre {{
            background-color: #1a171d;
            border: 1px solid #433f4c;
            border-radius: 8px;
            padding: 1rem;
        }}

        /* ═══ DOWNLOAD BUTTON ═══ */
        .stDownloadButton > button {{
            background-color: #322e38;
            color: {BRAND_SUCCESS};
            border: 2px solid {BRAND_SUCCESS};
            border-radius: 8px;
            font-family: 'Space Grotesk', sans-serif;
            font-weight: 600;
            transition: all 0.3s ease;
        }}

        .stDownloadButton > button:hover {{
            background-color: {BRAND_SUCCESS};
            color: #232129;
        }}

        /* ═══ RADIO BUTTONS ═══ */
        .stRadio > label {{
            font-family: 'Space Grotesk', sans-serif;
            font-weight: 500;
            color: {BRAND_ACCENT};
        }}

        /* ═══ MULTISELECT TAGS ═══ */
        .stMultiselect span[data-baseweb="tag"] {{
            background-color: {BRAND_PRIMARY} !important;
            color: #232129 !important;
            font-weight: 500;
        }}

        /* ═══ CAPTIONS ═══ */
        .caption {{
            color: #9a8e7e;
            font-size: 0.875rem;
        }}

        /* ═══ HIDE HEADER ANCHOR LINKS ═══ */
        /* Remove Streamlit's automatic header anchor/clip icons */
        h1 a, h2 a, h3 a, h4 a, h5 a, h6 a {{
            display: none !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header() -> None:
    """Render custom header with logo and tagline - ENHANCED RETRO VERSION."""
    logo_path = Path(__file__).parent.parent / "assets" / "whylinedenver-logo@512.png"

    # Retro rainbow stripe gradient
    stripe_gradient = f"linear-gradient(90deg, {BRAND_PRIMARY} 0%, {BRAND_ACCENT} 25%, {BRAND_SUCCESS} 50%, {BRAND_WARNING} 75%, {BRAND_ERROR} 100%)"

    if logo_path.exists():
        # Encode logo as base64 for embedding
        with open(logo_path, "rb") as f:
            logo_data = base64.b64encode(f.read()).decode()

        # Create image element (no animation)
        img_element = f'<img src="data:image/png;base64,{logo_data}" style="height: 140px; width: auto; filter: drop-shadow(0 6px 16px rgba(0,0,0,0.5));" />'
    else:
        # Fallback: no image
        img_element = ""

    st.markdown(
        f"""
        <div style="display: flex; align-items: center; gap: 2.5rem; margin-bottom: 2.5rem; padding: 2.5rem;
                    background: linear-gradient(135deg, rgba(135, 167, 179, 0.15) 0%, rgba(212, 165, 116, 0.12) 100%);
                    border-radius: 16px;
                    border: 4px solid rgba(135, 167, 179, 0.3);
                    box-shadow: 0 10px 40px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.1);
                    position: relative;
                    overflow: hidden;">
            <div style="position: absolute; top: 0; left: 0; right: 0; height: 6px; background: {stripe_gradient};"></div>
            {img_element}
            <div>
                <h1 style="margin: 0; font-size: 3.5rem; font-weight: 800;
                           background: linear-gradient(135deg, {BRAND_PRIMARY} 0%, {BRAND_ACCENT} 100%);
                           -webkit-background-clip: text;
                           -webkit-text-fill-color: transparent;
                           background-clip: text;
                           letter-spacing: -0.03em;
                           line-height: 1.1;">
                    {BRAND_NAME}
                </h1>
                <p style="margin: 0.75rem 0 0 0; color: {BRAND_ACCENT}; font-size: 1.3rem;
                          font-weight: 500; letter-spacing: 0.02em;">
                    {BRAND_TAGLINE}
                </p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_footer() -> None:
    """Render footer with branding and attributions."""
    st.markdown("---")
    st.markdown(
        f"""
        <div style="text-align: center; padding: 2rem 0; color: #9a8e7e; font-size: 0.9rem;">
            <p style="margin-bottom: 0.5rem;">
                <strong style="color: {BRAND_PRIMARY};">{BRAND_NAME}</strong> —
                Built with <span style="color: {BRAND_ACCENT};">♥</span> using dbt, DuckDB, BigQuery, and Streamlit
            </p>
            <p style="margin-bottom: 0.5rem; font-size: 0.85rem;">
                Data sources:
                <a href="https://www.rtd-denver.com/open-records" target="_blank" style="color: {BRAND_PRIMARY};">RTD GTFS</a> •
                <a href="https://www.denvergov.org/opendata/terms" target="_blank" style="color: {BRAND_PRIMARY};">Denver Open Data</a> •
                <a href="https://www.ncei.noaa.gov/" target="_blank" style="color: {BRAND_PRIMARY};">NOAA</a> •
                <a href="https://www.census.gov/" target="_blank" style="color: {BRAND_PRIMARY};">U.S. Census</a>
            </p>
            <p style="margin-bottom: 0; font-size: 0.85rem;">
                <a href="https://github.com/medsidd/whyline-denver" target="_blank" style="color: {BRAND_ACCENT};">View on GitHub</a> •
                <a href="https://medsidd.github.io/whyline-denver/" target="_blank" style="color: {BRAND_ACCENT};">dbt Docs</a>
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
