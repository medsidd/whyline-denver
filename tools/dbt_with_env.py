"""dbt runner that loads the project .env before delegating to dbt.cli.main."""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from pathlib import Path

from dotenv import load_dotenv

try:
    from dbt.cli.main import dbtRunner
except ModuleNotFoundError as exc:  # pragma: no cover - import guard
    raise SystemExit(
        "dbt is not installed. Install dependencies before running this helper."
    ) from exc


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DBT_PROJECT_PATH = PROJECT_ROOT / "dbt"
DBT_PROFILES_PATH = DBT_PROJECT_PATH / "profiles"


def _load_project_env() -> None:
    """Load .env from the repository root so dbt sees required env vars."""
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)
    else:  # pragma: no cover - defensive log for missing .env
        load_dotenv(override=False)


def _ensure_runtime_env() -> None:
    """Populate environment defaults for dbt invocations."""
    profiles_dir = os.environ.get("DBT_PROFILES_DIR")
    if profiles_dir:
        profiles_path = Path(profiles_dir)
        if not profiles_path.is_absolute():
            os.environ["DBT_PROFILES_DIR"] = str((PROJECT_ROOT / profiles_path).resolve())
    else:
        os.environ["DBT_PROFILES_DIR"] = str(DBT_PROFILES_PATH)

    creds = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if creds:
        cred_path = Path(creds)
        if not cred_path.is_absolute():
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str((PROJECT_ROOT / cred_path).resolve())
    else:
        candidates = sorted(PROJECT_ROOT.glob("whyline-dbt-*.json"))
        if candidates:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(candidates[0].resolve())


def _with_default_project_dir(args: Sequence[str]) -> list[str]:
    """Ensure a --project-dir flag points at the dbt folder."""
    args_list = list(args)
    for arg in args_list:
        if arg == "--project-dir":
            return args_list
        if arg.startswith("--project-dir="):
            return args_list

    if not args_list:
        return ["parse", "--project-dir", str(DBT_PROJECT_PATH)]

    command = args_list[0]
    remainder = args_list[1:]
    return [command, "--project-dir", str(DBT_PROJECT_PATH), *remainder]


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
    _ensure_runtime_env()
    args = _with_default_project_dir(sys.argv[1:])
    return run_dbt(args)


if __name__ == "__main__":
    sys.exit(main())
