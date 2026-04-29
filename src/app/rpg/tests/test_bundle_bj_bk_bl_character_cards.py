from app.rpg.profiles import dynamic_npc_profiles as profiles
from app.rpg.profiles.character_cards import (
    approve_character_card_draft,
    draft_character_card,
    generate_character_card_portrait_prompt,
    get_character_card,
    list_character_cards_for_simulation_state,
    update_character_card,
)
from app.rpg.profiles.dynamic_npc_profiles import ensure_dynamic_npc_profile


def test_character_card_list_and_get(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "DEFAULT_PROFILE_ROOT", tmp_path)

    ensure_dynamic_npc_profile(
        npc_id="npc:Mira",
        name="Mira",
        identity_arc="cautious_mediator",
        current_role="Cautious mediator",
        tick=1,
    )

    state = {
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

    listed = list_character_cards_for_simulation_state(state)
    assert listed["ok"] is True
    assert listed["count"] == 1
    assert listed["cards"][0]["npc_id"] == "npc:Mira"

    card = get_character_card("npc:Mira")
    assert card["ok"] is True
    assert card["card"]["name"] == "Mira"


def test_character_card_update_draft_approve(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "DEFAULT_PROFILE_ROOT", tmp_path)

    ensure_dynamic_npc_profile(
        npc_id="npc:Mira",
        name="Mira",
        identity_arc="cautious_mediator",
        current_role="Cautious mediator",
        tick=1,
    )

    updated = update_character_card(
        "npc:Mira",
        {
            "personality": {
                "traits": ["cautious", "card-ui-edited"],
            }
        },
        edited_by="unit_test",
        tick=2,
    )
    assert updated["ok"] is True
    assert "card-ui-edited" in updated["card"]["personality"]["traits"]

    drafted = draft_character_card("npc:Mira", tick=3)
    assert drafted["ok"] is True

    approved = approve_character_card_draft("npc:Mira", tick=4)
    assert approved["ok"] is True
    assert approved["card"]["origin"] == "llm_drafted_from_scaffold"


def test_character_card_portrait_prompt(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "DEFAULT_PROFILE_ROOT", tmp_path)

    ensure_dynamic_npc_profile(
        npc_id="npc:Mira",
        name="Mira",
        identity_arc="cautious_mediator",
        current_role="Cautious mediator",
        tick=1,
    )

    result = generate_character_card_portrait_prompt("npc:Mira", tick=2)
    assert result["ok"] is True

    portrait = result["card"]["portrait"]
    assert "Mira" in portrait["prompt"]
    assert "cautious" in portrait["prompt"].lower() or "mediator" in portrait["prompt"].lower()
