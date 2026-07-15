from __future__ import annotations

from pathlib import Path

from app.rpg.narrative_engine import DeterministicNarrativeWriter
from app.rpg.session.canonical_direct_dialogue import (
    build_canonical_direct_dialogue_intent,
)
from app.rpg.session.first_call_dialogue import (
    build_non_stateful_dialogue_result,
)
from app.rpg.session.narrative_engine_bridge import (
    canonicalize_direct_dialogue_result,
)


ROOT = Path(__file__).resolve().parents[4]


def _session() -> dict:
    return {
        "manifest": {"session_id": "campaign:phase29"},
        "simulation_state": {
            "player": {"id": "player", "location_id": "location:tavern"},
            "npcs": {
                "npc:bran": {
                    "id": "npc:bran",
                    "name": "Bran",
                    "location_id": "location:tavern",
                }
            },
        },
        "runtime_state": {
            "tick": 3,
            "active_npc_id": "npc:bran",
            "current_location_id": "location:tavern",
        },
    }


def _advisory() -> dict:
    return {
        "action_type": "social_activity",
        "semantic_family": "social",
        "interaction_mode": "direct",
        "target_id": "npc:bran",
        "target_name": "Bran",
        "stateful": False,
        "needs_runtime_resolution": False,
        "risk_domain": "none",
        "utterance_mode": "local_knowledge",
        "visible_response": {
            "narration": "Legacy narrator prose.",
            "npc": {
                "speaker": "Bran",
                "line": "LEGACY LINE MUST NEVER BE PUBLISHED",
            },
        },
        "first_call_grounding_diagnostics": {
            "turn_grounding_packet": {
                "format_version": "phase29",
                "player_input": "Bran, how is the road?",
                "priority_context": {
                    "addressed_npc_ids": ["npc:bran"],
                },
                "npc_context": {
                    "addressed_npcs": [
                        {
                            "id": "npc:bran",
                            "name": "Bran",
                            "biography": "Bran keeps the tavern by the old road.",
                        }
                    ]
                },
            }
        },
    }


def test_first_call_uses_advisory_for_intent_but_never_for_visible_prose(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.rpg.narrative_provider.build_production_narrative_writer",
        lambda: DeterministicNarrativeWriter(),
    )
    session = _session()
    result = build_non_stateful_dialogue_result(
        session=session,
        simulation_state=session["simulation_state"],
        runtime_state=session["runtime_state"],
        player_input="Bran, how is the road?",
        semantic_advisory=_advisory(),
    )
    assert result["consumed"] is True
    assert result["legacy_visible_prose_consumed"] is False
    assert result["source"] == "narrative_engine_direct_dialogue_v2"
    assert "LEGACY LINE MUST NEVER BE PUBLISHED" not in result["summary"]
    canonical = result["canonical_narrative_response"]
    assert canonical["generation"]["source"] == "deterministic_writer"
    assert [row["purpose"] for row in canonical["blocks"]] == [
        "physical_reaction",
        "direct_answer",
    ]
    assert result["visible_response"]["messages"][0]["speaker_id"] == "npc:bran"


def test_fast_immersive_and_cinematic_profiles_use_the_same_canonical_engine(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.rpg.narrative_provider.build_production_narrative_writer",
        lambda: DeterministicNarrativeWriter(),
    )
    session = _session()
    for index, profile in enumerate(("fast", "immersive", "cinematic"), start=1):
        intent = build_canonical_direct_dialogue_intent(
            session=session,
            simulation_state=session["simulation_state"],
            runtime_state=session["runtime_state"],
            player_input="Bran, how is the road?",
            action_advisory={},
            semantic_advisory=_advisory(),
        )
        intent["presentation_profile"] = profile
        intent["turn_id"] = f"turn:profile:{index}"
        generated = canonicalize_direct_dialogue_result(
            intent,
            session_id="campaign:phase29",
            player_input="Bran, how is the road?",
        )
        canonical = generated["canonical_narrative_response"]
        assert canonical["metadata"]["profile"] == profile
        assert canonical["generation"]["source"] == "deterministic_writer"
        assert generated["canonical_narrative_source"] == "unified_narrative_engine_v1"


def test_canonical_writer_persists_content_quality_repair_before_delivery(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.rpg.narrative_provider.build_production_narrative_writer",
        lambda: DeterministicNarrativeWriter(),
    )
    session = _session()
    session["manifest"]["session_id"] = "campaign:phase29:quality"
    session["simulation_state"]["npc_index"] = {
        "npc:bran": {
            "id": "npc:bran",
            "npc_id": "npc:bran",
            "name": "Bran",
            "biography": {
                "public": "Bran owns the Rusty Flagon near the old road.",
            },
        }
    }

    result = build_non_stateful_dialogue_result(
        session=session,
        simulation_state=session["simulation_state"],
        runtime_state=session["runtime_state"],
        player_input="I ask Bran how business is doing.",
        semantic_advisory=_advisory(),
    )

    canonical = result["canonical_narrative_response"]
    text = " ".join(block["text"] for block in canonical["blocks"]).casefold()
    assert "regulars" in text
    assert "old road" in text
    assert canonical["metadata"]["dialogue_quality_repair"] is True
    assert canonical["validation"]["repair_history"] == [
        "dialogue_quality:business"
    ]
    assert "regulars" in result["visible_response"]["plain_text"].casefold()


def test_canonical_writer_removes_fabricated_dialogue_for_absent_npc(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.rpg.narrative_provider.build_production_narrative_writer",
        lambda: DeterministicNarrativeWriter(),
    )
    session = _session()
    session["manifest"]["session_id"] = "campaign:phase29:absent"
    session["state"] = {"location": "Rusty Flagon Tavern"}
    session["simulation_state"].update(
        {
            "npc_index": {
                "npc:base_innkeeper": {
                    "id": "npc:base_innkeeper",
                    "name": "Base Innkeeper",
                },
            },
            "npcs": {
                "npc:bran": {
                    "id": "npc:bran",
                    "npc_id": "npc:bran",
                    "name": "Bran",
                    "location_id": "location:offstage",
                },
                "npc:mira": {
                    "id": "npc:mira",
                    "npc_id": "npc:mira",
                    "name": "Mira",
                    "location_id": "location:tavern",
                },
            },
            "scene": {"present_npc_ids": ["npc:mira"]},
            "player_state": {"nearby_npc_ids": ["npc:mira"]},
        }
    )

    result = build_non_stateful_dialogue_result(
        session=session,
        simulation_state=session["simulation_state"],
        runtime_state=session["runtime_state"],
        player_input="I ask for Bran while he is away from the Rusty Flagon.",
        semantic_advisory=_advisory(),
    )

    canonical = result["canonical_narrative_response"]
    assert [block["kind"] for block in canonical["blocks"]] == ["narration"]
    assert "Bran is not here" in result["visible_response"]["plain_text"]
    assert result["visible_response"]["messages"] == []


def test_production_sources_no_longer_use_dialogue_monkey_patch_or_legacy_line_writer() -> None:
    gateway = (
        ROOT / "src" / "app" / "gateway" / "rpg_turn_pipeline.py"
    ).read_text(encoding="utf-8")
    bridge = (
        ROOT / "src" / "app" / "rpg" / "session" / "narrative_engine_bridge.py"
    ).read_text(encoding="utf-8")
    first_call = (
        ROOT / "src" / "app" / "rpg" / "session" / "first_call_dialogue.py"
    ).read_text(encoding="utf-8")
    assert "install_interactive_direct_dialogue_cutover" not in gateway
    assert "_GroundedDialogueWriter" not in bridge
    assert "narrative_engine_grounded_dialogue" not in bridge
    assert "canonicalize_direct_dialogue_result" in first_call
    assert "legacy_visible_response_ignored" in first_call
