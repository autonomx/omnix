from __future__ import annotations

from typing import Any

from app.gateway import rpg_session_routes
from app.rpg.session import loadout
from app.rpg.session.ability_system import build_progression_package
from app.rpg.session.world_ability_integration import ensure_world_scale_abilities


def _world_session() -> dict[str, Any]:
    return {
        "manifest": {"id": "rpg_world", "session_id": "rpg_world", "title": "World Test", "updated_at": "before"},
        "setup_payload": {
            "genre": "political_intrigue",
            "tone": "court pressure",
            "player": {"name": "Envoy", "background": "disgraced envoy", "build": "silver_tongue"},
            "primary_capability": "influence",
            "secondary_capabilities": ["knowledge", "recon"],
            "power_source": "social_power",
            "generated_class_name": "Court Schemer",
        },
        "state": {
            "session_id": "rpg_world",
            "current_turn": 0,
            "turn_count": 0,
            "world": {"time": "Day 1 • Court", "reputation": {"label": "Unknown", "score": 0}},
            "summary": "Before",
            "player": {
                "name": "Envoy",
                "background": "disgraced envoy",
                "build": "silver_tongue",
                "class": "Court Schemer",
                "level": 5,
                "resources": {"hp": {"current": 50, "max": 50}, "stamina": {"current": 40, "max": 40}, "mana": {"current": 40, "max": 40}},
                "inventory": [],
                "equipment": [],
            },
            "timeline": [],
            "journal": {"entries": []},
        },
    }


def test_world_scale_templates_are_added_to_matching_ability_tree() -> None:
    package = build_progression_package(
        {
            "genre": "political_intrigue",
            "player": {"name": "Envoy", "background": "disgraced envoy", "build": "silver_tongue"},
            "primary_capability": "influence",
            "secondary_capabilities": ["knowledge"],
            "power_source": "social_power",
        },
        build_id="silver_tongue",
        level=1,
        seed=7,
    )
    state = {"ability_tree": package["ability_tree"], "ability_state": package["ability_state"], "hotbar": package["hotbar"]}

    assert ensure_world_scale_abilities(state) is True
    tree = state["ability_tree"]
    ids = {ability["ability_id"] for ability in tree["abilities"]}

    assert "influence_broker_truce" in ids
    assert any(category["category_id"] == "influence_world" for category in tree["categories"])
    assert tree["world_scale_template_version"] == "world_scale_templates_v1"


def test_world_scale_ability_can_be_unlocked_assigned_and_used(monkeypatch) -> None:
    saved: list[dict[str, Any]] = []
    session = _world_session()
    monkeypatch.setattr(loadout, "load_session", lambda session_id: saved[-1] if saved else session)
    monkeypatch.setattr(loadout, "save_session", lambda updated, *, compact=False: saved.append(updated) or updated)

    unlock = loadout.apply_loadout_action("rpg_world", loadout.RpgLoadoutActionRequest(action="unlock_ability", ability_id="influence_broker_truce"))
    assign = loadout.apply_loadout_action("rpg_world", loadout.RpgLoadoutActionRequest(action="assign_hotbar", ability_id="influence_broker_truce", hotbar_slot="8"))
    use = loadout.apply_loadout_action("rpg_world", loadout.RpgLoadoutActionRequest(action="hotbar", hotbar_slot="8"))

    assert unlock["ok"] is True
    assert assign["ok"] is True
    assert use["ok"] is True
    state = saved[-1]["state"]
    assert state["faction_state"]["relations"]["town_guard:road_gang"]["score"] == 2
    assert state["world"]["events"][0]["event_id"] == "truce_brokered"
    assert state["narrative_affordances"]["world"][0]["tag"] == "negotiate_truce_terms"
    assert state["timeline"][0]["kind"] == "world_ability"
    assert state["ability_state"]["cooldowns"]["influence_broker_truce"] == 8


def test_locked_world_scale_ability_is_rejected(monkeypatch) -> None:
    session = _world_session()
    monkeypatch.setattr(loadout, "load_session", lambda session_id: session)

    result = loadout.apply_loadout_action("rpg_world", loadout.RpgLoadoutActionRequest(action="use_ability", ability_id="influence_broker_truce"))

    assert result["ok"] is False
    assert result["error"] == "ability_locked"


def test_session_route_payloads_expose_world_scale_templates() -> None:
    package = build_progression_package(
        {
            "genre": "political_intrigue",
            "player": {"name": "Envoy", "background": "disgraced envoy", "build": "silver_tongue"},
            "primary_capability": "influence",
            "secondary_capabilities": [],
            "power_source": "social_power",
        },
        build_id="silver_tongue",
        level=1,
        seed=8,
    )
    payload = {"ok": True, "session": {"state": {"ability_tree": package["ability_tree"], "ability_state": package["ability_state"], "hotbar": package["hotbar"]}}}

    decorated = rpg_session_routes._with_world_scale_abilities(payload)
    ids = {ability["ability_id"] for ability in decorated["game"]["ability_tree"]["abilities"]}

    assert "influence_broker_truce" in ids
