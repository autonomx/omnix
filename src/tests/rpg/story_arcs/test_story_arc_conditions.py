from app.rpg.lore.state import reveal_lore_to_player, upsert_lore_entry
from app.rpg.memory.observation import record_told_memory
from app.rpg.puzzles.state import set_puzzle_flag, start_puzzle
from app.rpg.quests.state import start_quest
from app.rpg.story_arcs.conditions import evaluate_story_arc_condition
from app.rpg.story_arcs.state import set_story_arc_flag, start_story_arc


def test_arc_pressure_condition():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:bandit_pressure", pressure=60)

    result = evaluate_story_arc_condition(
        simulation_state,
        {"type": "arc_pressure_at_least", "arc_id": "arc:bandit_pressure", "minimum": 50},
    )

    assert result["ok"] is True


def test_arc_flag_condition():
    simulation_state = {}
    start_story_arc(simulation_state, "arc:bandit_pressure")
    set_story_arc_flag(simulation_state, "arc:bandit_pressure", "bran_warned", True)

    result = evaluate_story_arc_condition(
        simulation_state,
        {"type": "arc_flag", "arc_id": "arc:bandit_pressure", "flag": "bran_warned", "expected": True},
    )

    assert result["ok"] is True


def test_lore_condition_delegation():
    simulation_state = {}
    upsert_lore_entry(simulation_state, {"lore_id": "lore:red_sashes", "title": "The Red Sashes"})
    reveal_lore_to_player(simulation_state, "lore:red_sashes")

    result = evaluate_story_arc_condition(
        simulation_state,
        {"type": "lore_revealed_to_player", "lore_id": "lore:red_sashes"},
    )

    assert result["ok"] is True


def test_quest_and_puzzle_conditions():
    simulation_state = {}
    start_quest(simulation_state, "quest:stop_red_sashes", stage="investigate")
    start_puzzle(simulation_state, "puzzle:cellar_runes")
    set_puzzle_flag(simulation_state, "puzzle:cellar_runes", "rune_unlocked", True)

    quest_result = evaluate_story_arc_condition(
        simulation_state,
        {"type": "quest_stage", "quest_id": "quest:stop_red_sashes", "stage": "investigate"},
    )
    puzzle_result = evaluate_story_arc_condition(
        simulation_state,
        {"type": "puzzle_flag", "puzzle_id": "puzzle:cellar_runes", "flag": "rune_unlocked", "expected": True},
    )

    assert quest_result["ok"] is True
    assert puzzle_result["ok"] is True


def test_npc_memory_condition():
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

    result = evaluate_story_arc_condition(
        simulation_state,
        {
            "type": "npc_knows_memory",
            "npc_id": "bran",
            "event_id": "evt:bandits",
            "tags": ["bandit"],
        },
    )

    assert result["ok"] is True