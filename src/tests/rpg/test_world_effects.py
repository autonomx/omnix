from __future__ import annotations

from typing import Any

from app.rpg.session.world_effects import (
    apply_world_scale_ability_to_state,
    build_world_scale_ability_templates,
    validate_world_scale_ability,
)


def _world_ability(**overrides: Any) -> dict[str, Any]:
    ability: dict[str, Any] = {
        "ability_id": "broker_truce",
        "kind": "active",
        "name": "Broker Truce",
        "description": "A deterministic world-scale diplomacy power.",
        "capability": "influence",
        "power_source": "social_power",
        "purpose": "world_influence",
        "dimensions": ["relationships", "economy", "world", "narrative"],
        "effect_ops": [
            {"dimension": "relationships", "op": "modify_faction_alert", "target_id": "town_guard", "amount": -2},
            {"dimension": "relationships", "op": "modify_faction_relationship", "target_id": "town_guard", "relationship": "road_gang", "amount": 3},
            {"dimension": "economy", "op": "modify_economy_price", "tag": "road_tolls", "amount": -1},
            {"dimension": "economy", "op": "modify_economy_availability", "tag": "safe_passage", "amount": 2},
            {"dimension": "world", "op": "add_world_event", "tag": "truce_brokered", "event_type": "faction_diplomacy", "state_value": "A fragile truce has been brokered."},
            {"dimension": "narrative", "op": "record_world_opportunity", "tag": "negotiate_truce_terms"},
        ],
    }
    ability.update(overrides)
    return ability


def test_world_scale_ability_modifies_factions_economy_and_world_events() -> None:
    state: dict[str, Any] = {
        "faction_state": {"factions": {"town_guard": {"alert": 5}}, "relations": {}},
        "economy": {},
        "world": {},
        "timeline": [],
        "journal": {"entries": []},
    }

    result = apply_world_scale_ability_to_state(state, _world_ability())

    assert result.ok is True
    assert state["faction_state"]["factions"]["town_guard"]["alert"] == 3
    assert state["faction_state"]["relations"]["town_guard:road_gang"]["score"] == 3
    assert state["economy"]["price_modifiers"]["road_tolls"]["amount"] == -1
    assert state["economy"]["availability_modifiers"]["safe_passage"]["amount"] == 2
    assert state["world"]["events"][0]["event_id"] == "truce_brokered"
    assert state["timeline"][0]["kind"] == "world_effect"
    assert state["journal"]["entries"][0]["kind"] == "world_effect"
    assert state["narrative_affordances"]["world"][0]["tag"] == "negotiate_truce_terms"
    assert len(state["mechanics"]["world_effect_trace"]) == len(result.effects)


def test_world_scale_ability_updates_settlement_rumors_and_quest_branches() -> None:
    ability = _world_ability(
        ability_id="found_safehouse",
        name="Found Safehouse",
        dimensions=["access", "information", "narrative", "world"],
        effect_ops=[
            {"dimension": "access", "op": "modify_settlement_state", "settlement_id": "rusty_flagon", "state_key": "safehouse", "state_value": True},
            {"dimension": "information", "op": "propagate_rumor", "settlement_id": "rusty_flagon", "tag": "safehouse_open", "rumor": "A safehouse is open near the tavern."},
            {"dimension": "narrative", "op": "open_quest_branch", "quest_id": "bandit_road", "tag": "use_safehouse_route", "state_value": "Use the safehouse route."},
        ],
    )
    state: dict[str, Any] = {"quests": [{"quest_id": "bandit_road", "branches": []}]}

    result = apply_world_scale_ability_to_state(state, ability)

    assert result.ok is True
    assert state["settlements"]["rusty_flagon"]["state"]["safehouse"] is True
    assert state["world"]["rumors"][0]["rumor_id"] == "safehouse_open"
    assert state["settlements"]["rusty_flagon"]["rumors"][0]["rumor_id"] == "safehouse_open"
    assert state["quest_branches"][0]["branch_id"] == "use_safehouse_route"
    assert state["quests"][0]["branches"][0]["branch_id"] == "use_safehouse_route"


def test_world_scale_validator_rejects_flavor_only_and_unknown_ops() -> None:
    errors = validate_world_scale_ability(
        _world_ability(
            ability_id="bad_world_power",
            dimensions=["world"],
            effect_ops=[{"dimension": "world", "op": "invent_world_mechanic"}],
        )
    )

    assert any("unsupported world-scale effect op invent_world_mechanic" in error for error in errors)
    assert validate_world_scale_ability(_world_ability(effect_ops=[]))


def test_world_scale_templates_validate_and_cover_core_dimensions() -> None:
    templates = build_world_scale_ability_templates()

    assert templates
    assert all(validate_world_scale_ability(template) == [] for template in templates)
    covered = {dimension for template in templates for dimension in template["dimensions"]}
    assert {"relationships", "economy", "world", "access", "narrative"}.issubset(covered)
