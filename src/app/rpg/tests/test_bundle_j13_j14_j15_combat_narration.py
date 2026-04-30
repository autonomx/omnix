from app.rpg.narration.combat_contract import build_combat_narration_contract
from app.rpg.narration.combat_validator import validate_combat_narration


def _combat_state():
    return {
        "active": True,
        "round": 1,
        "current_actor_id": "enemy:bandit_1",
        "participants": {
            "player": {"actor_id": "player", "name": "You", "side": "party", "hp": 20},
            "enemy:bandit_1": {"actor_id": "enemy:bandit_1", "name": "Bandit", "side": "enemy", "hp": 2},
        },
    }


def test_combat_contract_for_non_defeating_attack_blocks_death():
    contract = build_combat_narration_contract(
        combat_result={
            "reason": "combat_attack_resolved",
            "actor_id": "player",
            "target_id": "enemy:bandit_1",
            "hit": True,
            "damage_applied": 6,
            "target_hp_before": 8,
            "target_hp_after": 2,
            "defeated": False,
        },
        combat_state=_combat_state(),
    )

    assert contract["facts"]["defeated"] is False
    assert contract["facts"]["target_name"] == "Bandit"

    validation = validate_combat_narration(
        narration_payload={
            "narration": "Your arrow kills the bandit and leaves him dead.",
            "action": "The bandit dies.",
        },
        combat_contract=contract,
    )

    assert validation["ok"] is False
    assert "combat_narration_invented_death" in validation["warnings"]


def test_combat_validator_accepts_grounded_attack():
    contract = build_combat_narration_contract(
        combat_result={
            "reason": "combat_attack_resolved",
            "actor_id": "player",
            "target_id": "enemy:bandit_1",
            "hit": True,
            "damage_applied": 6,
            "target_hp_before": 8,
            "target_hp_after": 2,
            "defeated": False,
        },
        combat_state=_combat_state(),
    )

    validation = validate_combat_narration(
        narration_payload={
            "narration": "Your shot catches the Bandit hard and drives him back, but he stays upright.",
            "action": "You wound the Bandit.",
        },
        combat_contract=contract,
    )

    assert validation["ok"] is True
    assert validation["warnings"] == []


def test_combat_validator_requires_defeat_acknowledgement():
    contract = build_combat_narration_contract(
        combat_result={
            "reason": "combat_defeat_resolved",
            "actor_id": "player",
            "target_id": "enemy:bandit_1",
            "hit": True,
            "damage_applied": 4,
            "target_hp_before": 2,
            "target_hp_after": 0,
            "defeated": True,
        },
        combat_state=_combat_state(),
    )

    validation = validate_combat_narration(
        narration_payload={
            "narration": "Your arrow strikes the Bandit and sends him staggering.",
            "action": "You wound the Bandit.",
        },
        combat_contract=contract,
    )

    assert validation["ok"] is False
    assert "combat_narration_missing_defeat_acknowledgement" in validation["warnings"]