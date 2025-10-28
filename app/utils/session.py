"""Session state management."""

from __future__ import annotations

import streamlit as st


def initialize() -> None:
    """Initialize Streamlit session state with default values."""
    defaults = {
        "generated_sql": None,
        "sql_error": None,
        "explanation": "",
        "results_df": None,
        "results_stats": None,
        "run_error": None,
        "sql_cache_hit": False,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)
