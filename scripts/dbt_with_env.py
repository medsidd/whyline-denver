"""dbt runner that loads the project .env before delegating to dbt.cli.main."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from dotenv import load_dotenv

try:
    from dbt.cli.main import dbtRunner
except ModuleNotFoundError as exc:
    raise SystemExit(
        "dbt is not installed. Install dependencies before running this helper."
    ) from exc


def _load_project_env() -> None:
    """Load .env from the repository root so dbt sees required env vars."""
    project_root = Path(__file__).resolve().parents[1]
    env_path = project_root / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)
    else:  # pragma: no cover - defensive log for missing .env
        load_dotenv(override=False)


def run_dbt(args: Sequence[str]) -> int:
    """Execute dbt with the provided CLI arguments."""
    runner = dbtRunner()
    result = runner.invoke(list(args))
    if result.success:
        return 0
    if result.exception:
        raise result.exception
    return 1


def main() -> int:
    """Entry point that loads .env then executes the dbt CLI."""
    _load_project_env()
    return run_dbt(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
