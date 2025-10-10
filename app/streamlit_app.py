import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import streamlit as st

from whylinedenver.engines import bigquery_engine, duckdb_engine

st.set_page_config(page_title="WhyLine Denver", layout="wide")
st.title("WhyLine Denver — MVP Sanity")

engine = st.selectbox("Engine", ["duckdb", "bigquery"], index=0)
sql = st.text_area("SQL (read-only models later)", "SELECT 1 AS ok")

if st.button("Run"):
    if engine == "duckdb":
        stats, df = duckdb_engine.execute(sql)
    else:
        stats, df = bigquery_engine.execute(sql)
    st.write(stats)
    st.dataframe(df)
