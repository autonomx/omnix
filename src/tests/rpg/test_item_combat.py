from __future__ import annotations

from app.rpg.session.item_combat import (
    build_attack_profile_from_item,
    equipment_defense_profile,
    equipment_resistance_profile,
    item_damage_profile,
    resolve_damage_against_defense,
    resolve_item_attack_against_equipment,
)


def test_item_damage_profile_normalizes_dict_and_list_shapes() -> None:
    assert item_damage_profile({"damage": {"slashing": 4, "fire": 2, "ignored": 0}}) == {"slashing": 4, "fire": 2}
    assert item_damage_profile({"damage": [{"type": "piercing", "amount": 3}, {"piercing": 2}]}) == {"piercing": 5}


def test_equipment_profiles_sum_defense_and_resistances() -> None:
    equipment = [
        {"name": "Scale Vest", "defense": {"physical": 1, "slashing": 3}},
        {"name": "Heat Lining", "defense": {"slashing": 1}, "resistances": {"fire": 2}},
    ]

    assert equipment_defense_profile(equipment) == {"physical": 1, "slashing": 4}
    assert equipment_resistance_profile(equipment) == {"fire": 2}


def test_damage_resolution_reduces_matching_types_only() -> None:
    result = resolve_damage_against_defense({"slashing": 10, "fire": 3}, {"slashing": 4}, resistances={"fire": 1})

    assert result["resolved_damage"] == {"slashing": 6, "fire": 2}
    assert result["total_incoming"] == 13
    assert result["total_resolved"] == 8
    assert result["reductions"]["slashing"] == {
        "incoming": 10,
        "defense": 4,
        "physical_defense": 0,
        "resistance": 0,
        "reduced_by": 4,
        "final": 6,
    }
    assert result["reductions"]["fire"] == {
        "incoming": 3,
        "defense": 0,
        "physical_defense": 0,
        "resistance": 1,
        "reduced_by": 1,
        "final": 2,
    }


def test_physical_defense_applies_to_physical_damage_types() -> None:
    result = resolve_damage_against_defense({"piercing": 5, "cold": 5}, {"physical": 2})

    assert result["resolved_damage"] == {"piercing": 3, "cold": 5}
    assert result["reductions"]["piercing"]["physical_defense"] == 2
    assert result["reductions"]["cold"]["physical_defense"] == 0


def test_item_attack_against_equipment_returns_traceable_resolution() -> None:
    attacker = {"item_id": "training_blade", "name": "Training Blade", "damage": {"slashing": 7, "fire": 1}}
    defender = [{"slot": "Armor", "name": "Scale Vest", "defense": {"slashing": 2}, "resistances": {"fire": 1}}]

    result = resolve_item_attack_against_equipment(attacker, defender)

    assert build_attack_profile_from_item(attacker) == result["attack"]
    assert result["resolution"]["resolved_damage"] == {"slashing": 5, "fire": 0}
    assert result["resolution"]["total_resolved"] == 5
    assert result["mechanics_source"] == "engine_item_combat_resolution_v1"
