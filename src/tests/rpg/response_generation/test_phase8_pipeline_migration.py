from __future__ import annotations

from pathlib import Path

from app.rpg.ai import world_scene_narrator
from app.rpg.response_generation import legacy_bridge


REPO_ROOT = Path(__file__).resolve().parents[4]
AI_ROOT = REPO_ROOT / "src" / "app" / "rpg" / "ai"
SESSION_RUNTIME = REPO_ROOT / "src" / "app" / "rpg" / "session" / "narration_runtime.py"


def test_phase8_facade_uses_explicit_exports_without_fixup_side_effects():
    source = (AI_ROOT / "world_scene_narrator.py").read_text(encoding="utf-8")

    assert " import *" not in source
    assert "turn_fixups" not in source
    assert "current_turn_fixups" not in source
    assert "patch" not in source.casefold()
    assert "narrate_scene = narrate_scene_canonical" in source
    assert not (AI_ROOT / "world_scene_narrator_turn_fixups.py").exists()
    assert not (AI_ROOT / "world_scene_narrator_current_turn_fixups.py").exists()


def test_phase8_session_publication_resolves_through_canonical_facade():
    source = SESSION_RUNTIME.read_text(encoding="utf-8")

    assert "from app.rpg.ai.world_scene_narrator import narrate_scene" in source
    assert "world_scene_narrator_runtime import narrate_scene" not in source
    assert world_scene_narrator.narrate_scene is legacy_bridge.narrate_scene_canonical


def test_phase8_bridge_owns_final_visible_assembly(monkeypatch):
    def fake_legacy(*args, **kwargs):
        return {
            "narration": "You open the door.\n\nYou open the door.\n\nResult: The door opens.",
            "used_llm": True,
            "narration_json": {
                "narration": "You open the door.",
                "action": "You open the door.",
                "npc": {"speaker": "Bran", "line": "The door is open."},
            },
        }

    monkeypatch.setattr(legacy_bridge, "_legacy_narrate_scene", fake_legacy)
    result = legacy_bridge.narrate_scene_canonical(
        {"scene_id": "tavern"},
        {
            "turn_id": "turn-phase8",
            "player_input": "Open the door.",
            "state_delta": {"door_open": True},
        },
    )

    assert result["canonical_response_source"] == "rpg_response_generator_v1"
    assert result["narration"].count("You open the door.") == 1
    assert "Result:" not in result["narration"]
    assert "The door is open." in result["narration"]
    assert result["canonical_response"]["quality_report"]["ok"] is True
    assert result["canonical_response"]["metadata"]["candidate_source"] == "legacy_world_scene"


def test_phase8_bridge_preserves_authoritative_deltas_as_metadata_only(monkeypatch):
    monkeypatch.setattr(
        legacy_bridge,
        "_legacy_narrate_scene",
        lambda *args, **kwargs: {
            "narration": "Bran accepts the payment.",
            "narration_json": {
                "narration": "Bran accepts the payment.",
                "action": "",
                "npc": {"speaker": "", "line": ""},
            },
        },
    )
    delta = {"currency": {"silver": -5}, "inventory": {"room_key": 1}}

    result = legacy_bridge.narrate_scene_canonical(
        {"scene_id": "tavern"},
        {
            "turn_id": "turn-payment",
            "player_input": "Pay for the room.",
            "turn_contract": {"state_delta": delta},
        },
    )

    text = result["narration"]
    assert "room_key" not in text
    assert "-5" not in text
    assert result["canonical_response"]["metadata"]["turn_id"] == "turn-payment"


def test_phase8_legacy_public_prompt_and_scene_apis_remain_importable():
    assert callable(world_scene_narrator.build_scene_prompt)
    assert callable(world_scene_narrator.build_npc_reaction_prompt)
    assert callable(world_scene_narrator.build_choice_prompt)
    assert callable(world_scene_narrator.parse_scene_response)
    assert callable(world_scene_narrator.parse_npc_reaction)
    assert callable(world_scene_narrator.parse_choices)
    assert callable(world_scene_narrator.play_scene)
    assert world_scene_narrator.SceneNarrator is legacy_bridge.SceneNarrator
