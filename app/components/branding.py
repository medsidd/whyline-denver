"""Branding components: custom CSS, header, footer."""

from __future__ import annotations

import base64
import json
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
BRAND_TAGLINE = os.getenv("APP_TAGLINE", "Ask anything about Denver transit")
PRIMARY_DOMAIN = os.getenv("APP_PRIMARY_DOMAIN", "https://www.whylinedenver.com")
FAVICON_ICO_URL = f"{PRIMARY_DOMAIN}/favicon.ico"
FAVICON_PNG_512_URL = f"{PRIMARY_DOMAIN}/assets/whylinedenver-logo@512.png"
APPLE_TOUCH_ICON_URL = f"{PRIMARY_DOMAIN}/assets/apple-touch-icon.png"
MASK_ICON_URL = f"{PRIMARY_DOMAIN}/assets/whylinedenver-pinned-tab.svg"

STRIPE_GRADIENT = (
    f"linear-gradient(90deg, {BRAND_PRIMARY} 0%, {BRAND_ACCENT} 25%, "
    f"{BRAND_SUCCESS} 50%, {BRAND_WARNING} 75%, {BRAND_ERROR} 100%)"
)

# Chart color palette (5-color sequential for data viz)
CHART_COLORS = [BRAND_PRIMARY, BRAND_SUCCESS, BRAND_ACCENT, BRAND_WARNING, BRAND_ERROR]


def inject_custom_css() -> None:
    """Apply heavy custom CSS to override Streamlit defaults and create retro aesthetic."""
    favicon_links = [
        {"rel": "icon", "href": FAVICON_ICO_URL, "attrs": {"type": "image/x-icon"}},
        {
            "rel": "icon",
            "href": FAVICON_PNG_512_URL,
            "attrs": {"type": "image/png", "sizes": "512x512"},
        },
        {
            "rel": "apple-touch-icon",
            "href": APPLE_TOUCH_ICON_URL,
            "attrs": {"sizes": "180x180"},
        },
        {
            "rel": "mask-icon",
            "href": MASK_ICON_URL,
            "attrs": {"color": BRAND_PRIMARY},
        },
    ]
    favicon_json = json.dumps(favicon_links, separators=(",", ":"))

    st.markdown(
        f"""
        <link rel="icon" type="image/x-icon" href="{FAVICON_ICO_URL}">
        <link rel="shortcut icon" type="image/x-icon" href="{FAVICON_ICO_URL}">
        <link rel="icon" type="image/png" sizes="512x512" href="{FAVICON_PNG_512_URL}">
        <link rel="apple-touch-icon" sizes="180x180" href="{APPLE_TOUCH_ICON_URL}">
        <link rel="mask-icon" href="{MASK_ICON_URL}" color="{BRAND_PRIMARY}">
        <!-- Prefer link-based font loading for Safari stability -->
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700;800&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <script>
        (() => {{
            if (window.__WHYLINE_FAVICON_PATCH__) {{
                return;
            }}
            window.__WHYLINE_FAVICON_PATCH__ = true;
            const head = document.head || document.getElementsByTagName('head')[0];
            if (!head) {{
                return;
            }}
            const iconDefs = {favicon_json};
            head.querySelectorAll("link[rel='icon'],link[rel='apple-touch-icon'],link[rel='mask-icon']").forEach((node) => {{
                if (node.parentNode) {{
                    node.parentNode.removeChild(node);
                }}
            }});
            iconDefs.forEach((def) => {{
                const link = document.createElement('link');
                link.rel = def.rel;
                link.href = def.href;
                if (def.attrs) {{
                    Object.entries(def.attrs).forEach(([key, value]) => {{
                        if (value) {{
                            link.setAttribute(key, value);
                        }}
                    }});
                }}
                head.appendChild(link);
            }});
        }})();
        </script>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <style>
        /* Fonts loaded via <link> tags above for better Safari compatibility */

        /* ═══ GLOBAL RESETS & BASE STYLES ═══ */
        html, body, [class*="css"] {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            color: #e8d5c4;
            background: #232129;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
            -webkit-text-size-adjust: 100%;
            text-rendering: optimizeLegibility;
        }}

        /* Normalize form controls for WebKit */
        input, textarea, select, button {{
            -webkit-appearance: none;
            appearance: none;
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
            /* --- keep label inside button --- */
            display: inline-flex;
            align-items: center;
            justify-content: center;
            /* Avoid breaking words into separate lines */
            white-space: normal;         /* allow wrapping only at spaces */
            word-break: keep-all;        /* prevent mid-word breaks */
            overflow-wrap: normal;       /* don't force breaks inside words */
            hyphens: none;               /* no auto-hyphenation */
            overflow: hidden;            /* clip overflow */
            text-overflow: ellipsis;     /* ellipsis as last resort */
            box-sizing: border-box;
            max-width: 100%;
            min-width: 0;
            line-height: 1.2;
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

        /* Secondary buttons (e.g., Prebuilt Questions) - keep long labels on one line
           and dynamically shrink the text to fit. */
        .stButton > button[kind="secondary"] {{
            /* Fluid, slightly smaller typography with lower bound for tight fits */
            font-size: clamp(0.80rem, 1.1vw, 1.00rem);
            letter-spacing: 0.015em;
            text-transform: none !important;  /* remove uppercase to save width */
            /* Prevent wrapping and gracefully clip if still too long */
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            /* Slightly tighter horizontal padding to buy space */
            padding-left: 1.25rem;
            padding-right: 1.25rem;
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
            /* Widen sidebar to keep freshness badges on a single line */
            width: 440px;
        }}

        [data-testid="stSidebar"] > div {{
            width: 100%;
        }}

        @media (max-width: 1400px) {{
            [data-testid="stSidebar"] {{
                width: 420px;
            }}
        }}

        @media (max-width: 1100px) {{
            [data-testid="stSidebar"] {{
                width: 380px;
            }}
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

        .status-badge {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 0.5rem;
            background-color: rgba(135, 167, 179, 0.08);
            border-left: 4px solid rgba(135, 167, 179, 0.3);
            border-radius: 10px;
            padding: 0.6rem 0.85rem;
            margin-bottom: 0.6rem;
            /* Enforce single-line for badge text */
            flex-wrap: nowrap;
            white-space: nowrap;
            overflow: hidden;
        }}

        .status-badge__label {{
            font-family: 'Space Grotesk', sans-serif;
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: #9a8e7e;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}

        .status-badge__value {{
            font-family: 'Space Grotesk', sans-serif;
            font-weight: 600;
            font-size: 0.9rem;
            letter-spacing: 0.02em;
            color: {BRAND_PRIMARY};
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}

        .status-badge--success {{
            background-color: rgba(163, 184, 140, 0.16);
            border-left-color: {BRAND_SUCCESS};
        }}

        .status-badge--accent {{
            background-color: rgba(212, 165, 116, 0.16);
            border-left-color: {BRAND_ACCENT};
        }}

        .status-badge--warning {{
            background-color: rgba(232, 184, 99, 0.18);
            border-left-color: {BRAND_WARNING};
        }}

        .status-badge--success .status-badge__value {{
            color: {BRAND_SUCCESS};
        }}

        .status-badge--accent .status-badge__value {{
            color: {BRAND_ACCENT};
        }}

        .status-badge--warning .status-badge__value {{
            color: {BRAND_WARNING};
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
        hr.section-separator {{
            border: none;
            border-top: 1px solid rgba(135, 167, 179, 0.25);
            margin: 1.5rem 0 1rem;
        }}

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

        /* ═══ RETRO HEADER ═══ */
        .retro-banner {{
            position: relative;
            display: flex;
            align-items: center;
            gap: 2.5rem;
            margin-bottom: 2.5rem;
            padding: 2.5rem;
            background: linear-gradient(135deg, rgba(135, 167, 179, 0.15) 0%, rgba(212, 165, 116, 0.12) 100%);
            border-radius: 16px;
            border: 4px solid rgba(135, 167, 179, 0.3);
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.1);
            overflow: hidden;
        }}

        .retro-banner__stripe {{
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 6px;
            background: {STRIPE_GRADIENT};
        }}

        .retro-banner__logo {{
            flex: 0 0 auto;
            display: flex;
            align-items: center;
            justify-content: center;
        }}

        .retro-banner__logo-img {{
            height: 140px;
            width: auto;
            filter: drop-shadow(0 6px 16px rgba(0, 0, 0, 0.5));
        }}

        .retro-banner__text {{
            min-width: 0;
        }}

        .retro-banner__title {{
            margin: 0;
            font-size: 3.5rem;
            font-weight: 800;
            background: linear-gradient(135deg, {BRAND_PRIMARY} 0%, {BRAND_ACCENT} 100%);
            -webkit-background-clip: text;
            background-clip: text;
            -webkit-text-fill-color: transparent;
            letter-spacing: -0.03em;
            line-height: 1.1;
        }}

        .retro-banner__tagline {{
            margin: 0.75rem 0 0 0;
            color: {BRAND_ACCENT};
            font-size: 1.3rem;
            font-weight: 500;
            letter-spacing: 0.02em;
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

        /* ═══ RESPONSIVE ADJUSTMENTS ═══ */
        @media (max-width: 1200px) {{
            h1 {{
                font-size: 2.75rem;
            }}
            h2 {{
                font-size: 1.8rem;
            }}
            .stButton > button {{
                font-size: 1rem;
                padding: 0.65rem 1.5rem;
            }}
            .retro-banner {{
                gap: 1.75rem;
                padding: 2rem;
            }}
            .retro-banner__logo-img {{
                height: 120px;
            }}
            .retro-banner__title {{
                font-size: 3rem;
            }}
        }}

        @media (max-width: 900px) {{
            .block-container {{
                padding: 1.5rem 1.25rem 2.5rem;
            }}
            div[data-testid="stHorizontalBlock"] {{
                flex-direction: column;
                align-items: stretch;
                gap: 0.85rem !important;
            }}
            div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {{
                width: 100% !important;
                flex: 1 1 100% !important;
            }}
            .retro-banner {{
                padding: 1.75rem;
                gap: 1.5rem;
            }}
            .retro-banner__title {{
                font-size: 2.6rem;
            }}
            .retro-banner__tagline {{
                font-size: 1.15rem;
            }}
            .retro-banner__logo-img {{
                height: 110px;
            }}
        }}

        @media (max-width: 680px) {{
            html, body, [class*="css"] {{
                font-size: 15px;
            }}
            h1 {{
                font-size: 2.1rem;
            }}
            h2 {{
                font-size: 1.6rem;
            }}
            h3 {{
                font-size: 1.3rem;
            }}
            .retro-banner {{
                flex-direction: column;
                align-items: flex-start;
                padding: 1.5rem;
            }}
            .retro-banner__logo {{
                width: 100%;
                justify-content: flex-start;
            }}
            .retro-banner__logo-img {{
                height: 90px;
            }}
            .retro-banner__text {{
                width: 100%;
            }}
            .retro-banner__title {{
                font-size: 2.3rem;
            }}
            .retro-banner__tagline {{
                font-size: 1rem;
                margin-top: 0.5rem;
            }}
            .stButton > button {{
                font-size: 0.95rem;
                padding: 0.65rem 1.1rem;
                width: 100%;
            }}
            [data-testid="stSidebar"] {{
                border-right: none;
            }}
            .status-badge {{
                flex-direction: column;
                align-items: flex-start;
                gap: 0.25rem;
            }}
            .stAlert {{
                font-size: 0.95rem;
            }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header() -> None:
    """Render custom header with logo and tagline - ENHANCED RETRO VERSION."""
    assets_dir = Path(__file__).parent.parent / "assets"
    logo_path = None
    for candidate in ("whylinedenver-logo.svg", "whylinedenver-logo@512.png"):
        path = assets_dir / candidate
        if path.exists():
            logo_path = path
            break

    if logo_path and logo_path.suffix.lower() == ".svg":
        raw = logo_path.read_text(encoding="utf-8")
        logo_data = base64.b64encode(raw.encode("utf-8")).decode()
        mime = "image/svg+xml"
    elif logo_path:
        with open(logo_path, "rb") as f:
            logo_data = base64.b64encode(f.read()).decode()
        mime = "image/png"
    else:
        logo_data = ""
        mime = ""

    if logo_data:
        img_element = (
            f'<img src="data:{mime};base64,{logo_data}" alt="{BRAND_NAME} logo" '
            'class="retro-banner__logo-img" />'
        )
    else:
        img_element = ""

    logo_markup = f'<div class="retro-banner__logo">{img_element}</div>' if img_element else ""

    st.markdown(
        f"""
        <div class="retro-banner">
            <div class="retro-banner__stripe"></div>
            {logo_markup}
            <div class="retro-banner__text">
                <h1 class="retro-banner__title">{BRAND_NAME}</h1>
                <p class="retro-banner__tagline">{BRAND_TAGLINE}</p>
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
                Built with <span style="color: {BRAND_ACCENT};">♥</span> by your Denver City neighbor.
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
