from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.rpg.session.passive_traits import apply_passive_hooks_to_state, collect_narrative_trait_context


def _passive(**overrides: Any) -> dict[str, Any]:
    ability = {
        "ability_id": "keen_eye",
        "kind": "passive",
        "name": "Keen Eye",
        "description": "Improves clue discovery through a deterministic hook.",
        "capability": "recon",
        "power_source": "mundane",
        "purpose": "information_gathering",
        "dimensions": ["information", "narrative"],
        "level_required": 1,
        "rank": 1,
        "max_rank": 3,
        "resource_cost": {},
        "cooldown_turns": 0,
        "prerequisites": [],
        "hooks": ["on_investigation_check"],
        "effect_ops": [],
    }
    ability.update(overrides)
    return ability


def _trait(**overrides: Any) -> dict[str, Any]:
    ability = {
        "ability_id": "former_detective",
        "kind": "narrative_trait",
        "name": "Former Detective",
        "description": "A saved grounded fact that unlocks investigative context.",
        "capability": "recon",
        "power_source": "mundane",
        "purpose": "information_gathering",
        "dimensions": ["information", "relationships", "narrative"],
        "level_required": 1,
        "rank": 1,
        "max_rank": 1,
        "resource_cost": {},
        "cooldown_turns": 0,
        "prerequisites": [],
        "influence_tags": ["recognize_police_procedure", "unlock_detective_dialogue_paths"],
        "effect_ops": [],
    }
    ability.update(overrides)
    return ability


def test_passive_hook_applies_matching_unlocked_passives_only() -> None:
    state: dict[str, Any] = {
        "ability_tree": {
            "abilities": [
                _passive(),
                _passive(ability_id="locked_eye", name="Locked Eye"),
                _passive(ability_id="battle_ready", name="Battle Ready", hooks=["on_combat_start"]),
            ]
        },
        "ability_state": {"unlocked": ["keen_eye"], "ranks": {"keen_eye": 2}, "cooldowns": {}, "active_effects": []},
    }

    result = apply_passive_hooks_to_state(state, "on_investigation_check", {"check": "investigation", "scene_tags": ["crime_scene"]})

    assert result.ok is True
    assert len(result.applied) == 1
    assert result.applied[0]["ability_id"] == "keen_eye"
    assert result.applied[0]["rank"] == 2
    assert state["runtime"]["passive_modifiers"][0]["amount"] == 2
    assert state["runtime"]["passive_modifiers"][0]["check"] == "investigation"
    assert state["narrative_affordances"]["passive"][0]["tag"] == "keen_eye:on_investigation_check"


def test_passive_hook_ignores_locked_passives() -> None:
    state: dict[str, Any] = {
        "ability_tree": {"abilities": [_passive()]},
        "ability_state": {"unlocked": [], "ranks": {}, "cooldowns": {}, "active_effects": []},
    }

    result = apply_passive_hooks_to_state(state, "on_investigation_check", {"check": "investigation"})

    assert result.ok is True
    assert result.applied == []
    assert "runtime" not in state
    assert "mechanics" not in state


def test_passive_hook_records_trace() -> None:
    state: dict[str, Any] = {
        "ability_tree": {"abilities": [_passive()]},
        "ability_state": {"unlocked": ["keen_eye"], "ranks": {"keen_eye": 1}, "cooldowns": {}, "active_effects": []},
    }

    apply_passive_hooks_to_state(state, "on_investigation_check", {"check": "investigation"})

    trace = state["mechanics"]["passive_hook_trace"][0]
    assert trace["ability_id"] == "keen_eye"
    assert trace["hook"] == "on_investigation_check"
    assert trace["modifier"]["check"] == "investigation"
    assert trace["affordance"]["tag"] == "keen_eye:on_investigation_check"


def test_passive_hook_can_modify_check_context_or_affordance_candidates() -> None:
    passive = _passive(
        ability_id="systems_discipline",
        name="Systems Discipline",
        hooks=["on_investigation_check"],
        dimensions=["information", "position"],
        effect_ops=[{"dimension": "position", "op": "modify_next_check", "check": "systems_intrusion", "amount": 2}],
    )
    state: dict[str, Any] = {
        "ability_tree": {"abilities": [passive]},
        "ability_state": {"unlocked": ["systems_discipline"], "ranks": {"systems_discipline": 1}, "cooldowns": {}, "active_effects": []},
    }

    result = apply_passive_hooks_to_state(state, "on_investigation_check", {"check": "systems_intrusion", "target": "locked terminal"})

    assert result.ok is True
    assert len(result.effects) == 1
    assert result.effects[0]["op"] == "modify_next_check"
    assert state["runtime"]["passive_modifiers"][0]["check"] == "systems_intrusion"
    assert state["runtime"]["effects"][0]["check"] == "systems_intrusion"
    assert state["narrative_affordances"]["passive"][0]["tag"] == "systems_discipline:on_investigation_check"


def test_narrative_trait_context_collects_unlocked_traits() -> None:
    state: dict[str, Any] = {
        "ability_tree": {"abilities": [_trait(), _trait(ability_id="locked_trait", name="Locked Trait", influence_tags=["locked_tag"])]},
        "ability_state": {"unlocked": ["former_detective"], "ranks": {}, "cooldowns": {}, "active_effects": []},
    }

    context = collect_narrative_trait_context(state)

    assert context["count"] == 1
    assert context["traits"][0]["trait_id"] == "former_detective"
    assert context["traits"][0]["name"] == "Former Detective"
    assert context["influence_tags"] == ["recognize_police_procedure", "unlock_detective_dialogue_paths"]
    assert {row["tag"] for row in context["affordance_candidates"]} == {
        "recognize_police_procedure",
        "unlock_detective_dialogue_paths",
    }


def test_narrative_trait_context_ignores_locked_traits() -> None:
    state: dict[str, Any] = {
        "ability_tree": {"abilities": [_trait()]},
        "ability_state": {"unlocked": [], "ranks": {}, "cooldowns": {}, "active_effects": []},
    }

    context = collect_narrative_trait_context(state)

    assert context == {"traits": [], "influence_tags": [], "affordance_candidates": [], "count": 0}


def test_narrative_traits_do_not_directly_mutate_state_without_effect_ops() -> None:
    state: dict[str, Any] = {
        "ability_tree": {"abilities": [_trait()]},
        "ability_state": {"unlocked": ["former_detective"], "ranks": {}, "cooldowns": {}, "active_effects": []},
    }
    before = deepcopy(state)

    context = collect_narrative_trait_context(state)

    assert context["count"] == 1
    assert state == before
    assert "runtime" not in state
    assert "mechanics" not in state
