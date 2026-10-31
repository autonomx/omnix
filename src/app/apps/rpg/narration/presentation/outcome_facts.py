"""What a turn changed, as the play screen's outcome card states it (RQ-7.2): coin, items, health, conditions,
experience, quest steps, offers and the dice, each a plain fact with a tone (a gain, a loss, or neither).

Built from the turn's changes and the campaign as the turn left it (for the names the changes only carry as ids);
the rules decided all of it, so the card says only what the changes say.
"""
from __future__ import annotations

from typing import Any, Literal, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.foundation.state.changes import (
    CheckResolved,
    CombatAdvanced,
    ConditionsChanged,
    ExperienceGained,
    HpChanged,
    ItemAdded,
    ItemDropped,
    ItemPickedUp,
    ItemRemoved,
    LevelReached,
    PurseChanged,
    QuestOffered,
    QuestStatusChanged,
    QuestStepCompleted,
    RegardChanged,
    StateChange,
)
from app.apps.rpg.foundation.state import access as _sections

FactKind = Literal["coin", "item", "health", "condition", "experience", "level", "quest", "offer", "check", "regard",
                   "fight"]
Tone = Literal["gain", "loss", "neutral"]
_BANDS = {"strong": "a strong success", "success": "a success", "cost": "a success at a cost", "failure": "a failure"}


class Suggestion(BaseModel):
    """Something the play screen offers to do next (RQ-7.3): a label, the command its log shows, and the card's action
    (evolution roadmap EV-9): the reading it carries (``family``, ``target_id``, ``second_target_id``, ``check``,
    ``slots``) and the turn it was offered at, played with no model call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str
    command: str
    action: dict[str, Any] = Field(default_factory=dict)


class OutcomeFact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: FactKind
    text: str
    tone: Tone = "neutral"


def _coins(copper: int) -> str:
    gold, rest = divmod(abs(copper), 100)
    silver, left = divmod(rest, 10)
    return ", ".join(f"{amount} {coin}" for amount, coin in ((gold, "gold"), (silver, "silver"), (left, "copper"))
                     if amount) or "0 copper"


def _quest_titles(document: Mapping[str, Any]) -> dict[str, str]:
    rows = _l(_d(_sections.quest_state_of(_d(_sections.simulation_state_of(document)))).get("quests"))
    return {_s(_d(row).get("quest_id") or _d(row).get("id")): _s(_d(row).get("title")) for row in rows}


def _item_names(document: Mapping[str, Any]) -> dict[str, str]:
    simulation = _d(_sections.simulation_state_of(document))
    carried = _l(_d(_sections.inventory_state_of(_d(_sections.player_state_of(simulation)))).get("items"))
    known = _l(_d(_sections.world_model_of(simulation)).get("items"))
    names = {_s(_d(row).get("id")): _s(_d(row).get("name")) for row in known}
    names.update({_s(_d(row).get("item_id")): _s(_d(row).get("name")) for row in carried})
    return {key: value for key, value in names.items() if key and value}


def outcome_facts(changes: Sequence[StateChange], document: Mapping[str, Any] | None) -> tuple[OutcomeFact, ...]:
    """The turn's facts for the outcome card, in the order the rules made them."""
    document = _d(document)
    titles, items = _quest_titles(document), _item_names(document)

    def item(item_id: str) -> str:
        return items.get(item_id) or item_id.rsplit(":", 1)[-1].replace("-", " ").replace("_", " ")

    def quest(quest_id: str) -> str:
        return titles.get(quest_id) or quest_id

    facts: list[OutcomeFact] = []
    for change in changes:
        if isinstance(change, PurseChanged) and change.delta_copper:
            gained = change.delta_copper > 0
            facts.append(OutcomeFact(kind="coin", text=f"{'+' if gained else '-'}{_coins(change.delta_copper)}",
                                     tone="gain" if gained else "loss"))
        elif isinstance(change, ItemAdded):
            facts.append(OutcomeFact(kind="item", text=f"+{change.name}" + (f" x{change.quantity}" if change.quantity > 1 else ""),
                                     tone="gain"))
        elif isinstance(change, ItemPickedUp):
            facts.append(OutcomeFact(kind="item", text=f"+{item(change.item_id)}", tone="gain"))
        elif isinstance(change, (ItemRemoved, ItemDropped)):
            facts.append(OutcomeFact(kind="item", text=f"-{item(change.item_id)}"
                                     + (f" x{change.quantity}" if change.quantity > 1 else ""), tone="loss"))
        elif isinstance(change, HpChanged) and change.delta:
            facts.append(OutcomeFact(kind="health", text=f"{'+' if change.delta > 0 else ''}{change.delta} health",
                                     tone="gain" if change.delta > 0 else "loss"))
        elif isinstance(change, ConditionsChanged) and change.actor_id == "player":
            kinds = [_s(_d(row).get("kind")) for row in change.conditions if _s(_d(row).get("kind"))]
            facts.append(OutcomeFact(kind="condition", text=", ".join(kinds).capitalize() if kinds else "Recovered",
                                     tone="loss" if kinds else "gain"))
        elif isinstance(change, ExperienceGained) and change.amount:
            facts.append(OutcomeFact(kind="experience", text=f"+{change.amount} experience", tone="gain"))
        elif isinstance(change, LevelReached):
            facts.append(OutcomeFact(kind="level", text=f"Level {change.level}", tone="gain"))
        elif isinstance(change, QuestOffered):
            title = _s(change.quest.get("title")) or quest(change.quest_id)
            facts.append(OutcomeFact(kind="offer", text=f"Offered: {title}"))
        elif isinstance(change, QuestStepCompleted):
            facts.append(OutcomeFact(kind="quest", text=f"{quest(change.quest_id)}: step done"
                                     + (f"; next, {change.next_objective}" if change.next_objective else ""), tone="gain"))
        elif isinstance(change, QuestStatusChanged):
            words = {"active": "taken on", "completed": "complete", "failed": "failed"}.get(change.status, change.status)
            facts.append(OutcomeFact(kind="quest", text=f"{quest(change.quest_id)}: {words}",
                                     tone="loss" if change.status == "failed" else "gain"))
        elif isinstance(change, CheckResolved):
            facts.append(OutcomeFact(
                kind="check", text=(f"{change.kind.replace('_', ' ').capitalize()}: d20 {change.natural} "
                                    f"{'+' if change.bonus >= 0 else '-'} {abs(change.bonus)} = {change.total} against "
                                    f"{change.difficulty}, {_BANDS[change.band]}"),
                tone="loss" if change.band == "failure" else "gain"))
        elif isinstance(change, RegardChanged) and change.delta:
            facts.append(OutcomeFact(kind="regard", text=f"{change.name} trusts you {'more' if change.delta > 0 else 'less'}",
                                     tone="gain" if change.delta > 0 else "loss"))
        elif isinstance(change, CombatAdvanced) and change.combat_state.get("active") is True:
            # A fight going on: each foe's health as the turn leaves it, once (the playtest: the card told only the
            # hero's wounds, so eight rounds against the Rootbound Knight read as eight misses).
            facts = [fact for fact in facts if not (fact.kind == "fight" and fact.text.endswith(" health"))]
            for row in _d(change.combat_state.get("participants")).values():
                row = _d(row)
                if _s(row.get("side")) == "enemy" and int(row.get("max_hp") or 0) > 0:
                    facts.append(OutcomeFact(kind="fight", text=f"{_s(row.get('name')) or 'The foe'}: "
                                             f"{max(0, int(row.get('hp') or 0))} of {int(row['max_hp'])} health"))
        elif isinstance(change, CombatAdvanced) and change.combat_state.get("active") is not True:
            ended = _s(change.combat_state.get("ended_reason"))
            said = {"enemy_side_defeated": ("Fight won", "gain"), "party_side_defeated": ("Fight lost", "loss"),
                    "party_fled": ("Broke away", "neutral"), "enemy_fled": ("It got away", "neutral"),
                    "evaded": ("Slipped past", "gain"), "talked_down": ("Talked down", "gain")}.get(ended)
            if said:
                facts.append(OutcomeFact(kind="fight", text=said[0], tone=said[1]))  # type: ignore[arg-type]
    return tuple(facts)


__all__ = ["OutcomeFact", "Suggestion", "outcome_facts"]
