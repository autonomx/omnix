from __future__ import annotations

from app.rpg.combat_runtime import build_combat_runtime_report


def _combatants() -> list[dict[str, object]]:
    return [
        {"combatant_id": "hero", "side": "player", "initiative": 10, "hp": 10, "max_hp": 10},
        {"combatant_id": "raider", "side": "enemy", "initiative": 5, "hp": 2, "max_hp": 2},
    ]


def test_phase21_combat_runtime_defeat_and_xp() -> None:
    report = build_combat_runtime_report(
        {
            "combat_state": {"encounter_id": "e1", "combatants": _combatants()},
            "combat_action": {"actor_id": "hero", "target_id": "raider", "damage": 3},
            "xp_source": "kill",
            "xp_amount": 25,
            "skill_use": {"skill_id": "sword", "delta": 1},
        }
    )

    assert report["ready"] is True
    assert report["expanded_defeat_outcome"] == "defeated"
    assert report["loot_allowed"] is True
    assert report["xp"]["amount"] == 25
    assert report["skill_progress"]["skill_id"] == "sword"


def test_phase21_combat_runtime_blocks_bad_xp_source() -> None:
    report = build_combat_runtime_report(
        {
            "combat_state": {"encounter_id": "e1", "combatants": _combatants()},
            "combat_action": {"actor_id": "hero", "target_id": "raider", "damage": 1},
            "xp_source": "dialogue",
        }
    )

    assert report["ready"] is False
    assert "xp_source_not_allowed:dialogue" in report["issues"]


def test_phase21_combat_runtime_expanded_non_loot_outcome() -> None:
    report = build_combat_runtime_report(
        {
            "combat_state": {"encounter_id": "e1", "combatants": _combatants()},
            "combat_action": {"actor_id": "hero", "target_id": "raider", "damage": 3},
            "defeat_outcome": "captured",
        }
    )

    assert report["expanded_defeat_outcome"] == "captured"
    assert report["loot_allowed"] is False
