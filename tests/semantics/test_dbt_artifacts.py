from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from whyline.semantics.dbt_artifacts import DbtArtifacts
from whyline.sync.constants import ALLOWLISTED_MARTS


@pytest.fixture(scope="module")
def artifacts(tmp_path_factory) -> DbtArtifacts:
    target_path = tmp_path_factory.mktemp("dbt-artifacts")
    project = Path(__file__).resolve().parents[2] / "dbt"
    # Parse real model definitions offline; never reuse the checked-in runtime snapshot.
    (target_path / "profiles.yml").write_text(
        "whyline_denver:\n  target: test\n  outputs:\n    test:\n"
        "      type: bigquery\n      method: oauth\n"
        "      project: offline-test\n      dataset: test\n"
    )
    env = {
        **os.environ,
        "DBT_SEND_ANONYMOUS_USAGE_STATS": "false",
        "GCP_PROJECT_ID": "offline-test",
        "BQ_DATASET_RAW": "raw_test",
        "BQ_DATASET_STG": "stg_test",
        "BQ_DATASET_MART": "mart_test",
    }
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "dbt.cli.main",
            "parse",
            "--project-dir",
            str(project),
            "--profiles-dir",
            str(target_path),
            "--target-path",
            str(target_path),
            "--log-path",
            str(target_path / "logs"),
            "--no-partial-parse",
            "--target",
            "test",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    # A minimal catalog fixture exercises warehouse type merging without contacting BQ.
    (target_path / "catalog.json").write_text(
        json.dumps(
            {
                "nodes": {
                    "model.previous_project.mart_reliability_by_route_day": {
                        "columns": {"service_date_mst": {"type": "DATE"}}
                    }
                }
            }
        )
    )
    loader = DbtArtifacts(target_path=target_path)
    loader.load_artifacts()
    return loader


def test_every_allowlisted_mart_is_exposed(artifacts: DbtArtifacts) -> None:
    # Each allowlisted mart must also set meta.allow_in_app, or the app silently drops it.
    assert set(artifacts.allowed_models()) == set(ALLOWLISTED_MARTS)


def test_columns_and_descriptions_loaded(artifacts: DbtArtifacts) -> None:
    models = artifacts.allowed_models()
    reliability = models["mart_reliability_by_route_day"]
    assert reliability.description
    columns = reliability.columns
    assert "service_date_mst" in columns
    assert columns["service_date_mst"].type in {"DATE", "DATE32"}
    assert "route_id" in columns
    assert columns["route_id"].description
