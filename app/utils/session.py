"""Session state management."""

from __future__ import annotations

import streamlit as st


def initialize() -> None:
    """
    Initialize Streamlit session state with default values.

    Optimized for low memory usage:
    - Store query parameters instead of large DataFrames
    - Results are recomputed from cached execution functions
    """
    defaults = {
        "generated_sql": None,
        "sql_error": None,
        "explanation": "",
        # Store parameters for recomputing results, not the DataFrame itself
        "query_params": None,  # {"engine": str, "sql": str, "question": str}
        "results_stats": None,
        "run_error": None,
        "sql_cache_hit": False,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)
