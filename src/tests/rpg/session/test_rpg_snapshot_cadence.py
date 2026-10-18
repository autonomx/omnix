"""A full RPG snapshot is written every OMNIX_RPG_SNAPSHOT_EVERY revisions (WP-5.6)."""
from __future__ import annotations

import pytest

from app.apps.rpg.session.persistence.rpg_turn_service import snapshot_due


def test_a_snapshot_is_due_every_twentieth_revision_by_default(monkeypatch) -> None:
    monkeypatch.delenv("OMNIX_RPG_SNAPSHOT_EVERY", raising=False)
    assert [revision for revision in range(1, 61) if snapshot_due(revision)] == [20, 40, 60]


def test_the_interval_is_configurable_and_bounded(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_RPG_SNAPSHOT_EVERY", "1")
    assert all(snapshot_due(revision) for revision in range(1, 5))
    monkeypatch.setenv("OMNIX_RPG_SNAPSHOT_EVERY", "0")
    with pytest.raises(ValueError):
        snapshot_due(1)
