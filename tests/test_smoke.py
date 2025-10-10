import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def test_imports():
    from whylinedenver.config import settings

    assert settings.ENGINE in ("duckdb", "bigquery")
