from __future__ import annotations

from pathlib import Path

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
            "stateful": False,
            "needs_runtime_resolution": False,
        },
        "narration": f"Bran: {line}",
        "final_narration": f"Bran: {line}",
        "summary": f"Bran: {line}",
        "npc": {"speaker": "Bran", "line": line},
        "visible_response": {
            "narration": "",
            "npc": {"speaker": "Bran", "line": line},
        },
        "first_call_grounding_diagnostics": {
            "turn_grounding_packet": {
                "npc_context": {
                    "addressed_npcs": [
                        {
                            "name": "Bran",
                            "biography": "Keeper of the Rusty Flagon.",
                            "personality_profile": {
                                "summary": "Practical and observant."
                            },
                        }
                    ]
                }
            }
        },
    }


def test_direct_dialogue_is_republished_as_ordered_canonical_blocks() -> None:
    result = canonicalize_direct_dialogue_result(
        _legacy_result(),
        session_id="campaign:direct",
        player_input="How is the road?",
    )
    canonical = result["canonical_narrative_response"]
    assert result["source"] == "narrative_engine_direct_dialogue_v1"
    assert result["canonical_narrative_source"] == "unified_narrative_engine_v1"
    assert [block["purpose"] for block in canonical["blocks"]] == [
        "physical_reaction",
        "direct_answer",
        "continuation",
    ]
    assert result["narration"].startswith("Bran pauses")
    assert result["npc"] == {
        "speaker": "npc:bran",
        "line": "The road is muddy, but passable.",
    }
    assert result["narration"].count("muddy, but passable") == 0
    assert result["summary"].count("muddy, but passable") == 1


def test_corrupted_direct_line_is_rejected_and_replaced_before_publication() -> None:
    result = canonicalize_direct_dialogue_result(
        _legacy_result("The road is open مرحبا broken."),
        session_id="campaign:direct",
        player_input="How is the road?",
    )
    canonical = result["canonical_narrative_response"]
    assert canonical["validation"]["passed"] is True
    assert "مرحبا" not in result["summary"]
    assert canonical["generation"]["metadata"]["fallback_used"] is True


def test_runtime_installs_one_unified_direct_dialogue_publisher() -> None:
    session_init = (
        REPO_ROOT / "src/app/rpg/session/__init__.py"
    ).read_text(encoding="utf-8")
    gateway = (
        REPO_ROOT / "src/app/gateway/rpg_turn_pipeline.py"
    ).read_text(encoding="utf-8")
    assert "install_interactive_direct_dialogue_cutover" in session_init
    assert (
        "install_interactive_direct_dialogue_cutover"
        "(interactive_first_call_runtime)"
        in gateway
    )
    assert 'payload["canonical_narrative_response"]' in gateway
