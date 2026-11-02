"""Quests of steps, branches and deadlines (rules/quest/progress.py; docs/rpg/design/quests.md)."""
from __future__ import annotations

from app.apps.rpg.foundation.state import reduce
from app.apps.rpg.foundation.state.changes import CheckResolved, CombatAdvanced, DialogueExchanged
from app.apps.rpg.rules.quest.arrival import quest_rewards
from app.apps.rpg.rules.quest.progress import accepted_step, open_steps, quest_progress

RATS = {"quest_id": "quest:rats", "title": "Cellar Rats", "status": "active", "giver_id": "npc:bran",
        "rewards": ["5 silver"], "steps": [
            {"id": "clear", "summary": "Clear the rats", "all_of": [{"defeat": "creature:rat", "count": 2}]},
            {"id": "report", "summary": "Tell Bran", "any_of": [{"talk": "npc:bran"}, {"check": "persuade"}]}]}


def _document(quest: dict, *, minute: int = 600) -> dict:
    return {"manifest": {}, "state": {"quests": [dict(quest)]},
            "simulation_state": {"environment": {"absolute_minutes": minute},
                                 "world_model": {"npcs": {"npc:bran": {"name": "Bran"}}},
                                 "player_state": {"location_id": "loc:inn", "level": 1, "xp": 0},
                                 "quest_state": {"quests": [dict(quest)]}}}


def _won(*foes: str) -> CombatAdvanced:
    return CombatAdvanced(combat_state={"active": False, "ended_reason": "enemy_side_defeated", "participants": {
        f"enemy:{index}": {"side": "enemy", "definition_id": foe, "hp": 0} for index, foe in enumerate(foes)}})


def _advance(document: dict, applied: list) -> tuple[dict, list, list[str]]:
    simulation = document["simulation_state"]
    changes, lines = quest_progress(simulation, applied, lambda quest: quest_rewards(simulation, quest))
    after, _ = reduce(document, changes) if changes else (document, None)
    return after, changes, lines


def _quest(document: dict) -> dict:
    return document["simulation_state"]["quest_state"]["quests"][0]


def test_a_stage_done_advances_the_quest_and_the_last_completes_it_with_its_rewards() -> None:
    document, _, lines = _advance(_document(RATS), [_won("creature:rat")])
    assert _quest(document)["progress"]["counts"] == {"creature:rat": 1} and not lines  # one of two
    document, _, lines = _advance(document, [_won("creature:rat")])
    assert _quest(document)["progress"]["stage"] == 1 and _quest(document)["objective"] == "Tell Bran"
    assert lines == ["Cellar Rats: Clear the rats. Next: Tell Bran."]
    document, changes, lines = _advance(document, [CheckResolved(kind="persuade", natural=15, band="success")])
    assert _quest(document)["status"] == "completed" and _quest(document)["progress"]["branches"] == [
        {"stage": 1, "branch": 1}]  # the other way through: a persuading word
    assert any(change.type == "purse_changed" for change in changes) and lines[-1].startswith("Quest complete")


def test_a_deadline_gone_by_fails_the_quest_and_costs_the_givers_trust() -> None:
    timed = {**RATS, "deadline_hours": 24, "accepted_at_minute": 600}
    document, _, _ = _advance(_document(timed, minute=600 + 23 * 60), [DialogueExchanged(npc_id="npc:bran")])
    assert _quest(document)["status"] == "active"
    document, changes, lines = _advance(_document(timed, minute=600 + 24 * 60), [])
    assert _quest(document)["status"] == "failed" and lines == ["Cellar Rats has failed: the time for it ran out."]
    assert [(change.npc_id, change.delta) for change in changes if change.type == "regard_changed"] == [("npc:bran", -10)]


def test_a_talk_about_something_needs_the_line_to_answer_its_step() -> None:
    """EV-3: a step that asks something particular of someone is done by a line whose reading names it (its address,
    accepted by the plan); talking to them of anything else does not do it, and no word of the line is matched."""
    rumor = {"quest_id": "quest:rumor", "title": "Rumor", "status": "active", "steps": [
        {"id": "ask", "summary": "Ask Bran", "any_of": [{"talk": "npc:bran", "about": ["rumor", "rumour"]}]}]}
    document, _, _ = _advance(_document(rumor), [DialogueExchanged(npc_id="npc:bran", player_line="Which RUMOR is true?")])
    assert _quest(document)["status"] == "active"  # the words alone do nothing
    document, _, _ = _advance(document, [DialogueExchanged(npc_id="npc:bran", step="quest:rumor|ask|1")])
    assert _quest(document)["status"] == "active"  # a way the step does not have
    assert open_steps(document["simulation_state"], "npc:bran") == [("quest:rumor|ask|0", "Ask Bran (about: rumor, rumour)")]
    assert accepted_step(document["simulation_state"], "npc:orik", "quest:rumor|ask|0") == ""  # not Orik's to answer
    document, _, _ = _advance(document, [DialogueExchanged(npc_id="npc:bran", step="quest:rumor|ask|0")])
    assert _quest(document)["status"] == "completed"


def test_a_companion_step_is_done_by_one_named_or_by_anyone_in_the_party() -> None:
    """Aurelia's first night ends with a first companion chosen (the playtest: it ended on reaching the guild)."""
    def quest(who: str) -> dict:
        return {"quest_id": "quest:first", "title": "First Night", "status": "active", "steps": [
            {"id": "companion", "summary": "Choose a first companion", "all_of": [{"companion": who}]}]}

    alone = _document(quest("anyone"))
    assert _advance(alone, [])[1] == []
    joined = _document(quest("anyone"))
    joined["simulation_state"]["player_state"]["party_state"] = {"companions": [{"npc_id": "npc:liora"}]}
    assert _quest(_advance(joined, [])[0])["status"] == "completed"
    named = _document(quest("npc:bran"))
    named["simulation_state"]["player_state"]["party_state"] = {"companions": [{"npc_id": "npc:liora"}]}
    assert _advance(named, [])[1] == []  # Liora is not Bran


def test_a_way_taken_tells_what_came_of_it() -> None:
    """The playtest: the finale's choice of the gate's fate ended on "Quest complete" and nothing of the choice."""
    gate = {"quest_id": "quest:gate", "title": "The Gate", "status": "active", "giver_id": "npc:bran", "steps": [
        {"id": "choose", "summary": "Choose the gate's fate", "any_of": [
            {"all_of": [{"talk": "npc:bran", "about": ["close"]}], "told": "The gate is sealed forever."},
            {"all_of": [{"talk": "npc:bran", "about": ["bridge"]}], "told": "The gate becomes a guarded bridge."}]}]}
    document, _, lines = _advance(_document(gate), [DialogueExchanged(npc_id="npc:bran", step="quest:gate|choose|1")])
    assert _quest(document)["status"] == "completed" and _quest(document)["progress"]["branches"] == [
        {"stage": 0, "branch": 1}]
    assert lines[0] == "The gate becomes a guarded bridge." and lines[1].startswith("Quest complete: The Gate.")
