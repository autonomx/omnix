from __future__ import annotations

from app.rpg.session.first_call_dialogue import build_non_stateful_dialogue_result
from app.rpg.session.narrative_engine_bridge import (
    canonicalize_direct_dialogue_result,
)


def test_compact_provider_dialogue_is_adopted_without_deterministic_writer() -> None:
    provider_line = (
        '"Just overseeing the flow," Helix replies, wiping grease from his brow. '
        '"Making sure everything moves where it should."'
    )
    result = {
        "ok": True,
        "turn_id": "turn:4",
        "result": {
            "response_mode": "dialogue",
            "target_id": "npc:helix",
            "target_name": "Helix",
        },
        "resolved_result": {
            "response_mode": "dialogue",
            "target_id": "npc:helix",
            "target_name": "Helix",
        },
        "first_call_semantic_advisory": {
            "source": "compact_grounded_dialogue_v1",
            "visible_response": {
                "narration": "",
                "npc": {"speaker": "Helix", "line": provider_line},
            },
            "first_call_grounding_diagnostics": {
                "provider_called": True,
                "raw_text": provider_line,
            },
        },
    }

    canonical = canonicalize_direct_dialogue_result(
        result,
        session_id="session:vesper",
        player_input="I ask Helix what he is doing here",
    )

    assert canonical["npc"]["line"] == provider_line
    assert canonical["visible_response"]["messages"][0]["text"] == provider_line
    assert canonical["llm_called"] is True
    assert canonical["deterministic_fallback_used"] is False
    assert canonical["legacy_visible_prose_consumed"] is False
    assert canonical["provider_visible_prose_adopted"] is True
    assert canonical["source"] == "compact_dialogue_provider_canonical_v1"
    assert canonical["result"]["npc"]["line"] == provider_line
    assert canonical["resolved_result"]["npc"]["line"] == provider_line
    assert canonical["result"]["llm_called"] is True
    assert canonical["resolved_result"]["llm_called"] is True
    assert (
        canonical["canonical_narrative_response"]["generation"]["source"]
        == "compact_dialogue_provider"
    )


def test_first_call_builder_preserves_compact_provider_dialogue() -> None:
    provider_line = (
        '"Just overseeing the flow," Helix replies, wiping grease from his brow. '
        '"Making sure everything moves where it should."'
    )
    semantic_advisory = {
        "source": "compact_grounded_dialogue_v1",
        "action_type": "ask",
        "semantic_family": "social",
        "target_id": "npc:helix",
        "target_name": "Helix",
        "stateful": False,
        "needs_runtime_resolution": False,
        "risk_domain": "",
        "visible_response": {
            "narration": "",
            "npc": {"speaker": "Helix", "line": provider_line},
        },
        "first_call_grounding_diagnostics": {
            "provider_called": True,
            "raw_text": provider_line,
        },
    }

    result = build_non_stateful_dialogue_result(
        session={"session_id": "session:vesper"},
        simulation_state={},
        runtime_state={"turn_id": "turn:4"},
        player_input="I ask Helix what he is doing here",
        semantic_advisory=semantic_advisory,
    )

    assert result["consumed"] is True
    assert result["npc"]["line"] == provider_line
    assert result["visible_response"]["messages"][0]["text"] == provider_line
    assert result["llm_called"] is True
    assert result["deterministic_fallback_used"] is False
    assert result["legacy_visible_prose_consumed"] is False
    assert result["provider_visible_prose_adopted"] is True
