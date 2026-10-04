from __future__ import annotations

from typing import Any

import pytest

from app.rpg.session.ability_system import (
    assign_ability_to_hotbar,
    apply_ability_to_state,
    build_ability_tree,
    build_progression_package,
    grant_player_xp,
    grant_skill_xp,
    remove_hotbar_slot,
    skill_modifier_for_check,
    tick_ability_state,
    unlock_ability_in_state,
    upgrade_ability_rank_in_state,
    validate_ability_tree,
)


def _base_active_ability(**overrides: Any) -> dict[str, Any]:
    ability = {
        "ability_id": "test_active",
        "kind": "active",
        "name": "Test Active",
        "description": "A deterministic test ability.",
        "capability": "knowledge",
        "power_source": "magic",
        "purpose": "utility",
        "dimensions": ["information"],
        "level_required": 1,
        "rank": 1,
        "max_rank": 3,
        "resource_cost": {"mana": 1},
        "cooldown_turns": 1,
        "prerequisites": [],
        "effect_ops": [{"dimension": "information", "op": "reveal_clue", "clue_tag": "test_clue"}],
    }
    ability.update(overrides)
    return ability


def test_progression_package_stores_capability_identity_and_valid_tree() -> None:
    package = build_progression_package(
        {
            "campaign_template": "cyberpunk",
            "genre": "cyberpunk",
            "tone": "street-level neon noir",
            "player": {"name": "Nyx", "background": "corporate defector", "build": "balanced_adventurer"},
            "primary_capability": "technical",
            "secondary_capabilities": ["knowledge", "recon"],
            "power_source": "technology",
        },
        build_id="balanced_adventurer",
        level=1,
        seed=123,
    )

    identity = package["character_identity"]
    assert identity["primary_capability"] == "technical"
    assert identity["power_source"] == "technology"
    assert identity["generated_class_name"] == "Netrunner"

    tree = package["ability_tree"]
    assert validate_ability_tree(tree).ok is True
    assert tree["design_rule"].startswith("Every active ability")
    assert {"information", "access"}.issubset(set(tree["dimensions"]))


@pytest.mark.parametrize(
    ("identity", "expected_family", "expected_class"),
    [
        ({"genre": "classic_fantasy", "primary_capability": "knowledge", "power_source": "magic"}, "classic_fantasy_knowledge_magic_v1", "Runebinder"),
        ({"genre": "classic_fantasy", "primary_capability": "combat", "power_source": "martial"}, "classic_fantasy_combat_martial_v1", "Champion"),
        ({"genre": "classic_fantasy", "primary_capability": "recon", "power_source": "martial"}, "classic_fantasy_recon_martial_v1", "Ranger"),
        ({"genre": "cyberpunk", "primary_capability": "technical", "power_source": "technology"}, "cyberpunk_technical_technology_v1", "Netrunner"),
        ({"genre": "cyberpunk", "primary_capability": "combat", "power_source": "technology"}, "cyberpunk_combat_technology_v1", "Street Samurai"),
        ({"genre": "detective_noir", "primary_capability": "recon", "power_source": "mundane"}, "detective_noir_recon_mundane_v1", "Private Eye"),
        ({"genre": "political_intrigue", "primary_capability": "influence", "power_source": "social_power"}, "political_intrigue_influence_social_power_v1", "Court Schemer"),
        ({"genre": "post_apocalyptic", "primary_capability": "survival", "power_source": "scrap"}, "post_apocalyptic_survival_scrap_v1", "Scavenger"),
        ({"genre": "space_opera", "primary_capability": "knowledge", "power_source": "psionic"}, "space_opera_knowledge_psionic_v1", "Psionic"),
        ({"genre": "space_opera", "primary_capability": "technical", "power_source": "technology"}, "space_opera_technical_technology_v1", "Science Officer"),
        ({"genre": "modern_occult", "primary_capability": "knowledge", "power_source": "occult"}, "modern_occult_knowledge_occult_v1", "Ritualist"),
        ({"genre": "survival_horror", "primary_capability": "survival", "power_source": "mundane"}, "survival_horror_survival_mundane_v1", "Survivor"),
    ],
)
def test_template_families_build_valid_playable_trees(identity: dict[str, Any], expected_family: str, expected_class: str) -> None:
    tree = build_ability_tree(identity)

    assert tree["source"] == "template_family_v1"
    assert tree["template_family"] == expected_family
    assert tree["class_name"] == expected_class
    assert validate_ability_tree(tree).ok is True
    assert tree["starting_unlocks"]
    assert tree["recommended_hotbar"] == tree["starting_unlocks"][:6]
    assert any(ability["kind"] == "passive" and ability["hooks"] for ability in tree["abilities"])
    assert any(ability["kind"] == "narrative_trait" and ability["influence_tags"] for ability in tree["abilities"])
    assert any(ability["kind"] == "active" and ability["effect_ops"] for ability in tree["abilities"])


def test_active_abilities_must_have_dimension_effects() -> None:
    tree = {
        "abilities": [
            {
                "ability_id": "flavor_only",
                "kind": "active",
                "name": "Flavor Only",
                "description": "No mechanics.",
                "capability": "knowledge",
                "power_source": "magic",
                "purpose": "utility",
                "dimensions": ["narrative"],
                "effect_ops": [],
            }
        ]
    }

    result = validate_ability_tree(tree)

    assert result.ok is False
    assert any("active ability has no effect_ops" in error for error in result.errors)


def test_validator_accepts_valid_active_passive_and_narrative_trait() -> None:
    tree = {
        "abilities": [
            _base_active_ability(),
            {
                "ability_id": "keen_eye",
                "kind": "passive",
                "name": "Keen Eye",
                "description": "Improves clue discovery through a deterministic hook.",
                "capability": "recon",
                "power_source": "mundane",
                "purpose": "information_gathering",
                "dimensions": ["information"],
                "resource_cost": {},
                "cooldown_turns": 0,
                "level_required": 1,
                "rank": 1,
                "max_rank": 3,
                "prerequisites": [],
                "hooks": ["on_investigation_check"],
                "effect_ops": [],
            },
            {
                "ability_id": "former_detective",
                "kind": "narrative_trait",
                "name": "Former Detective",
                "description": "A saved grounded fact that unlocks investigative context.",
                "capability": "recon",
                "power_source": "mundane",
                "purpose": "information_gathering",
                "dimensions": ["information", "relationships", "narrative"],
                "resource_cost": {},
                "cooldown_turns": 0,
                "level_required": 1,
                "rank": 1,
                "max_rank": 1,
                "prerequisites": [],
                "influence_tags": ["recognize_police_procedure", "unlock_detective_dialogue_paths"],
                "effect_ops": [],
            },
        ]
    }

    result = validate_ability_tree(tree)

    assert result.ok is True
    assert result.errors == []


def test_validator_rejects_unsupported_schema_values() -> None:
    tree = {
        "abilities": [
            _base_active_ability(
                capability="alchemy",
                power_source="vibes",
                purpose="flavor",
                dimensions=["mood"],
                effect_ops=[{"dimension": "mood", "op": "invent_mechanic"}],
            )
        ]
    }

    result = validate_ability_tree(tree)

    assert result.ok is False
    assert any("unsupported capability alchemy" in error for error in result.errors)
    assert any("unsupported power_source vibes" in error for error in result.errors)
    assert any("unsupported purpose flavor" in error for error in result.errors)
    assert any("invalid dimensions" in error for error in result.errors)
    assert any("unsupported effect op invent_mechanic" in error for error in result.errors)


def test_validator_rejects_bad_cost_cooldown_and_gates() -> None:
    tree = {
        "abilities": [
            _base_active_ability(
                resource_cost={"story_tokens": 1, "mana": -1},
                cooldown_turns=-1,
                level_required=0,
                rank=3,
                max_rank=2,
            )
        ]
    }

    result = validate_ability_tree(tree)

    assert result.ok is False
    assert any("invalid cost resource story_tokens" in error for error in result.errors)
    assert any("invalid cost value for mana" in error for error in result.errors)
    assert any("invalid cooldown_turns" in error for error in result.errors)
    assert any("invalid level_required" in error for error in result.errors)
    assert any("rank exceeds max_rank" in error for error in result.errors)


def test_validator_rejects_invalid_prerequisites() -> None:
    tree = {
        "abilities": [
            _base_active_ability(prerequisites=["test_active", "missing_ability", "missing_ability", 42]),
        ]
    }

    result = validate_ability_tree(tree)

    assert result.ok is False
    assert any("prerequisite cannot reference itself" in error for error in result.errors)
    assert any("missing prerequisite missing_ability" in error for error in result.errors)
    assert any("duplicate prerequisite missing_ability" in error for error in result.errors)
    assert any("invalid prerequisite 42" in error for error in result.errors)


def test_narrative_trait_without_effect_ops_requires_deterministic_hooks() -> None:
    tree = {
        "abilities": [
            {
                "ability_id": "flavor_trait",
                "kind": "narrative_trait",
                "name": "Flavor Trait",
                "description": "Pure prose without deterministic hooks.",
                "capability": "knowledge",
                "power_source": "mundane",
                "purpose": "utility",
                "dimensions": ["narrative"],
                "resource_cost": {},
                "cooldown_turns": 0,
                "level_required": 1,
                "rank": 1,
                "max_rank": 1,
                "prerequisites": [],
                "effect_ops": [],
            }
        ]
    }

    result = validate_ability_tree(tree)

    assert result.ok is False
    assert any("narrative_trait without effect_ops requires deterministic influence_tags or hooks" in error for error in result.errors)


def test_ability_use_changes_information_and_access_dimensions() -> None:
    package = build_progression_package(
        {
            "genre": "cyberpunk",
            "player": {"name": "Nyx", "background": "corporate defector", "build": "balanced_adventurer"},
            "primary_capability": "technical",
            "power_source": "technology",
        },
        build_id="balanced_adventurer",
        level=1,
        seed=456,
    )
    state: dict[str, Any] = {
        "player": {"resources": {"mana": {"current": 20, "max": 40}, "stamina": {"current": 50, "max": 50}}},
        "ability_tree": package["ability_tree"],
        "ability_state": package["ability_state"],
        "hotbar": package["hotbar"],
    }

    result = apply_ability_to_state(state, ability_name="Signal Probe", target="locked terminal")

    assert result.ok is True
    assert state["player"]["resources"]["mana"] == {"current": 14, "max": 40}
    assert state["clues"][0]["tag"] == "system_weakness"
    assert state["narrative_affordances"]["scene"][0]["tag"] == "technical_bypass_hint"
    assert result.effects[0]["dimension"] == "information"


def test_unlock_upgrade_and_hotbar_helpers_enforce_progression_gates() -> None:
    base = _base_active_ability(ability_id="base", name="Base", resource_cost={}, cooldown_turns=0)
    advanced = _base_active_ability(
        ability_id="advanced",
        name="Advanced",
        level_required=2,
        max_rank=2,
        prerequisites=["base"],
        resource_cost={},
        cooldown_turns=0,
    )
    passive = {
        "ability_id": "passive",
        "kind": "passive",
        "name": "Passive",
        "description": "Passive helper.",
        "capability": "knowledge",
        "power_source": "magic",
        "purpose": "utility",
        "dimensions": ["information"],
        "resource_cost": {},
        "cooldown_turns": 0,
        "level_required": 1,
        "rank": 1,
        "max_rank": 1,
        "prerequisites": [],
        "hooks": ["on_turn_start"],
        "effect_ops": [],
    }
    state: dict[str, Any] = {
        "player": {"level": 1, "resources": {}},
        "ability_tree": {"abilities": [base, advanced, passive]},
        "ability_state": {"ability_points": 0, "unlocked": ["base"], "ranks": {"base": 1}, "cooldowns": {}, "active_effects": []},
        "hotbar": {},
    }

    assert unlock_ability_in_state(state, "advanced").error == "level_required"
    state["player"]["level"] = 2
    assert unlock_ability_in_state(state, "advanced").error == "insufficient_ability_points"
    state["ability_state"]["ability_points"] = 2

    unlock_result = unlock_ability_in_state(state, "advanced")
    assert unlock_result.ok is True
    assert state["ability_state"]["ability_points"] == 1
    assert state["ability_state"]["ranks"]["advanced"] == 1

    assign_result = assign_ability_to_hotbar(state, "advanced", 3)
    assert assign_result.ok is True
    assert state["hotbar"]["3"] == "advanced"
    assert state["ability_state"]["hotbar"]["3"] == "advanced"
    assert assign_ability_to_hotbar(state, "passive", 4).error == "hotbar_requires_active_ability"

    upgrade_result = upgrade_ability_rank_in_state(state, "advanced")
    assert upgrade_result.ok is True
    assert state["ability_state"]["ability_points"] == 0
    assert state["ability_state"]["ranks"]["advanced"] == 2
    assert upgrade_ability_rank_in_state(state, "advanced").error == "max_rank"

    remove_result = remove_hotbar_slot(state, 3)
    assert remove_result.ok is True
    assert state["hotbar"] == {}


def test_unlock_helper_blocks_missing_prerequisites_before_spending_points() -> None:
    advanced = _base_active_ability(
        ability_id="advanced",
        name="Advanced",
        level_required=2,
        prerequisites=["base"],
        resource_cost={},
        cooldown_turns=0,
    )
    state: dict[str, Any] = {
        "player": {"level": 2, "resources": {}},
        "ability_tree": {"abilities": [advanced]},
        "ability_state": {"ability_points": 1, "unlocked": [], "ranks": {}, "cooldowns": {}, "active_effects": []},
    }

    result = unlock_ability_in_state(state, "advanced")

    assert result.ok is False
    assert result.error == "missing_prerequisites"
    assert state["ability_state"]["ability_points"] == 1


def test_ranked_use_scales_effects_and_tick_expires_cooldowns_and_active_effects() -> None:
    ability = _base_active_ability(
        ability_id="ranked",
        name="Ranked",
        dimensions=["resources", "position"],
        resource_cost={},
        cooldown_turns=2,
        effect_ops=[
            {"dimension": "resources", "op": "resource_delta", "target": "self", "resource": "stamina", "amount": 4},
            {"dimension": "position", "op": "modify_next_check", "check": "stealth", "amount": 1, "duration_turns": 2},
        ],
    )
    state: dict[str, Any] = {
        "player": {"resources": {"stamina": {"current": 0, "max": 20}}},
        "ability_tree": {"abilities": [ability]},
        "ability_state": {
            "ability_points": 0,
            "unlocked": ["ranked"],
            "ranks": {"ranked": 3},
            "cooldowns": {"old": 1},
            "active_effects": [{"ability_id": "old", "remaining_turns": 1}],
        },
        "hotbar": {"1": "ranked"},
    }

    result = apply_ability_to_state(state, ability_name="Ranked")

    assert result.ok is True
    assert state["player"]["resources"]["stamina"]["current"] == 6
    assert state["runtime"]["effects"][0]["amount"] == 3
    assert state["ability_state"]["cooldowns"] == {"ranked": 2}
    assert state["ability_state"]["active_effects"] == [
        {
            "ability_id": "ranked",
            "name": "Ranked",
            "rank": 3,
            "dimensions": ["resources", "position"],
            "purpose": "utility",
            "target": "the current situation",
            "created_at": state["ability_state"]["active_effects"][0]["created_at"],
            "duration_turns": 2,
            "remaining_turns": 2,
        }
    ]
    assert apply_ability_to_state(state, ability_name="Ranked").error == "ability_on_cooldown"

    tick_ability_state(state)
    assert state["ability_state"]["cooldowns"] == {"ranked": 1}
    assert state["ability_state"]["active_effects"][0]["remaining_turns"] == 1
    tick_ability_state(state)
    assert state["ability_state"]["cooldowns"] == {}
    assert state["ability_state"]["active_effects"] == []


def test_player_xp_levels_up_and_grants_ability_points_from_authorized_sources() -> None:
    state: dict[str, Any] = {
        "player": {"level": 1, "xp": {"current": 90, "max": 100}},
        "ability_state": {"ability_points": 0, "unlocked": [], "ranks": {}, "cooldowns": {}, "active_effects": []},
    }

    result = grant_player_xp(state, 30, source="objective")

    assert result.ok is True
    assert result.xp_gained == 30
    assert result.level_ups == [{"from": 1, "to": 2}]
    assert result.ability_points_granted == 1
    assert state["player"]["level"] == 2
    assert state["player"]["xp"] == {"current": 20, "max": 200}
    assert state["ability_state"]["ability_points"] == 1

    blocked = grant_player_xp(state, 50, source="conversation")
    assert blocked.ok is False
    assert blocked.error == "unsupported_xp_source"
    assert state["player"]["xp"] == {"current": 20, "max": 200}


def test_skill_xp_ranks_separately_and_modifies_matching_checks() -> None:
    ability = _base_active_ability(
        ability_id="skill_check",
        name="Skill Check",
        dimensions=["position"],
        resource_cost={},
        cooldown_turns=0,
        effect_ops=[{"dimension": "position", "op": "modify_next_check", "check": "stealth", "amount": 1}],
    )
    state: dict[str, Any] = {
        "player": {"resources": {}},
        "ability_tree": {"abilities": [ability]},
        "ability_state": {"ability_points": 0, "unlocked": ["skill_check"], "ranks": {"skill_check": 1}, "cooldowns": {}, "active_effects": []},
        "skill_progression": {"stealth": {"xp": 95, "rank": 1}},
    }

    skill_result = grant_skill_xp(state, "stealth", 10, source="sneak_action")

    assert skill_result.ok is True
    assert skill_result.skill_awards["stealth"] == {"xp_gained": 10, "xp": 5, "rank": 2}
    assert skill_result.skill_level_ups == [{"skill": "stealth", "from": 1, "to": 2}]
    assert skill_modifier_for_check(state, "stealth") == 1

    use_result = apply_ability_to_state(state, ability_name="Skill Check")

    assert use_result.ok is True
    assert state["runtime"]["effects"][0]["amount"] == 2
    assert state["runtime"]["effects"][0]["skill_modifier"] == 1
    assert state["skill_progression"]["knowledge"]["xp"] == 5
    assert state["skill_progression"]["knowledge"]["rank"] == 1


def test_effect_executor_mutates_all_gameplay_dimensions_and_records_trace() -> None:
    ability = _base_active_ability(
        ability_id="dimension_suite",
        name="Dimension Suite",
        purpose="world_influence",
        dimensions=[
            "resources",
            "information",
            "relationships",
            "access",
            "environment",
            "position",
            "narrative",
            "economy",
            "world",
        ],
        resource_cost={},
        cooldown_turns=0,
        effect_ops=[
            {"dimension": "resources", "op": "resource_delta", "target": "self", "resource": "stamina", "amount": 5},
            {"dimension": "information", "op": "reveal_clue", "clue_tag": "watch_rotation"},
            {"dimension": "position", "op": "modify_next_check", "check": "stealth", "amount": 2, "duration_turns": 1},
            {"dimension": "position", "op": "apply_status", "target": "self", "status": "hidden", "duration_turns": 2},
            {"dimension": "position", "op": "clear_status", "target": "self", "status": "exposed"},
            {"dimension": "relationships", "op": "modify_relationship", "relationship": "city_watch", "amount": 2},
            {"dimension": "relationships", "op": "modify_reputation", "amount": 1},
            {"dimension": "access", "op": "unlock_travel_option", "option_tag": "old_tunnel", "duration_turns": 3},
            {"dimension": "access", "op": "unlock_scene_affordance", "affordance": "hidden_panel", "duration_turns": 2},
            {"dimension": "environment", "op": "apply_scene_status", "status": "illuminated", "duration_turns": 2},
            {"dimension": "environment", "op": "create_hazard", "hazard": "smoke_screen", "duration_turns": 1},
            {"dimension": "environment", "op": "clear_hazard", "hazard": "old_fire"},
            {"dimension": "economy", "op": "modify_price_modifier", "tag": "black_market", "amount": -2},
            {"dimension": "world", "op": "modify_faction_alert", "faction_id": "city_watch", "amount": 3},
            {"dimension": "world", "op": "change_location_state", "location_id": "old_town", "state_key": "gate", "state_value": "open"},
            {"dimension": "world", "op": "add_world_rumor", "rumor_id": "safehouse_moved", "rumor": "The safehouse moved."},
            {"dimension": "narrative", "op": "unlock_dialogue_option", "option_tag": "ask_about_heir"},
            {"dimension": "narrative", "op": "grant_temp_affordance", "affordance": "temporary_alias", "duration_turns": 1},
            {"dimension": "narrative", "op": "advance_quest_signal", "quest_id": "missing_heir", "signal": "lead_found"},
            {"dimension": "narrative", "op": "complete_objective", "quest_id": "missing_heir", "objective_id": "find_clue"},
        ],
    )
    state: dict[str, Any] = {
        "player": {
            "resources": {"stamina": {"current": 10, "max": 20}},
            "statuses": [{"status": "exposed"}],
        },
        "ability_tree": {"abilities": [ability]},
        "ability_state": {"unlocked": ["dimension_suite"], "ranks": {"dimension_suite": 1}, "cooldowns": {}, "active_effects": []},
        "hotbar": {"1": "dimension_suite"},
        "scene_state": {"hazards": [{"hazard": "old_fire"}]},
        "quests": [{"quest_id": "missing_heir", "objectives": [{"objective_id": "find_clue", "status": "active", "completed": False}]}],
        "timeline": [],
        "journal": {"entries": []},
    }

    result = apply_ability_to_state(state, ability_name="Dimension Suite")

    assert result.ok is True
    assert all(effect.get("applied") is True for effect in result.effects)
    assert state["player"]["resources"]["stamina"] == {"current": 15, "max": 20}
    assert state["clues"][0]["tag"] == "watch_rotation"
    assert state["runtime"]["effects"][0]["check"] == "stealth"
    assert [status["status"] for status in state["player"]["statuses"]] == ["hidden"]
    assert state["relationships"][0]["score"] == 2
    assert state["world"]["reputation"]["score"] == 1
    assert state["narrative_affordances"]["travel"][0]["tag"] == "old_tunnel"
    assert any(row["tag"] == "hidden_panel" for row in state["narrative_affordances"]["scene"])
    assert any(row["tag"] == "temporary_alias" for row in state["narrative_affordances"]["scene"])
    assert state["scene_state"]["statuses"][0]["status"] == "illuminated"
    assert [row["hazard"] for row in state["scene_state"]["hazards"]] == ["smoke_screen"]
    assert state["economy"]["price_modifiers"]["black_market"]["amount"] == -2
    assert state["faction_state"]["factions"]["city_watch"]["alert"] == 3
    assert state["locations"]["old_town"]["state"]["gate"] == "open"
    assert state["world"]["rumors"][0]["rumor_id"] == "safehouse_moved"
    assert state["narrative_affordances"]["dialogue"][0]["tag"] == "ask_about_heir"
    assert state["quest_signals"][0]["signal"] == "lead_found"
    assert state["quests"][0]["objectives"][0]["status"] == "completed"
    assert len(state["mechanics"]["ability_effect_trace"]) == len(result.effects)
    assert "pending_dimension_effects" not in state["mechanics"]
    assert state["timeline"][0]["kind"] == "ability_effect"
    assert state["journal"]["entries"][0]["kind"] == "ability_effect"


def test_effect_executor_reports_missing_targets_as_structured_errors() -> None:
    ability = _base_active_ability(
        ability_id="missing_target",
        name="Missing Target",
        purpose="quest_progression",
        dimensions=["narrative"],
        resource_cost={},
        cooldown_turns=0,
        effect_ops=[
            {"dimension": "narrative", "op": "complete_objective", "quest_id": "missing_quest", "objective_id": "missing_objective"},
        ],
    )
    state: dict[str, Any] = {
        "player": {"resources": {}},
        "ability_tree": {"abilities": [ability]},
        "ability_state": {"unlocked": ["missing_target"], "ranks": {"missing_target": 1}, "cooldowns": {}, "active_effects": []},
        "hotbar": {"1": "missing_target"},
        "timeline": [],
        "journal": {"entries": []},
    }

    result = apply_ability_to_state(state, ability_name="Missing Target")

    assert result.ok is False
    assert result.error == "effect_target_unavailable"
    assert result.effects == [
        {
            "dimension": "narrative",
            "op": "complete_objective",
            "target": "missing_quest",
            "applied": False,
            "error": "target_unavailable",
            "detail": "missing quest missing_quest",
        }
    ]
    assert state["mechanics"]["ability_effect_trace"][0]["applied"] is False
    assert state["timeline"] == []
    assert state["journal"]["entries"] == []
