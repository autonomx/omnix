from app.rpg.memory.observation import record_told_memory
from app.rpg.puzzles.state import set_puzzle_flag, start_puzzle
from app.rpg.quests.conditions import evaluate_quest_condition
from app.rpg.quests.state import start_quest
from app.rpg.social.reputation import set_relationship_values
from tests.rpg.spatial.fixtures import tavern_spatial_fixture


def test_condition_has_item_manual_inventory():
    simulation_state = {"manual_inventory_items": ["cellar_key"]}
    result = evaluate_quest_condition(
        simulation_state,
        {"type": "has_item", "item_id": "cellar_key"},
    )

    assert result["ok"] is True


def test_condition_social_trust_at_least():
    simulation_state = {}
    set_relationship_values(simulation_state, "bran", {"trust": 40})

    result = evaluate_quest_condition(
        simulation_state,
        {"type": "social_trust_at_least", "npc_id": "bran", "minimum": 30},
    )

    assert result["ok"] is True


def test_condition_npc_knows_memory():
    simulation_state = {}
    record_told_memory(
        simulation_state,
        "bran",
        speaker_id="player",
        event_id="evt:bandits",
        summary="The player told Bran about bandits.",
        facts={"actor_id": "bandits"},
        tags=["bandit"],
        verified=True,
    )

    result = evaluate_quest_condition(
        simulation_state,
        {
            "type": "npc_knows_memory",
            "npc_id": "bran",
            "event_id": "evt:bandits",
            "tags": ["bandit"],
        },
    )

    assert result["ok"] is True


def test_condition_entity_in_area():
    simulation_state = {"spatial_graph": tavern_spatial_fixture()}
    result = evaluate_quest_condition(
        simulation_state,
        {
            "type": "entity_in_area",
            "entity_id": "player",
            "area_id": "tavern_common_room",
        },
    )

    assert result["ok"] is True


def test_condition_quest_stage():
    simulation_state = {}
    start_quest(simulation_state, "quest:rat_cellar", stage="investigate")
    result = evaluate_quest_condition(
        simulation_state,
        {
            "type": "quest_stage",
            "quest_id": "quest:rat_cellar",
            "stage": "investigate",
        },
    )

    assert result["ok"] is True


def test_condition_puzzle_flag_reports_debug_fields():
    simulation_state = {}
    start_puzzle(simulation_state, "puzzle:cellar_runes", state="initial")
    set_puzzle_flag(simulation_state, "puzzle:cellar_runes", "rune_unlocked", True)

    result = evaluate_quest_condition(
        simulation_state,
        {
            "type": "puzzle_flag",
            "puzzle_id": "puzzle:cellar_runes",
            "flag": "rune_unlocked",
            "expected": True,
        },
    )

    assert result["ok"] is True
    assert result["puzzle_state_exists"] is True
    assert result["puzzle_exists"] is True
    assert "puzzle:cellar_runes" in result["available_puzzle_ids"]
    assert "rune_unlocked" in result["available_flags"]