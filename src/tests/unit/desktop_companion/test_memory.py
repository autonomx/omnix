from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.desktop_companion.memory import DesktopSceneMemory
from app.desktop_companion.models import DesktopObservation, DesktopObservedChange, DesktopObservedValue


BASE = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)


def observation(
    identifier: str,
    *,
    generation: str = "capture-1",
    source: str = "screen-1",
    observed_at: datetime = BASE,
    scene: str = "Inventory",
    confidence: float = 0.7,
    change_kind: str = "delta",
    event: str = "Inventory opened",
    event_confidence: float = 0.7,
) -> DesktopObservation:
    return DesktopObservation(
        observation_id=identifier,
        session_id="chat-1",
        capture_generation=generation,
        source_fingerprint=source,
        client_sequence=int(identifier.rsplit("-", 1)[-1]),
        captured_at=observed_at,
        observed_at=observed_at,
        expires_at=observed_at + timedelta(seconds=12),
        change_kind=change_kind,
        current_scene=DesktopObservedValue(value=scene, confidence=confidence),
        visible_changes=[
            DesktopObservedChange(
                event=event,
                confidence=event_confidence,
                fingerprint="change:inventory",
            )
        ],
        uncertainties=["Selection is unclear"],
    )


def test_scene_memory_revises_events_and_prefers_stronger_scene_evidence():
    memory = DesktopSceneMemory()
    assert memory.record(observation("obs-1"), now=BASE) is True
    assert memory.record(
        observation(
            "obs-2",
            observed_at=BASE + timedelta(seconds=5),
            scene="Equipment inventory",
            confidence=0.9,
            event_confidence=0.85,
        ),
        now=BASE + timedelta(seconds=5),
    ) is True

    snapshot = memory.snapshot("chat-1", now=BASE + timedelta(seconds=6))
    assert snapshot.current_scene is not None
    assert snapshot.current_scene.value == "Equipment inventory"
    assert len(snapshot.recent_events) == 1
    assert snapshot.recent_events[0].confidence == 0.85
    assert snapshot.recent_observation_ids == ("obs-1", "obs-2")
    assert "Current visible scene" in snapshot.compact_summary()


def test_new_capture_generation_resets_scene_specific_memory():
    memory = DesktopSceneMemory()
    memory.record(observation("obs-1"), now=BASE)
    memory.record(
        observation(
            "obs-2",
            generation="capture-2",
            source="screen-2",
            observed_at=BASE + timedelta(seconds=2),
            scene="Browser",
            event="Application changed",
        ),
        now=BASE + timedelta(seconds=2),
    )

    snapshot = memory.snapshot("chat-1", now=BASE + timedelta(seconds=3))
    assert snapshot.capture_generation == "capture-2"
    assert snapshot.source_fingerprint == "screen-2"
    assert snapshot.recent_observation_ids == ("obs-2",)
    assert snapshot.current_scene is not None
    assert snapshot.current_scene.value == "Browser"


def test_stale_observations_are_rejected_and_memory_expires():
    memory = DesktopSceneMemory(scene_ttl_seconds=10, event_ttl_seconds=20, uncertainty_ttl_seconds=10)
    assert memory.record(observation("obs-1"), now=BASE + timedelta(seconds=12)) is False

    fresh = observation("obs-2", observed_at=BASE + timedelta(seconds=20))
    assert memory.record(fresh, now=BASE + timedelta(seconds=20)) is True
    snapshot = memory.snapshot("chat-1", now=BASE + timedelta(seconds=41))
    assert snapshot.current_scene is None
    assert snapshot.recent_events == ()
    assert snapshot.uncertainties == ()
