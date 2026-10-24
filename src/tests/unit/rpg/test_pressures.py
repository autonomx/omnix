"""The world's pressures and what the hero does to them (rules/pressures.py; docs/rpg/design/quests.md)."""
from __future__ import annotations

from app.apps.rpg.foundation.state import reduce
from app.apps.rpg.foundation.state.changes import CombatAdvanced, QuestStatusChanged
from app.apps.rpg.rules.pressures import lever_pulls, pressure_offers
from app.apps.rpg.world.causal_runtime import advance_causal_runtime, bootstrap_causal_runtime, replay_causal_events

ROADS = {"pressure_id": "pressure:roads:march", "name": "Danger on the roads", "summary": "Wolves prey on travellers.",
         "severity": 70.0, "trend": "volatile", "escalation_threshold": 90.0, "resolution_threshold": 15.0,
         "next_tick_delta": {"target_id": "region:march", "dimension": "trade_access", "operation": "decrease",
                             "value": 1.0},
         "levers": [{"action": "defeat:creature:wolf", "effect": "lower", "amount": 8.0},
                    {"action": "quest:quest:roads", "effect": "lower", "amount": 30.0}]}


def _document(*, severity: float = 70.0, quests: list | None = None) -> dict:
    runtime = bootstrap_causal_runtime({"present_day_state": {"state": {"region:march": {"trade_access": 30}}},
                                        "pressure_plan": {"pressures": [{**ROADS, "severity": severity}]}})
    runtime, _ = advance_causal_runtime(runtime, tick=1)
    return {"manifest": {}, "state": {"quests": list(quests or [])}, "simulation_state": {
        "causal_world_runtime": runtime,
        "campaign_mechanics": {"creatures": {"creature:wolf": {"definition_id": "creature:wolf", "name": "Grey Wolf"}}},
        "world_model": {"locations": {"loc:gate": {"region_id": "region:march"}, "loc:far": {"region_id": "region:far"}},
                        "npcs": {"npc:rhea": {"name": "Rhea", "role": "village guard captain", "location_id": "loc:gate"},
                                 "npc:orik": {"name": "Orik", "role": "innkeeper", "location_id": "loc:gate"}}},
        "player_state": {"location_id": "loc:gate"}, "quest_state": {"quests": list(quests or [])}}}


def _severity(document: dict) -> float:
    cells = document["simulation_state"]["causal_world_runtime"]["state"]["cells"]
    return cells["pressure:roads:march"]["values"]["pressure_severity"]


def _won(*foes: str) -> CombatAdvanced:
    return CombatAdvanced(combat_state={"active": False, "ended_reason": "enemy_side_defeated", "participants": {
        f"enemy:{index}": {"side": "enemy", "definition_id": foe, "hp": 0} for index, foe in enumerate(foes)}})


def test_felled_creatures_and_a_quest_done_pull_the_levers_as_a_replayable_event() -> None:
    document = _document()
    before = _severity(document)
    changes, lines = lever_pulls(document["simulation_state"], [_won("creature:wolf", "creature:wolf"),
                                                                  QuestStatusChanged(quest_id="quest:roads", status="completed")])
    after, _ = reduce(document, changes)
    assert _severity(after) == before - 16 - 30 and lines == ["Danger on the roads: it eases."]
    runtime = after["simulation_state"]["causal_world_runtime"]
    assert replay_causal_events(runtime["initial_state"], runtime["events"]) == runtime["state"]  # history still adds up
    advance_causal_runtime(runtime, tick=2)  # and the clock goes on from it
    assert lever_pulls(after["simulation_state"], [_won("creature:bat")]) == ([], [])  # nothing it answers to


def test_a_high_pressure_raises_one_side_quest_from_someone_whose_work_fits() -> None:
    document = _document()
    changes, lines = pressure_offers(document["simulation_state"])
    assert [(change.npc_id, change.quest["steps"][0]["all_of"]) for change in changes] == [
        ("npc:rhea", [{"defeat": "creature:wolf", "count": 3}])]  # the captain, not the innkeeper; 3 x 8 eases 20
    assert lines == ['Rhea asks for your help: "Danger on the roads". Defeat 3 Grey Wolves.']
    offered, _ = reduce(document, changes)
    quest = offered["simulation_state"]["quest_state"]["quests"][0]
    assert quest["status"] == "available" and quest["offered_by"] == "npc:rhea" and quest["rewards"] == ["10 silver"]
    assert pressure_offers(offered["simulation_state"]) == ([], [])  # one open quest for each pressure
    assert pressure_offers(_document(severity=50)["simulation_state"]) == ([], [])  # not yet pressing
    away = _document()
    away["simulation_state"]["player_state"]["location_id"] = "loc:far"
    assert pressure_offers(away["simulation_state"]) == ([], [])  # no one here to ask
    alone = _document()
    alone["simulation_state"]["world_model"]["npcs"]["npc:rhea"]["location_id"] = "loc:far"
    assert pressure_offers(alone["simulation_state"]) == ([], [])  # the captain is elsewhere: only the innkeeper
