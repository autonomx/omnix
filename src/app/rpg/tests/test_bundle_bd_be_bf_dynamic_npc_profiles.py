from pathlib import Path

from app.rpg.profiles import dynamic_npc_profiles as profiles
from app.rpg.profiles.dynamic_npc_profiles import (
    ensure_dynamic_npc_profile,
    load_npc_profile,
    update_npc_character_card,
)
from app.rpg.world.companion_acceptance import (
    record_manual_companion_join_offer_for_test_or_runtime,
)


def test_dynamic_profile_created_for_manual_companion_offer(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "DEFAULT_PROFILE_ROOT", tmp_path)

    state = {
        "location_id": "loc_tavern",
        "player_state": {"location_id": "loc_tavern"},
    }

    result = record_manual_companion_join_offer_for_test_or_runtime(
        state,
        npc_id="npc:Mira",
        name="Mira",
        identity_arc="cautious_mediator",
        current_role="Cautious mediator",
        active_motivations=[
            {
                "kind": "protect_party",
                "summary": "Keep the party from rushing into needless danger.",
                "strength": 2,
            }
        ],
        tick=1,
        reason="manual_test_offer_mira",
    )

    assert result["recorded"] is True
    profile_result = result["profile_result"]
    assert profile_result["created"] is True

    profile = load_npc_profile("npc:Mira")
    assert profile["npc_id"] == "npc:Mira"
    assert profile["name"] == "Mira"
    assert profile["biography"]["short_summary"]
    assert profile["personality"]["traits"]
    assert profile["morality"]["compassion"] == 2
    assert profile["card_edit_state"]["editable"] is True


def test_dynamic_profile_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "DEFAULT_PROFILE_ROOT", tmp_path)

    first = ensure_dynamic_npc_profile(
        npc_id="npc:Mira",
        name="Mira",
        identity_arc="cautious_mediator",
        current_role="Cautious mediator",
        tick=1,
    )
    second = ensure_dynamic_npc_profile(
        npc_id="npc:Mira",
        name="Mira Changed",
        identity_arc="other",
        current_role="Other",
        tick=2,
    )

    assert first["created"] is True
    assert second["created"] is False
    profile = load_npc_profile("npc:Mira")
    assert profile["name"] == "Mira"


def test_character_card_edit_persists_revision(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "DEFAULT_PROFILE_ROOT", tmp_path)

    ensure_dynamic_npc_profile(
        npc_id="npc:Mira",
        name="Mira",
        identity_arc="cautious_mediator",
        current_role="Cautious mediator",
        tick=1,
    )

    result = update_npc_character_card(
        "npc:Mira",
        {
            "biography": {
                "short_summary": "Edited Mira summary."
            },
            "personality": {
                "traits": ["cautious", "player-edited"]
            },
        },
        edited_by="unit_test",
        tick=2,
    )

    assert result["updated"] is True
    profile = load_npc_profile("npc:Mira")
    assert profile["biography"]["short_summary"] == "Edited Mira summary."
    assert "player-edited" in profile["personality"]["traits"]
    assert profile["card_edit_state"]["revision"] == 2
    assert profile["card_edit_state"]["last_edited_by"] == "unit_test"


def test_safe_profile_filename():
    assert profiles.safe_npc_profile_filename("npc:Mira") == "npc_Mira.json"
    assert profiles.safe_npc_profile_filename("npc:Bad/Name") == "npc_Bad_Name.json"
