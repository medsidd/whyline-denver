"""Exercise documentation export orchestration without installing a browser renderer."""

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "export_diagrams.sh"


def test_exports_all_mermaid_sources_with_spaces(tmp_path):
    sources = tmp_path / "docs" / "diagrams"
    sources.mkdir(parents=True)
    for name in ("pipeline", "model lineage"):
        (sources / f"{name}.mmd").write_text(f"flowchart LR\n  {name!r}\n")
    renderer = tmp_path / "mock-renderer"
    renderer.write_text('#!/bin/sh\ncp "$2" "$4"\n')
    renderer.chmod(0o755)

    subprocess.run(  # noqa: S603 - fixed repository script and test-owned inputs
        ["/bin/bash", str(SCRIPT)],
        cwd=tmp_path,
        env={**os.environ, "MERMAID_CLI": str(renderer)},
        check=True,
    )

    outputs = sources / "exports"
    assert len(list(outputs.iterdir())) == 4
    for source in sources.glob("*.mmd"):
        for extension in ("svg", "png"):
            assert (outputs / f"{source.stem}.{extension}").read_text() == source.read_text()


def test_renderer_failure_stops_export(tmp_path):
    sources = tmp_path / "docs" / "diagrams"
    sources.mkdir(parents=True)
    (sources / "pipeline.mmd").write_text("flowchart LR\n  A --> B\n")
    result = subprocess.run(  # noqa: S603 - fixed repository script and test-owned inputs
        ["/bin/bash", str(SCRIPT)],
        cwd=tmp_path,
        env={**os.environ, "MERMAID_CLI": "/usr/bin/false"},
        check=False,
    )
    assert result.returncode != 0
    assert not list((sources / "exports").iterdir())


def test_missing_renderer_reports_setup_instructions(tmp_path):
    result = subprocess.run(  # noqa: S603 - fixed repository script and test-owned inputs
        ["/bin/bash", str(SCRIPT)],
        cwd=tmp_path,
        env={**os.environ, "MERMAID_CLI": str(tmp_path / "missing-renderer")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "docs/diagrams/README.md" in result.stderr
    assert not (tmp_path / "docs").exists()
