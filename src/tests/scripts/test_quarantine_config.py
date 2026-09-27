from __future__ import annotations

from tests.conftest_quarantine import collection_globs, quarantine_count


def test_quarantine_entries_are_explicit_and_unique() -> None:
    globs = collection_globs()
    assert quarantine_count() == len(globs)
    assert len(globs) == len(set(globs))
    assert all(path.endswith(".py") for path in globs)
