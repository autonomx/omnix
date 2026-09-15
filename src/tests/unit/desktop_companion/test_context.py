from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.desktop_companion.context import DesktopCompanionContextStore
from app.desktop_companion.models import DesktopObservation, DesktopObservedValue

BASE = datetime(2026, 9, 14, 20, 0, tzinfo=timezone.utc)


def observation(index: int, *, character_id: str | None = "sofia") -> DesktopObservation:
    return DesktopObservation(
        observation_id=f"obs:{index}",
        session_id="chat:1",
        character_id=character_id,
        capture_generation="capture:1",
        source_fingerprint="desktop:test",
        client_sequence=index,
        captured_at=BASE + timedelta(seconds=index),
        observed_at=BASE + timedelta(seconds=index),
        expires_at=BASE + timedelta(minutes=5),
        change_kind="scene_change",
        current_scene=DesktopObservedValue(value=f"scene {index}", confidence=0.9),
        importance=0.5 + min(index, 4) * 0.1,
    )


def test_context_store_builds_bounded_activity_thread_and_keeps_character_identity() -> None:
    store = DesktopCompanionContextStore(maximum_summaries=3)
    for index in range(1, 5):
        store.record(observation(index), scene_summary=f"working state {index}")

    snapshot = store.snapshot("chat:1")
    assert snapshot is not None
    assert snapshot.character_id == "sofia"
    assert snapshot.observation_id == "obs:4"
    assert snapshot.observation_count == 4
    assert snapshot.activity_thread == "working state 2 | working state 3 | working state 4"


def test_context_store_deduplicates_consecutive_summary_and_clears_on_reset() -> None:
    store = DesktopCompanionContextStore(maximum_summaries=4)
    store.record(observation(1), scene_summary="same scene")
    store.record(observation(2), scene_summary="same scene")
    snapshot = store.snapshot("chat:1")
    assert snapshot is not None
    assert snapshot.activity_thread == "same scene"
    assert snapshot.observation_count == 2

    store.clear("chat:1")
    assert store.snapshot("chat:1") is None
