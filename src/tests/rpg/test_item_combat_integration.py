from __future__ import annotations

from app.rpg.session.item_combat_integration import (
    actor_equipment,
    actor_resource_snapshot,
    resolve_actor_item_damage,
    select_item_damage_source,
)


def test_actor_equipment_reads_nested_loadout_shapes() -> None:
    actor = {"name": "Scout", "loadout": {"equipment": [{"slot": "Tool", "name": "Field Kit"}]}}

    assert actor_equipment(actor) == [{"slot": "Tool", "name": "Field Kit"}]


def test_select_item_damage_source_prefers_equipped_damage_slot() -> None:
    actor = {
        "name": "Ari",
        "equipment": [
            {"slot": "Tool", "name": "Lamp", "damage": {"fire": 1}},
            {"slot": "Weapon", "name": "Practice Blade", "item_id": "practice_blade", "damage": {"slashing": 5}},
        ],
    }

    source = select_item_damage_source(actor)

    assert source["item_id"] == "practice_blade"
    assert source["damage"] == {"slashing": 5}


def test_resource_snapshot_accepts_health_resource_shapes() -> None:
    actor = {"resources": {"hp": {"current": 7, "max": 10}}}

    assert actor_resource_snapshot(actor) == {"key": "hp", "current": 7, "max": 10}


def test_actor_item_damage_resolves_against_defender_equipment() -> None:
    attacker = {
        "name": "Ari",
        "equipment": [{"slot": "Weapon", "name": "Training Saber", "item_id": "training_saber", "damage": {"slashing": 8, "fire": 2}}],
    }
    defender = {
        "name": "Bran",
        "resources": {"health": {"current": 12, "max": 12}},
        "equipment": [{"slot": "Armor", "name": "Scale Vest", "defense": {"physical": 1, "slashing": 2}, "resistances": {"fire": 1}}],
    }

    result = resolve_actor_item_damage(attacker, defender)

    assert result["ok"] is True
    assert result["attack"]["source_item_id"] == "training_saber"
    assert result["resolution"]["resolved_damage"] == {"slashing": 5, "fire": 1}
    assert result["resolution"]["total_resolved"] == 6
    assert result["effects"] == [
        {"action": "change_resource", "target": "Bran", "resource": "health", "delta": -6, "before": 12, "after": 6}
    ]
    assert result["trace"]["event"] == "item_combat_damage_resolved"
    assert result["trace"]["total_resolved"] == 6
    assert result["mechanics_source"] == "engine_item_combat_integration_v1"


def test_actor_item_damage_uses_unarmed_fallback_and_marks_defeat() -> None:
    attacker = {"name": "Ari", "equipment": []}
    defender = {"name": "Training Dummy", "resources": {"health": {"current": 1, "max": 1}}, "equipment": []}

    result = resolve_actor_item_damage(attacker, defender)

    assert result["attack"]["source_item_id"] == "unarmed"
    assert result["resolution"]["resolved_damage"] == {"bludgeoning": 1}
    assert result["effects"][0]["after"] == 0
    assert result["defeated"] is True
    assert result["trace"]["defeated"] is True
