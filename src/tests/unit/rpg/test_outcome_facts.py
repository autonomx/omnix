"""The outcome card's facts (RQ-7.2; narration/presentation/outcome_facts.py): what a turn changed, in plain words."""
from __future__ import annotations

from app.apps.rpg.foundation.state.changes import (
    CheckResolved,
    CombatAdvanced,
    ConditionsChanged,
    ExperienceGained,
    HpChanged,
    ItemAdded,
    ItemRemoved,
    LevelReached,
    PurseChanged,
    QuestOffered,
    QuestStatusChanged,
    QuestStepCompleted,
    RegardChanged,
    TurnCounted,
)
from app.apps.rpg.narration.presentation.outcome_facts import outcome_facts

DOCUMENT = {"simulation_state": {
    "quest_state": {"quests": [{"quest_id": "quest:rats", "title": "Rats in the Cellar"}]},
    "world_model": {"items": [{"id": "item:torch", "name": "Torch"}]}}}


def test_each_change_the_player_should_see_is_one_plain_fact_with_its_tone() -> None:
    facts = outcome_facts([
        TurnCounted(turn_count=4),  # bookkeeping: not shown
        PurseChanged(delta_copper=-125, reason="bought"), ItemAdded(item_id="item:rope", name="Rope", quantity=2),
        ItemRemoved(item_id="item:torch"), HpChanged(delta=-6), HpChanged(delta=0),
        ConditionsChanged(actor_id="player", conditions=({"kind": "wounded"},)),
        ConditionsChanged(actor_id="npc:mira", conditions=()),
        ExperienceGained(amount=50), LevelReached(level=3, xp=0, xp_to_next=300),
        QuestOffered(quest_id="quest:wolves", npc_id="npc:bran", quest={"title": "Wolves on the Road"}),
        QuestStepCompleted(quest_id="quest:rats", stage=1, next_objective="Tell Bran"),
        QuestStatusChanged(quest_id="quest:rats", status="completed"),
        CheckResolved(kind="pick_lock", natural=12, bonus=-1, total=11, difficulty=13, band="cost"),
        RegardChanged(npc_id="npc:bran", name="Bran", delta=-5),
        CombatAdvanced(combat_state={"active": False, "ended_reason": "evaded"}),
    ], DOCUMENT)
    assert [(fact.kind, fact.text, fact.tone) for fact in facts] == [
        ("coin", "-1 gold, 2 silver, 5 copper", "loss"), ("item", "+Rope x2", "gain"), ("item", "-Torch", "loss"),
        ("health", "-6 health", "loss"), ("condition", "Wounded", "loss"), ("experience", "+50 experience", "gain"),
        ("level", "Level 3", "gain"), ("offer", "Offered: Wolves on the Road", "neutral"),
        ("quest", "Rats in the Cellar: step done; next, Tell Bran", "gain"),
        ("quest", "Rats in the Cellar: complete", "gain"),
        ("check", "Pick lock: d20 12 - 1 = 11 against 13, a success at a cost", "gain"),
        ("regard", "Bran trusts you less", "loss"), ("fight", "Slipped past", "gain")]
