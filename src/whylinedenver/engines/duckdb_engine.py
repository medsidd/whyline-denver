import duckdb
import pandas as pd


def execute(sql: str) -> tuple[dict, pd.DataFrame]:
    con = duckdb.connect(database="data/warehouse.duckdb", read_only=False)
    df = con.execute(sql).fetch_df()
    stats = {"engine": "duckdb", "rows": len(df)}
    con.close()
    return stats, df
