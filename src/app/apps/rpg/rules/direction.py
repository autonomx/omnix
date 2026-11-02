"""The game master's bounds (evolution roadmap EV-0, part 1). Pure.

The game master directs the campaign from a job after a turn commits; what it proposes reaches the campaign only
through the proposal record (EV-11), folded in by the rule that owns each kind. This rule keeps what bounds it:

- **meaningful events**: a fact set; a quest offered, advanced or ended; a fight started; a goal's beat advanced; a
  person arriving or leaving where the hero is; an item or coin gained beyond a purchase. The campaign keeps the turn
  of the last one (``DirectionTracked``), and a stall is the hero's turns since;
- **daily limits**: at most ``EVENTS_PER_DAY`` of its events a day, and ``COMPLICATIONS_PER_SCENE`` complication a scene;
- **protected people**: no companion, giver of an open quest, or person an open quest's step needs fails, leaves or
  dies without the hero (questions 6 and 11);
- **the player's wishes** (``note_preference``): how they want the story to go, from a closed set. The game master
  reads them when it directs; they never bind a rule.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.foundation.state import access as _sections
from app.apps.rpg.foundation.state.changes import (
    CombatStarted,
    CombatAdvanced,
    DirectionTracked,
    FactSet,
    ItemAdded,
    PreferenceNoted,
    PresenceChanged,
    PurseChanged,
    QuestOffered,
    QuestStatusChanged,
    QuestStepCompleted,
    StateChange,
)

EVENTS_PER_DAY = 3
COMPLICATIONS_PER_SCENE = 1
STALL_TURNS = 8  # turns with nothing meaningful: the game master is asked to move the story
MINUTES_PER_DAY = 24 * 60
# The wishes a player may note, and the values each takes; a person or a thread names an entry (``entry:<id>``).
WISHES: dict[str, tuple[str, ...]] = {
    "pace": ("slower", "faster"), "danger": ("less", "more"), "tone": ("lighter", "darker", "stranger"),
    "focus": ("entry",),
}


def direction(simulation: Mapping[str, Any]) -> dict[str, Any]:
    return _d(_sections.direction_of(simulation))


def _beat(change: StateChange) -> bool:
    return change.type == "beat_advanced"  # EV-4's goal beats


def meaningful(applied: Iterable[StateChange], *, before_present: Iterable[str] = ()) -> bool:
    """Whether a turn's changes hold a meaningful event (EV-0's stall)."""
    present_before = set(before_present)
    for change in applied:
        if isinstance(change, (FactSet, QuestOffered, QuestStepCompleted, CombatStarted)) or _beat(change):
            return True
        if isinstance(change, QuestStatusChanged) and change.status in {"active", "completed", "failed"}:
            return True
        if isinstance(change, CombatAdvanced) and change.combat_state.get("round") == 1 \
                and change.combat_state.get("active") is True:
            return True
        if isinstance(change, PresenceChanged) and present_before and set(change.present_npc_ids) != present_before:
            return True
        if isinstance(change, ItemAdded) and "bought" not in _s(change.fields.get("source")):
            return True
        if isinstance(change, PurseChanged) and change.delta_copper > 0 and not change.reason.startswith("sold"):
            return True
    return False


def _day(simulation: Mapping[str, Any]) -> int:
    from app.apps.rpg.rules.routines import clock

    return clock(simulation) // MINUTES_PER_DAY


def tracked(simulation: Mapping[str, Any], applied: Iterable[StateChange], turn_count: int) -> list[StateChange]:
    """The turn of the last meaningful event, kept when this turn holds one."""
    present = _d(_sections.present_npc_state_of(simulation)).get("present_npc_ids") or ()
    if not meaningful(applied, before_present=present):
        return []
    return [DirectionTracked(last_event_turn=int(turn_count))]


def stall(simulation: Mapping[str, Any], turn_count: int) -> int:
    """The hero's turns since the last meaningful event."""
    return max(0, int(turn_count) - int(direction(simulation).get("last_event_turn") or 0))


def events_today(simulation: Mapping[str, Any]) -> int:
    held = _d(direction(simulation).get("events"))
    return int(held.get(str(_day(simulation))) or 0)


def allows(simulation: Mapping[str, Any], kind: str, *, scene: str = "") -> str:
    """Why a game master's event cannot happen now ("" when it can): the day's limit, or a scene's complication."""
    if events_today(simulation) >= EVENTS_PER_DAY:
        return f"the day's limit of {EVENTS_PER_DAY} of the game master's events is reached"
    if kind == "complication" and scene:
        done = _d(direction(simulation).get("complications"))
        if int(done.get(scene) or 0) >= COMPLICATIONS_PER_SCENE:
            return "this scene already had its complication"
    return ""


def counted(simulation: Mapping[str, Any], kind: str, *, scene: str = "") -> DirectionTracked:
    """A game master's event, counted against the day's limit (and a complication against its scene's)."""
    held = direction(simulation)
    return DirectionTracked(last_event_turn=int(held.get("last_event_turn") or 0), day=_day(simulation),
                            complication_scene=scene if kind == "complication" else "")


def protected(simulation: Mapping[str, Any]) -> set[str]:
    """The people the game master may not take from the hero: companions, givers of open quests, and anyone an open
    quest's step needs."""
    from app.apps.rpg.rules.quest.progress import step_ways
    from app.apps.rpg.rules.routines import companions

    found = set(companions(simulation))
    for quest in map(_d, _l(_d(_sections.quest_state_of(simulation)).get("quests"))):
        if _s(quest.get("status")) not in {"active", "available"}:
            continue
        found.add(_s(quest.get("giver_id") or quest.get("offered_by")))
        for step in map(_d, _l(quest.get("steps"))):
            for way, _ in step_ways(step):
                found.update(_s(condition.get("talk") or condition.get("companion")) for condition in way)
    return {npc for npc in found if npc and npc != "anyone"}


@dataclass(frozen=True)
class Noted:
    changes: list[StateChange] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    refused: bool = False


def note_preference(simulation: Mapping[str, Any], kind: str, value: str) -> Noted:
    """The player's wish for the story, noted (``PreferenceNoted``): no time passes, nothing else changes."""
    from app.apps.rpg.rules.hero_knowledge import known_entries

    allowed = WISHES.get(kind)
    if allowed is None:
        return Noted(lines=["That is no wish the game master keeps."], refused=True)
    if kind == "focus":
        if value.removeprefix("entry:") not in known_entries(simulation):
            return Noted(lines=["The game master can follow only someone or something you know of."], refused=True)
    elif value not in allowed:
        return Noted(lines=[f"Say {' or '.join(allowed)} for {kind}."], refused=True)
    said = {"pace": f"The story will move {value}.", "danger": f"The road will hold {value} danger.",
            "tone": f"The story will turn {value}.", "focus": "The game master will keep that in sight."}[kind]
    return Noted([PreferenceNoted(kind=kind, value=value)], [f"Noted: {said}"])  # type: ignore[arg-type]


def wishes(simulation: Mapping[str, Any]) -> dict[str, str]:
    """The player's wishes, the latest of each kind."""
    return {_s(_d(row).get("kind")): _s(_d(row).get("value")) for row in _l(direction(simulation).get("wishes"))}


__all__ = ["COMPLICATIONS_PER_SCENE", "EVENTS_PER_DAY", "STALL_TURNS", "WISHES", "allows", "counted", "direction",
           "events_today", "meaningful", "note_preference", "protected", "stall", "tracked", "wishes"]
