from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from app.rpg.narrative_engine import DeterministicNarrativeWriter
from app.rpg.narrative_engine.validation import NarrativeProviderRequiredError
from app.rpg.presentation.dialogue_quality import enforce_dialogue_quality
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


class _ProviderTaggedWriter:
    def __init__(self, line: str) -> None:
        self.line = line

    def write(self, request, plan, evidence):
        generated = DeterministicNarrativeWriter().write(request, plan, evidence)
        blocks = tuple(
            replace(block, text=self.line)
            if block.kind.value == "dialogue"
            else block
            for block in generated.blocks
        )
        return replace(
            generated,
            blocks=blocks,
            source="structured_provider",
            provider="test-provider",
            model="test-model",
        )


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


def test_fast_visible_dialogue_uses_provider_for_canonical_prose(
    monkeypatch,
) -> None:
    builds = []

    def provider_writer():
        builds.append(True)
        return _ProviderTaggedWriter(
            "Business is slower than I would like. The regulars remain, but fewer "
            "travelers are taking the old road this week."
        )

    monkeypatch.setattr(
        "app.rpg.narrative_provider.build_production_narrative_writer",
        provider_writer,
    )
    monkeypatch.setattr(
        "app.rpg.session.genesis.turn_grounding.load_campaign_bible_snapshot",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("fast visible dialogue must reuse runtime grounding")
        ),
    )
    monkeypatch.setattr(
        "app.rpg.session.genesis.turn_grounding.research_campaign_turn",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("fast visible dialogue must not perform Hermes research")
        ),
    )
    session = _session()
    session["manifest"]["session_id"] = "campaign:phase29:fast"
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
    advisory = _advisory()
    advisory["first_call_grounding_diagnostics"]["source"] = (
        "fast_visible_dialogue_v1"
    )

    result = build_non_stateful_dialogue_result(
        session=session,
        simulation_state=session["simulation_state"],
        runtime_state=session["runtime_state"],
        player_input="I ask Bran how business is doing.",
        semantic_advisory=advisory,
    )

    canonical = result["canonical_narrative_response"]
    assert builds == [True]
    assert canonical["generation"]["source"] == "structured_provider"
    assert result["llm_called"] is True
    assert result["llm_purpose"] == "canonical_dialogue_generation"
    assert result["narrative_grounding"]["runtime_only"] is True
    assert "regulars" in result["visible_response"]["plain_text"].casefold()
    assert "speaking plainly" not in result["visible_response"]["plain_text"].casefold()


def test_fast_visible_dialogue_rejects_deterministic_prose(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.rpg.narrative_provider.build_production_narrative_writer",
        lambda: DeterministicNarrativeWriter(),
    )
    session = _session()
    session["manifest"]["session_id"] = "campaign:phase29:reject-deterministic"
    advisory = _advisory()
    advisory["first_call_grounding_diagnostics"]["source"] = (
        "fast_visible_dialogue_v1"
    )

    with pytest.raises(NarrativeProviderRequiredError, match="deterministic prose"):
        build_non_stateful_dialogue_result(
            session=session,
            simulation_state=session["simulation_state"],
            runtime_state=session["runtime_state"],
            player_input="I ask Bran how business is doing.",
            semantic_advisory=advisory,
        )


def test_provider_authored_prose_is_not_replaced_by_canned_quality_repair(
    monkeypatch,
) -> None:
    authored = "The room has been thin all week. I would keep an eye on who no longer comes through the door."
    monkeypatch.setattr(
        "app.rpg.narrative_provider.build_production_narrative_writer",
        lambda: _ProviderTaggedWriter(authored),
    )
    session = _session()
    session["manifest"]["session_id"] = "campaign:phase29:preserve-provider"
    advisory = _advisory()
    advisory["first_call_grounding_diagnostics"]["source"] = (
        "fast_visible_dialogue_v1"
    )

    result = build_non_stateful_dialogue_result(
        session=session,
        simulation_state=session["simulation_state"],
        runtime_state=session["runtime_state"],
        player_input="I ask Bran how business is doing.",
        semantic_advisory=advisory,
    )

    result = enforce_dialogue_quality(
        result,
        session=session,
        player_input="I ask Bran how business is doing.",
    )
    canonical = result["canonical_narrative_response"]
    assert authored in result["visible_response"]["plain_text"]
    assert canonical["metadata"]["dialogue_quality_contract_met"] is False
    assert canonical["metadata"]["dialogue_quality_missing_fragments"] == [
        "regulars",
        "old road",
    ]
    assert "dialogue_quality_repair" not in canonical["metadata"]


def test_group_dialogue_plans_one_provider_authored_block_per_speaker(
    monkeypatch,
) -> None:
    authored = "The tracks are sparse, and the old road deserves a careful look."
    monkeypatch.setattr(
        "app.rpg.narrative_provider.build_production_narrative_writer",
        lambda: _ProviderTaggedWriter(authored),
    )
    session = _session()
    session["manifest"]["session_id"] = "campaign:phase29:provider-group"
    session["simulation_state"]["npcs"]["npc:mira"] = {
        "id": "npc:mira",
        "name": "Mira",
        "location_id": "location:tavern",
    }
    advisory = _advisory()
    advisory["first_call_grounding_diagnostics"]["source"] = (
        "fast_visible_dialogue_v1"
    )
    advisory["first_call_grounding_diagnostics"]["turn_grounding_packet"][
        "npc_context"
    ]["addressed_npcs"].append(
        {
            "id": "npc:mira",
            "name": "Mira",
            "biography": "Mira scouts the old road.",
        }
    )

    result = build_non_stateful_dialogue_result(
        session=session,
        simulation_state=session["simulation_state"],
        runtime_state=session["runtime_state"],
        player_input="I ask Bran and Mira what they make of the old road.",
        semantic_advisory=advisory,
    )

    result = enforce_dialogue_quality(
        result,
        session=session,
        player_input="I ask Bran and Mira what they make of the old road.",
    )
    canonical = result["canonical_narrative_response"]
    dialogue = [block for block in canonical["blocks"] if block["kind"] == "dialogue"]
    assert [block["speaker_id"] for block in dialogue] == ["npc:bran", "npc:mira"]
    assert [message["speaker_id"] for message in result["visible_response"]["messages"]] == [
        "npc:bran",
        "npc:mira",
    ]
    assert result["dialogue_quality"]["repaired"] is False
    assert "speaking plainly" not in result["visible_response"]["plain_text"].casefold()


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
