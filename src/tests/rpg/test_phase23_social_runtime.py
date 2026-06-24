from __future__ import annotations

from app.rpg.social_runtime import build_social_runtime_report


def test_phase23_social_runtime_applies_delta_and_gate() -> None:
    report = build_social_runtime_report(
        {
            "npc_dispositions": [{"npc_id": "bran", "values": {"trust": 20, "loyalty": 10}}],
            "disposition_deltas": [
                {"npc_id": "bran", "axis": "trust", "amount": 10, "source_event_id": "paid-room"}
            ],
            "social_thread": {"thread_id": "t1", "kind": "directed", "participants": ["bran"]},
            "speak_requests": [{"npc_id": "bran", "directly_addressed": True}],
            "memory_hooks": [{"kind": "clue", "npc_ids": ["bran"], "fact": "The quarry trail is fresh."}],
        }
    )

    assert report["ready"] is True
    assert report["disposition_reports"][0]["after"]["trust"] == 30
    assert report["companion_eligible"]["bran"] is True
    assert report["social_scene"]["decisions"][0]["allowed"] is True
    assert report["memory_hooks"][0]["fact"] == "The quarry trail is fresh."


def test_phase23_social_runtime_blocks_repeat_speaker() -> None:
    report = build_social_runtime_report(
        {
            "npc_ids": ["bran"],
            "social_thread": {"thread_id": "t1", "kind": "directed", "participants": ["bran"], "last_speaker_id": "bran"},
            "speak_requests": [{"npc_id": "bran"}],
        }
    )

    decision = report["social_scene"]["decisions"][0]
    assert decision["allowed"] is False
    assert decision["reason"] == "repeat_speaker_blocked"


def test_phase23_social_runtime_flags_missing_inputs() -> None:
    report = build_social_runtime_report({})

    assert report["ready"] is False
    assert "missing_npc_dispositions" in report["issues"]
    assert "missing_speak_requests" in report["issues"]
