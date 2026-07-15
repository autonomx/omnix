from __future__ import annotations

from pathlib import Path

from app.rpg.narrative_engine import DeterministicNarrativeWriter
from app.rpg.session.narrative_engine_bridge import canonicalize_direct_dialogue_result


REPO_ROOT = Path(__file__).resolve().parents[4]


def _legacy_result(line: str = "The road is muddy, but passable.") -> dict:
    return {
        "consumed": True,
        "ok": True,
        "turn_id": "turn:direct:1",
        "tick": 1,
        "stateful": False,
        "needs_runtime_resolution": False,
        "resolved_result": {
            "ok": True,
            "semantic_family": "social",
            "response_mode": "dialogue",
            "target_id": "npc:bran",
            "target_name": "Bran",
            "stateful": False,
            "needs_runtime_resolution": False,
        },
        "narration": f"Bran: {line}",
        "final_narration": f"Bran: {line}",
        "summary": f"Bran: {line}",
        "npc": {"speaker": "Bran", "speaker_id": "npc:bran", "line": line},
        "visible_response": {
            "narration": "",
            "npc": {"speaker": "Bran", "speaker_id": "npc:bran", "line": line},
        },
        "first_call_grounding_diagnostics": {
            "turn_grounding_packet": {
                "player_input": "How is the road?",
                "priority_context": {"addressed_npc_ids": ["npc:bran"]},
                "npc_context": {
                    "addressed_npcs": [
                        {
                            "id": "npc:bran",
                            "name": "Bran",
                            "biography": "Keeper of the Rusty Flagon.",
                            "personality_profile": {"summary": "Practical and observant."},
                        }
                    ]
                },
            }
        },
    }


def test_direct_dialogue_is_regenerated_as_ordered_canonical_blocks(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.rpg.narrative_provider.build_production_narrative_writer",
        lambda: DeterministicNarrativeWriter(),
    )
    result = canonicalize_direct_dialogue_result(
        _legacy_result(),
        session_id="campaign:direct",
        player_input="How is the road?",
    )
    canonical = result["canonical_narrative_response"]
    assert result["source"] == "narrative_engine_direct_dialogue_v2"
    assert result["canonical_narrative_source"] == "unified_narrative_engine_v1"
    assert result["legacy_visible_prose_consumed"] is False
    assert [block["purpose"] for block in canonical["blocks"]][:2] == [
        "physical_reaction",
        "direct_answer",
    ]
    assert "The road is muddy, but passable." not in result["summary"]
    assert result["dialogue_blocks"][0]["speaker_id"] == "npc:bran"


def test_corrupted_direct_line_is_ignored_before_canonical_generation(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.rpg.narrative_provider.build_production_narrative_writer",
        lambda: DeterministicNarrativeWriter(),
    )
    result = canonicalize_direct_dialogue_result(
        _legacy_result("The road is open مرحبا broken."),
        session_id="campaign:direct",
        player_input="How is the road?",
    )
    canonical = result["canonical_narrative_response"]
    assert canonical["validation"]["passed"] is True
    assert "مرحبا" not in result["summary"]
    assert canonical["generation"]["source"] == "deterministic_writer"


def test_runtime_uses_direct_canonical_entry_without_monkey_patch() -> None:
    gateway = (
        REPO_ROOT / "src/app/gateway/rpg_turn_pipeline.py"
    ).read_text(encoding="utf-8")
    first_call = (
        REPO_ROOT / "src/app/rpg/session/first_call_dialogue.py"
    ).read_text(encoding="utf-8")
    assert "install_interactive_direct_dialogue_cutover" not in gateway
    assert "canonicalize_direct_dialogue_result" in first_call
    assert 'payload["canonical_narrative_response"]' in gateway
