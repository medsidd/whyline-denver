"""Registry invariant tests — verify MartEntry constraints hold for every entry."""

from __future__ import annotations

import pytest

from whyline.sync.constants import MART_REGISTRY, MartEntry


@pytest.mark.parametrize("entry", MART_REGISTRY, ids=lambda e: e.name)
def test_sync_requires_export(entry: MartEntry) -> None:
    """sync_to_duckdb=True requires export_to_gcs=True (can't refresh what was never exported)."""
    if entry.sync_to_duckdb:
        assert entry.export_to_gcs, f"{entry.name}: sync_to_duckdb=True but export_to_gcs=False"


@pytest.mark.parametrize("entry", MART_REGISTRY, ids=lambda e: e.name)
def test_hot_requires_sync(entry: MartEntry) -> None:
    """duckdb_hot=True requires sync_to_duckdb=True."""
    if entry.duckdb_hot:
        assert entry.sync_to_duckdb, f"{entry.name}: duckdb_hot=True but sync_to_duckdb=False"


@pytest.mark.parametrize("entry", MART_REGISTRY, ids=lambda e: e.name)
def test_latest_only_requires_export(entry: MartEntry) -> None:
    """latest_only=True requires export_to_gcs=True."""
    if entry.latest_only:
        assert entry.export_to_gcs, f"{entry.name}: latest_only=True but export_to_gcs=False"


@pytest.mark.parametrize("entry", MART_REGISTRY, ids=lambda e: e.name)
def test_download_requires_label(entry: MartEntry) -> None:
    """allow_download=True requires a non-empty download_label."""
    if entry.allow_download:
        assert (
            entry.download_label
        ), f"{entry.name}: allow_download=True but download_label is empty"


@pytest.mark.parametrize("entry", MART_REGISTRY, ids=lambda e: e.name)
def test_deprecated_not_prompt_or_download(entry: MartEntry) -> None:
    """deprecated=True requires allow_prompt=False and allow_download=False."""
    if entry.deprecated:
        assert not entry.allow_prompt, f"{entry.name}: deprecated=True but allow_prompt=True"
        assert not entry.allow_download, f"{entry.name}: deprecated=True but allow_download=True"


def test_mart_by_name_covers_all() -> None:
    """MART_BY_NAME contains every entry in MART_REGISTRY."""
    from whyline.sync.constants import MART_BY_NAME

    assert len(MART_BY_NAME) == len(
        MART_REGISTRY
    ), "MART_BY_NAME length differs from MART_REGISTRY — duplicate name in registry?"
    for entry in MART_REGISTRY:
        assert entry.name in MART_BY_NAME
