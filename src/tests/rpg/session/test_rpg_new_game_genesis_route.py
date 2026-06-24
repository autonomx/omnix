from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.rpg_session_routes import register_rpg_session_routes
from app.rpg.session import durable_store
from app.rpg.session import service as session_service
from app.rpg.session.service import load_session


def _wizard_payload() -> dict[str, object]:
    initial_stats = {
        "strength": 18,
        "agility": 13,
        "endurance": 12,
        "intellect": 10,
        "charisma": 11,
        "perception": 14,
        "archery": 9,
        "survival": 12,
    }
    starter_gear = ["Travel cloak", "Iron dagger", "Trail rations x3", "Torch x2", "10 silver"]
    genesis = {
        "contract_version": "rpg_genesis_v2",
        "campaign_template": "deterministic_rpg_campaign",
        "genre": None,
        "tone": "Even stats and flexible starter gear.",
        "identity": {
            "name": "Elara",
            "pronouns": "she/her",
            "background": "wanderer",
            "origin": "frontier_village",
            "power_source": "mundane",
        },
        "drivers": {
            "archetype": "balanced_adventurer",
            "motivation": {
                "primary": "survival",
                "target": "merchant_job",
                "intensity": 100,
                "fulfilled": False,
            },
            "flaw": "cautious",
            "talents": [
                {"id": "reconnaissance", "rank": 2},
                {"id": "action_readiness", "rank": 1},
                {"id": "survival_sense", "rank": 1},
            ],
            "values": ["agency", "loyalty"],
        },
        "initial_stats": initial_stats,
        "starter_gear_tags": starter_gear,
        "story_options": {
            "opening_hook": "merchant_job",
            "opening_pace": "balanced",
            "relationship_preset": "known_contact_nearby",
        },
        "world_options": {
            "world_profile": None,
            "starting_location": "rusty_flagon_tavern",
            "difficulty": "normal",
            "world_activity": "standard",
            "economy_pressure": "normal",
            "combat_lethality": "normal",
            "seed": 0,
        },
        "system_options": {
            "autosave": True,
            "companions": True,
            "permadeath": False,
            "validator": True,
            "background_soft_audit": True,
            "llm_narration": True,
            "image_generation": False,
            "tts": False,
            "stt": False,
        },
    }
    return {
        "campaign_template": "deterministic_rpg_campaign",
        "tone": "Even stats and flexible starter gear.",
        "background": "wanderer",
        "starting_location": "rusty_flagon_tavern",
        "player": {
            "name": "Elara",
            "pronouns": "she/her",
            "background": "wanderer",
            "build": "balanced_adventurer",
            "portrait_seed": 0,
        },
        "primary_capability": "recon",
        "secondary_capabilities": ["combat", "survival"],
        "power_source": "mundane",
        "generated_class_name": "Balanced Adventurer",
        "generated_class_summary": "Elara begins as a Balanced Adventurer from Frontier Village.",
        "difficulty": "normal",
        "world_activity": "standard",
        "economy_pressure": "normal",
        "combat_lethality": "normal",
        "companions_enabled": True,
        "permadeath": False,
        "seed": 0,
        "initial_stats": initial_stats,
        "starter_gear": starter_gear,
        "starter_gear_tags": starter_gear,
        "opening_hook": "merchant_job",
        "opening_pace": "balanced",
        "relationship_preset": "known_contact_nearby",
        "origin": "frontier_village",
        "motivation_primary": "survival",
        "motivation_target": "merchant_job",
        "flaw": "cautious",
        "values": ["agency", "loyalty"],
        "talents": [
            {"id": "reconnaissance", "rank": 2},
            {"id": "action_readiness", "rank": 1},
            {"id": "survival_sense", "rank": 1},
        ],
        "story_options": {
            "opening_hook": "merchant_job",
            "opening_hook_label": "Merchant Job",
            "opening_pace": "balanced",
            "opening_pace_label": "Balanced",
            "relationship_preset": "known_contact_nearby",
            "relationship_label": "Known contact nearby",
        },
        "system_options": {
            "autosave": True,
            "companions": True,
            "permadeath": False,
            "grounding": True,
            "softAudit": True,
            "narration": True,
            "images": False,
            "tts": False,
            "stt": False,
        },
        "features": {
            "autosave": True,
            "validator": True,
            "background_soft_audit": True,
            "llm_narration": True,
            "image_generation": False,
            "tts": False,
            "stt": False,
        },
        "genesis": genesis,
    }


def test_new_game_route_preserves_full_wizard_genesis_payload(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(durable_store, "_SESSION_DIR", tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)

    app = FastAPI()
    register_rpg_session_routes(app)
    client = TestClient(app)

    response = client.post("/api/rpg/new-game", json=_wizard_payload())

    assert response.status_code == 200
    result = response.json()
    assert result["ok"] is True
    session_id = result["session_id"]
    loaded = load_session(session_id)
    state = loaded["state"]
    metadata = state["metadata"]
    setup_payload = loaded["setup_payload"]

    assert state["contract_version"] == "rpg_genesis_v2"
    assert state["genesis_snapshot"]["identity"]["origin"] == "frontier_village"
    assert state["compiled_genesis_snapshot"]["compiled_stats"]["strength"] == 18
    assert state["bootstrap_snapshot"]["active_goals"]
    assert isinstance(setup_payload["bootstrap_snapshot"]["decision_biases"], dict)
    assert setup_payload["genesis"]["drivers"]["values"] == ["agency", "loyalty"]
    assert setup_payload["compiled_genesis"]["compiled_feature_flags"]["companions"] is True

    assert metadata["seed"] == 0
    assert loaded["simulation_state"]["seed"] == 0
    assert metadata["opening_hook"] == "merchant_job"
    assert metadata["relationship_preset"] == "known_contact_nearby"
    assert metadata["origin"] == "frontier_village"
    assert metadata["flaw"] == "cautious"
    assert metadata["values"] == ["agency", "loyalty"]

    assert state["player"]["name"] == "Elara"
    assert state["player"]["stats"]["strength"] == 18
    assert state["player"]["stats"]["dexterity"] == 13
    assert state["skill_progression"]["starting_stats"]["archery"] == {"value": 9, "source": "genesis_contract"}
    assert state["features"]["companions_enabled"] is True
    assert state["features"]["permadeath"] is False

    ability_tree = state["ability_tree"]
    ability_ids = [ability["ability_id"] for ability in ability_tree["abilities"]]
    assert len(ability_ids) == len(set(ability_ids))
    assert ability_tree["primary_capability"] == "recon"
    assert ability_tree["secondary_capabilities"] == ["combat", "survival"]

    inventory_names = {item["name"] for item in state["player"]["inventory"]}
    assert {"Travel cloak", "Iron dagger", "Trail rations", "Torch"}.issubset(inventory_names)
    assert state["player"]["currency"]["silver"] == 10


def test_new_game_route_uses_one_compact_genesis_final_save(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(durable_store, "_SESSION_DIR", tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    save_compact_flags: list[bool] = []
    original_save_session_to_disk = session_service.save_session_to_disk

    def spy_save_session_to_disk(session: dict, *, compact: bool = False) -> dict:
        save_compact_flags.append(compact)
        return original_save_session_to_disk(session, compact=compact)

    monkeypatch.setattr(session_service, "save_session_to_disk", spy_save_session_to_disk)

    app = FastAPI()
    register_rpg_session_routes(app)
    client = TestClient(app)

    response = client.post("/api/rpg/new-game", json=_wizard_payload())

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert save_compact_flags == [True, True]
