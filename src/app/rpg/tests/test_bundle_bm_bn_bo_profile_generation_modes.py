from app.rpg.profiles import dynamic_npc_profiles as profiles
from app.rpg.profiles.character_cards import (
    generate_character_card_profile,
    get_character_card,
    list_character_cards_for_simulation_state,
)
from app.rpg.world.companion_acceptance import record_manual_companion_join_offer_for_test_or_runtime


def _make_state_with_mira():
    return {
        "player_state": {
            "party_state": {
                "companions": [
                    {
                        "npc_id": "npc:Mira",
                        "name": "Mira",
                        "status": "active",
                    }
                ]
            }
        }
    }


def test_profile_auto_create_disabled_skips_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "DEFAULT_PROFILE_ROOT", tmp_path)

    sim = {}
    result = record_manual_companion_join_offer_for_test_or_runtime(
        sim,
        npc_id="npc:Mira",
        name="Mira",
        identity_arc="cautious_mediator",
        current_role="Cautious mediator",
        tick=1,
        profile_auto_create=False,
    )

    assert result["recorded"] is True
    profile_result = result["profile_result"]
    assert profile_result["skipped"] is True
    assert profile_result["reason"] == "auto_profile_creation_disabled"

    # Profile file must not have been created.
    missing = list_character_cards_for_simulation_state(_make_state_with_mira())
    assert "npc:Mira" in missing["missing_profile_npc_ids"]


def test_profile_auto_create_enabled_creates_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "DEFAULT_PROFILE_ROOT", tmp_path)

    sim = {}
    result = record_manual_companion_join_offer_for_test_or_runtime(
        sim,
        npc_id="npc:Mira",
        name="Mira",
        identity_arc="cautious_mediator",
        current_role="Cautious mediator",
        tick=1,
        profile_auto_create=True,
    )

    assert result["recorded"] is True
    profile_result = result["profile_result"]
    assert profile_result.get("skipped") is not True
    assert profile_result.get("created") is True or profile_result.get("profile") is not None

    # Profile must exist.
    card = get_character_card("npc:Mira")
    assert card["ok"] is True
    assert card["card"]["name"] == "Mira"


def test_generate_character_card_profile_creates_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "DEFAULT_PROFILE_ROOT", tmp_path)

    result = generate_character_card_profile(
        npc_id="npc:Mira",
        name="Mira",
        identity_arc="cautious_mediator",
        current_role="Cautious mediator",
        source_event="manual_profile_generation",
        context_summary="Mira was introduced as a potential companion.",
        tick=1,
    )

    assert result["ok"] is True
    inner = result["profile_generation_result"]
    assert inner.get("created") is True or inner.get("profile") is not None
    assert result["card"]["name"] == "Mira"
    assert result["source"] == "deterministic_character_card_service"

    # Idempotent second call should not fail.
    result2 = generate_character_card_profile(
        npc_id="npc:Mira",
        name="Mira",
        tick=2,
    )
    assert result2["ok"] is True
