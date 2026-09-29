from __future__ import annotations

from pathlib import Path

from tests.conftest import pytest_ignore_collect
from tests.conftest_quarantine import collection_globs, quarantine_count


def test_quarantine_entries_are_explicit_and_unique() -> None:
    globs = collection_globs()
    assert quarantine_count() == len(globs)
    assert len(globs) == len(set(globs))
    assert all(path.endswith(".py") for path in globs)


def test_collection_hook_defers_non_quarantine_paths_to_pytest_options() -> None:
    active_test = Path(__file__).resolve().parents[1] / "scripts" / "test_architecture_metrics.py"

    assert pytest_ignore_collect(active_test, config=None) is None


def test_collection_hook_ignores_quarantined_paths() -> None:
    quarantined_test = Path(__file__).resolve().parents[1] / "rpg" / "test_companions.py"

    assert pytest_ignore_collect(quarantined_test, config=None) is True
