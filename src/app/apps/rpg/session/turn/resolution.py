"""Steps 3-4 for every mechanic on the pipeline: the planned action's resolution by its own rule.

Each rule answers with a ``Resolution``: its changes, the facts the narrator is told, the in-game minutes it took,
whether it was refused, and the survival profile its turn presses on the hero's needs with. ``resolve_turn``
returns ``None`` when the rule has nothing to say for this campaign (a world without an economy section has no
trade on the pipeline), and the older path answers.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from app.apps.rpg.foundation.safe_values import safe_dict as _d
from app.apps.rpg.foundation.state.changes import StateChange, TimeAdvanced, TurnCounted
from app.apps.rpg.foundation.state.reducer import reduce
from app.apps.rpg.rules.interactions.items import drop_item, pick_up, use_item
from app.apps.rpg.rules.player.requests import accept_quest, join, leave, order, practise, status
from app.apps.rpg.rules.rest import rest
from app.apps.rpg.session.turn.planning import PlannedAction
from app.apps.rpg.session.turn.resolvers import outcome_lines, resolve
from app.apps.rpg.session.turn.trade import resolve_trade
from app.apps.rpg.session.turn.travel import resolve_travel

MINUTES_PER_TICK = 10  # docs/rpg/design/time.md


@dataclass(frozen=True)
class Resolution:
    changes: list[StateChange]
    lines: list[str]
    minutes: int = 0
    refused: bool = False
    needs: str | None = None  # the survival profile of the turn, or none
    told: bool = True  # told to the narrator; else the lines are the game's own, with no model call
    speech: dict[str, str] | None = None  # a person's spoken line, already written: speaker_id, speaker, line


def _counted(document: Mapping[str, Any]) -> TurnCounted:
    state, manifest = _d(document.get("state")), _d(document.get("manifest"))
    return TurnCounted(turn_count=int(state.get("turn_count") or manifest.get("turn_count") or 0) + 1)


def _timed(document: Mapping[str, Any], changes: list[StateChange], minutes: int) -> list[StateChange]:
    ticks = -(-minutes // MINUTES_PER_TICK)
    return [_counted(document), *([TimeAdvanced(ticks=ticks, minutes=minutes)] if minutes else []), *changes]


def resolve_turn(planned: PlannedAction, session: Mapping[str, Any], text: str) -> Resolution | None:
    mechanic = planned.mechanic
    if mechanic in {"look", "wait", "clarify"}:
        changes = resolve(planned, session)
        document, _ = reduce(dict(session), changes)  # what is seen, from where the hero then stands
        return Resolution(changes, outcome_lines(planned, document), minutes=planned.ticks * MINUTES_PER_TICK,
                          needs=None if mechanic == "clarify" else "wait", told=mechanic != "clarify")
    if mechanic == "travel":
        travel = resolve_travel(planned, session)
        return Resolution(travel.changes, travel.lines, minutes=travel.minutes, refused=travel.refused,
                          needs=None if travel.refused else "travel", told=not travel.refused)
    if mechanic == "trade":
        trade = resolve_trade(session, text, selling=planned.reason == "sell")
        if trade is None:
            return None
        return Resolution(trade.changes, trade.lines, minutes=trade.minutes, refused=trade.refused)
    simulation = _d(session.get("simulation_state"))
    if mechanic in {"use_item", "drop", "take"}:
        rule = {"use_item": use_item, "drop": drop_item, "take": pick_up}[mechanic]
        outcome = rule(simulation, planned.target_id, text)
        return Resolution(_timed(session, outcome.changes, outcome.minutes), outcome.lines, minutes=outcome.minutes,
                          refused=outcome.refused, told=not outcome.refused)
    if mechanic in {"quest", "practice", "status", "party", "order"}:
        if mechanic == "quest":
            asked = accept_quest(simulation, planned.target_id)
        elif mechanic == "practice":
            asked = practise(simulation, planned.target_id)
        elif mechanic == "status":
            asked = status(simulation, text)
        elif mechanic == "party":
            asked = leave(simulation, planned.target_id) if planned.reason == "party_leave" else join(simulation, planned.target_id)
        else:
            ordered = order(simulation, planned.target_id, text)
            if ordered is None:
                return None  # spoken to someone who takes no orders: it is talk, the older path's
            asked = ordered
        # Asking where one stands, or giving an order, is said by the game; the rest is told to the narrator.
        quiet = mechanic in {"status", "order"} or asked.refused
        return Resolution(_timed(session, asked.changes, asked.minutes), asked.lines, minutes=asked.minutes,
                          refused=asked.refused, needs=None if quiet else "standard_turn", told=not quiet)
    if mechanic == "talk":
        from app.apps.rpg.session.turn.dialogue import resolve_dialogue

        answer = resolve_dialogue(session, planned.target_id, text)
        if answer is None:
            return None
        speech = ({"speaker_id": answer.speaker_id, "speaker": answer.speaker_name, "line": answer.line}
                  if answer.line else None)
        return Resolution(_timed(session, answer.changes, MINUTES_PER_TICK), answer.lines, minutes=MINUTES_PER_TICK,
                          needs="standard_turn", speech=speech)
    if mechanic == "rest":
        outcome = rest(simulation, text)
        return Resolution(_timed(session, outcome.changes, outcome.minutes), outcome.lines, minutes=outcome.minutes,
                          refused=outcome.refused, needs="rest" if outcome.kind == "while" else "sleep",
                          told=not outcome.refused)
    return None


__all__ = ["Resolution", "resolve_turn"]
