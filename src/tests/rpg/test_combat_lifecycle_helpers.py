from __future__ import annotations

from app.rpg.combat_lifecycle import (
    CombatAction,
    CombatState,
    Combatant,
    award_xp,
    choose_enemy_action,
    combat_report_payload,
    loot_allowed,
    resolve_attack,
)


def _state() -> CombatState:
    return CombatState(
        "enc-1",
        (
            Combatant("player", "player", 12, 10, 10),
            Combatant("bran", "party", 10, 8, 8),
            Combatant("raider", "enemy", 8, 3, 6, "attack_weakest"),
        ),
    )


def test_initiative_order_and_current_combatant_are_stable() -> None:
    state = _state()

    assert [combatant.combatant_id for combatant in state.initiative_order()] == ["player", "bran", "raider"]
    assert state.current_combatant().combatant_id == "player"


def test_resolve_attack_updates_hp_and_narration_facts() -> None:
    resolution = resolve_attack(_state(), CombatAction("player", "raider", 2))

    assert resolution.ok is True
    assert resolution.reason == "hit"
    assert "2 damage" in resolution.narration_facts[0]


def test_defeat_allows_loot_and_zero_hp_fact() -> None:
    resolution = resolve_attack(_state(), CombatAction("player", "raider", 3))

    assert resolution.defeat_outcome == "defeated"
    assert loot_allowed(resolution) is True
    assert resolution.narration_facts[-1] == "raider reached 0 HP."


def test_enemy_policy_targets_weakest_opponent() -> None:
    action = choose_enemy_action(_state(), "raider")

    assert action is not None
    assert action.actor_id == "raider"
    assert action.target_id == "bran"


def test_turn_advances_round_after_order_wrap() -> None:
    state = _state().advance_turn().advance_turn().advance_turn()

    assert state.round_number == 2
    assert state.current_combatant().combatant_id == "player"


def test_xp_awards_only_return_non_negative_amounts() -> None:
    assert award_xp("kill", 25) == 25
    assert award_xp("quest", -10) == 0


def test_combat_report_payload_is_debug_friendly() -> None:
    payload = combat_report_payload(_state())

    assert payload["encounter_id"] == "enc-1"
    assert payload["initiative_order"] == ["player", "bran", "raider"]
