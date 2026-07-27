from __future__ import annotations

from app.persistence.rpg_world_generation_repository import _merge_persistent_progress


def test_reconciliation_preserves_unresolved_stale_topics() -> None:
    current = {
        "percent": 50,
        "publication_blocked": True,
        "stale_topic_ids": ["actors", "pressures"],
        "stale_topics": {
            "actors": {
                "status": "potentially_stale",
                "required_action": "revalidate",
            },
            "pressures": {
                "status": "potentially_stale",
                "required_action": "invalidate",
            },
        },
    }

    reconciled = _merge_persistent_progress(
        current,
        {"percent": 100, "publication_blocked": False},
    )

    assert reconciled["percent"] == 100
    assert reconciled["stale_topic_ids"] == ["actors", "pressures"]
    assert reconciled["stale_topics"] == current["stale_topics"]
    assert reconciled["publication_blocked"] is True


def test_explicit_empty_staleness_clears_persistent_state() -> None:
    current = {
        "publication_blocked": True,
        "stale_topic_ids": ["actors"],
        "stale_topics": {"actors": {"status": "potentially_stale"}},
    }

    cleared = _merge_persistent_progress(
        current,
        {
            "publication_blocked": False,
            "stale_topic_ids": [],
            "stale_topics": {},
        },
    )

    assert cleared["stale_topic_ids"] == []
    assert cleared["stale_topics"] == {}
    assert cleared["publication_blocked"] is False
