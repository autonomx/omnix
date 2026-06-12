from __future__ import annotations

from app.rpg.session.player_agency_contract import build_player_agency_contract, infer_player_personality
from app.rpg.session.player_personality_profile import (
    attach_player_personality_profile,
    extract_player_personality_profile,
    list_player_personality_presets,
    normalize_player_personality_profile,
)


def test_personality_presets_include_expected_player_styles() -> None:
    presets = list_player_personality_presets()
    ids = {preset["id"] for preset in presets["presets"]}

    assert presets["format_version"] == "rpg_player_personality_presets_v1"
    assert {"heroic", "pragmatic", "ruthless", "deceptive", "merciful", "chaotic"}.issubset(ids)


def test_ruthless_preset_normalizes_to_dark_presentation_only_profile() -> None:
    profile = normalize_player_personality_profile({"preset": "ruthless"})

    assert profile["format_version"] == "rpg_player_personality_profile_v1"
    assert profile["id"] == "ruthless"
    assert profile["tone_hint"] == "dark"
    assert profile["alignment"] == "evil"
    assert "ruthless" in profile["traits"]
    assert profile["presentation_only"] is True
    assert profile["simulation_authority"] is False


def test_custom_profile_merges_with_preset_without_authorizing_behavior() -> None:
    profile = normalize_player_personality_profile(
        {
            "preset": "deceptive",
            "label": "Velvet Knife",
            "traits": ["sly", "merciless", "patient", "sly"],
            "playstyle": "social leverage",
        }
    )

    assert profile["id"] == "deceptive"
    assert profile["label"] == "Velvet Knife"
    assert profile["tone_hint"] == "cunning"
    assert profile["traits"].count("sly") == 1
    assert "merciless" in profile["traits"]
    assert "social leverage" in profile["descriptor"]
    assert profile["simulation_authority"] is False


def test_extract_profile_prefers_stable_profile_field() -> None:
    result = {
        "player_personality_profile": {"preset": "merciful"},
        "player_personality": {"alignment": "evil", "traits": ["ruthless"]},
    }

    profile = extract_player_personality_profile(result=result)

    assert profile["id"] == "merciful"
    assert profile["tone_hint"] == "heroic"
    assert profile["alignment"] == "good"


def test_extract_profile_falls_back_to_nested_result_simulation_player_personality() -> None:
    result = {
        "simulation_state": {
            "player_state": {
                "personality": {"alignment": "evil", "traits": ["ruthless", "patient"]},
            }
        }
    }

    profile = extract_player_personality_profile(result=result)

    assert profile["tone_hint"] == "dark"
    assert profile["alignment"] == "evil"
    assert "ruthless" in profile["traits"]


def test_attach_player_personality_profile_adds_top_level_and_player_state_profile() -> None:
    target = {"player_state": {"name": "Test Hero"}}

    updated = attach_player_personality_profile(target, {"preset": "chaotic"})

    assert updated["player_personality_profile"]["id"] == "chaotic"
    assert updated["player_state"]["personality_profile"]["tone_hint"] == "wild"
    assert updated["player_state"]["personality_profile"]["presentation_only"] is True


def test_agency_contract_uses_stable_profile_context_for_flavor() -> None:
    result = {
        "player_personality_profile": {"preset": "ruthless"},
        "npc": {"id": "npc:bran", "speaker": "Bran"},
        "simulation_state": {
            "current_location_id": "loc:tavern",
            "location_name": "Rusty Flagon",
            "player_state": {"inventory_state": {"currency": {"silver": 3}}},
        },
    }

    personality = infer_player_personality(result=result)
    contract = build_player_agency_contract(result=result, player_input="What now?")

    assert personality["format_version"] == "rpg_player_personality_context_v2"
    assert personality["tone_hint"] == "dark"
    assert personality["profile"]["id"] == "ruthless"
    assert contract["personality"]["profile"]["format_version"] == "rpg_player_personality_profile_v1"
    assert contract["personality"]["profile"]["simulation_authority"] is False
    assert contract["option_count"] >= 1
