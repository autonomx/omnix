from __future__ import annotations

from app.rpg.presentation.turn_response import (
    TURN_RESPONSE_MAX_BYTES,
    build_turn_response_v2,
    turn_response_size_bytes,
)


def test_turn_response_exposes_authoritative_interaction_sequence() -> None:
    payload = build_turn_response_v2(
        {
            "ok": True,
            "interaction_id": "interaction:12",
            "narration": "Bran answers.",
        },
        session_id="session:bran",
        command="How is business?",
        session={
            "manifest": {"id": "session:bran"},
            "runtime_state": {"interaction_seq": 12, "state_revision": 14},
        },
    )

    assert payload["interaction_id"] == "interaction:12"
    assert payload["interaction_seq"] == 12
    assert payload["result"]["interaction_seq"] == 12
    assert payload["session_summary"]["interaction_seq"] == 12


def test_response_budget_fallback_preserves_interaction_sequence() -> None:
    payload = build_turn_response_v2(
        {
            "ok": True,
            "interaction_id": "interaction:42",
            "interaction_seq": 42,
            "narration": "x" * 500_000,
            "npc": {
                "speaker": "Bran",
                "line": "y" * 500_000,
            },
        },
        session_id="session:bran",
        command="Continue.",
        session={
            "manifest": {"id": "session:bran"},
            "runtime_state": {"interaction_seq": 42, "state_revision": 42},
        },
    )

    assert payload["interaction_seq"] == 42
    assert payload["interaction_id"] == "interaction:42"
    assert turn_response_size_bytes(payload) <= TURN_RESPONSE_MAX_BYTES
