"""Steps 3-4 for every mechanic on the pipeline: the planned action's resolution by its own rule.

Each rule answers with a ``Resolution``: its changes, the facts the narrator is told, the in-game minutes it took,
whether it was refused, and the survival profile its turn presses on the hero's needs with. ``resolve_turn``
returns ``None`` when the rule has nothing to say for this campaign (a world without an economy section has no
trade on the pipeline), and the older path answers.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.foundation.state.changes import StateChange, TimeAdvanced, TurnCounted
from app.apps.rpg.foundation.state.reducer import reduce
from app.apps.rpg.rules import ability_use
from app.apps.rpg.rules.checks import check
from app.apps.rpg.rules.player import progression
from app.apps.rpg.rules.combat.fight import fight
from app.apps.rpg.rules.interactions.items import drop_item, equip_item, pick_up, unequip_item, use_item
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
    map_event: dict[str, Any] | None = None  # a grid move: the map's change, committed in the turn's unit of work
    action_result: dict[str, Any] | None = None  # a structured action's own answer (the tactical route's fields)


def _counted(document: Mapping[str, Any]) -> TurnCounted:
    state, manifest = _d(document.get("state")), _d(document.get("manifest"))
    return TurnCounted(turn_count=int(state.get("turn_count") or manifest.get("turn_count") or 0) + 1)


def _timed(document: Mapping[str, Any], changes: list[StateChange], minutes: int) -> list[StateChange]:
    ticks = -(-minutes // MINUTES_PER_TICK)
    return [_counted(document), *([TimeAdvanced(ticks=ticks, minutes=minutes)] if minutes else []), *changes]


ABILITY_MINUTES = 5  # an ability used with no fight on: a few minutes


def _ability(planned: PlannedAction, session: Mapping[str, Any], simulation: Mapping[str, Any]) -> Resolution | None:
    """One of the hero's abilities in a fight, or aimed at a foe to open one (combat.md); out of a fight, one that is
    no blow is paid for and its heal heals, and the story tells the rest (``ability_use.out_of_fight``)."""
    ability = ability_use.find(session, planned.target_id)
    if ability is None:
        return None
    effect = ability_use.in_fight(ability)
    fighting = _d(simulation.get("combat_state")).get("active") is True
    if not fighting and effect.strikes and not planned.second_target_id:
        return Resolution([_counted(session)], [f"{_s(ability.get('name'))} needs a foe to aim at."], refused=True,
                          told=False)
    if not fighting and not effect.strikes:
        used = ability_use.out_of_fight(session, ability)
        if used.refused:
            return Resolution([_counted(session)], used.lines, refused=True, told=False)
        return Resolution(_timed(session, used.changes, ABILITY_MINUTES), used.lines, minutes=ABILITY_MINUTES,
                          needs="standard_turn")
    refusal = ability_use.not_ready(session, ability)
    if refusal:
        return Resolution([_counted(session)], [refusal], refused=True, told=False)
    spent = ability_use.spend(session, ability)
    paid, _ = reduce(dict(session), spent)
    turn = fight(_d(paid.get("simulation_state")), action="ability", target_ref=planned.second_target_id,
                 turn_key=str(_counted(session).turn_count), ability=effect, ability_name=_s(ability.get("name")))
    if turn is None:
        return None  # aimed at something that cannot be fought
    if turn.refused:
        return Resolution([_counted(session)], turn.lines, refused=True, told=False)
    return Resolution(_timed(session, [*spent, *turn.changes], turn.minutes), turn.lines, minutes=turn.minutes,
                      needs="standard_turn")


def met_on_the_road(session: Mapping[str, Any], travel: Any) -> tuple[list[StateChange], list[str]]:
    """A journey's changes and lines, and what bars the way where the hero arrives: on a dangerous road, a place where
    no one lives may hold one of the pressure's creatures (rules/pressures.py; encounters.md)."""
    from app.apps.rpg.rules.pressures import road_encounter

    arrived, _ = reduce(dict(session), travel.changes)
    arrived_at = _d(arrived.get("simulation_state"))
    turn_key = str(_counted(session).turn_count)
    foe = road_encounter(arrived_at, turn_key=turn_key)
    met = fight(arrived_at, action="confront", target_ref=foe, turn_key=turn_key) if foe else None
    if met is None:
        return travel.changes, travel.lines
    return [*travel.changes, *met.changes], [*travel.lines, *met.lines]


FREE_ACTION_MINUTES = 10


def free_action(session: Mapping[str, Any]) -> Resolution:
    """What no rule of the game decides (a song, a gesture, a look at the sky): the attempt is told and takes its few
    minutes; the game keeps nothing of it (RQ-3.2)."""
    return Resolution(_timed(session, [_counted(session)], FREE_ACTION_MINUTES),
                      ["You do so. A few minutes pass; nothing comes of it that the world keeps."],
                      minutes=FREE_ACTION_MINUTES, needs="standard_turn")


_TITLES = frozenset({"dr", "dr.", "doctor", "inspector", "captain", "sergeant", "lady", "lord", "sir", "dame",
                     "master", "mistress", "brother", "sister", "father", "mother", "elder", "magister"})


def _called(name: str) -> str:
    """What a person is called in passing: their first name, after any title ("Dr. Selene Kade": Selene)."""
    words = name.split()
    while len(words) > 1 and words[0].casefold() in _TITLES:
        words = words[1:]
    return words[0] if words else name


def resolve_turn(planned: PlannedAction, session: Mapping[str, Any], text: str) -> Resolution | None:
    mechanic = planned.mechanic
    if mechanic == "act":
        return free_action(session)
    if mechanic in {"look", "wait", "clarify"}:
        changes = resolve(planned, session)
        document, _ = reduce(dict(session), changes)  # what is seen, from where the hero then stands
        # Waiting is the game's own line, with no model call (F3: deterministic turns make none); looking is told.
        return Resolution(changes, outcome_lines(planned, document), minutes=planned.ticks * MINUTES_PER_TICK,
                          needs=None if mechanic == "clarify" else "wait", told=mechanic == "look")
    if mechanic == "travel":
        travel = resolve_travel(planned, session)
        changes, lines = (travel.changes, travel.lines) if travel.refused else met_on_the_road(session, travel)
        return Resolution(changes, lines, minutes=travel.minutes, refused=travel.refused,
                          needs=None if travel.refused else "travel", told=not travel.refused)
    if mechanic == "trade":
        trade = resolve_trade(session, text, selling=planned.reason == "sell")
        if trade is None:
            return None
        return Resolution(trade.changes, trade.lines, minutes=trade.minutes, refused=trade.refused)
    simulation = _d(session.get("simulation_state"))
    if mechanic == "fight" and planned.reason == "busy":
        return Resolution([_counted(session)], ["You are in a fight: strike, break away, or use something you carry."],
                          refused=True, told=False)
    if mechanic == "fight":
        turn = fight(simulation, action={"flee": "flee", "defend": "defend", "sneak": "sneak", "persuade": "parley",
                                         "intimidate": "parley"}.get(planned.reason, "attack"),
                     target_ref=planned.target_id or text, turn_key=str(_counted(session).turn_count),
                     parley="intimidate" if planned.reason == "intimidate" else "persuade")
        if turn is None:
            return None  # not a creature the world knows: the older path
        return Resolution(_timed(session, turn.changes, turn.minutes), turn.lines, minutes=turn.minutes,
                          refused=turn.refused, needs=None if turn.refused else "standard_turn",
                          told=not turn.refused)
    if mechanic == "ability":
        return _ability(planned, session, simulation)
    if mechanic == "grow":
        if int(_d(simulation.get("player_state")).get("level_choices_pending") or 0) <= 0:
            return None  # no level's choice is waiting: "learn to swim" is an attempt, told as one
        grown = progression.choose(session, text)
        return Resolution([_counted(session), *grown.changes], grown.lines, refused=grown.refused, told=False,
                          action_result={"kind": "level_choice", **grown.detail})
    if mechanic == "check":
        target = planned.target_id
        if planned.reason == "haggle" and not target:  # haggling, unnamed: with the one who sells here
            from app.apps.rpg.rules.economy.trade import sellers_here

            sellers = sellers_here(simulation)
            target = _s(sellers[0].get("provider_id")) if len(sellers) == 1 else ""
        tried = check(simulation, planned.reason, target, turn_key=str(_counted(session).turn_count))
        return Resolution(_timed(session, tried.changes, tried.minutes), tried.lines, minutes=tried.minutes,
                          needs="standard_turn", action_result={"kind": "check", **tried.record})
    if mechanic in {"use_item", "drop", "take", "equip", "unequip"}:
        rule = {"use_item": use_item, "drop": drop_item, "take": pick_up, "equip": equip_item,
                "unequip": unequip_item}[mechanic]
        outcome = rule(simulation, planned.target_id, text)
        if planned.reason == "in_fight" and not outcome.refused:
            # The hero's turn spent on it; then everyone whose turn comes before the hero's next acts.
            used, _ = reduce(dict(session), outcome.changes)
            turn = fight(_d(used.get("simulation_state")), action="pass", turn_key=str(_counted(session).turn_count))
            if turn is not None:
                return Resolution(_timed(session, [*outcome.changes, *turn.changes], turn.minutes),
                                  [*outcome.lines, *turn.lines], minutes=turn.minutes, needs="standard_turn")
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
            person = _d(_d(_d(simulation.get("world_model")).get("npcs")).get(planned.target_id))
            present = set(_l(_d(simulation.get("present_npc_state")).get("present_npc_ids")))
            if person and planned.target_id not in present:
                # Someone the world knows, but not here: the game says so, and where their day has them; no time
                # passes.
                from app.apps.rpg.rules.routines import clock, whereabouts

                name = _s(person.get("name")) or "They"
                place_id = getattr(whereabouts(simulation, clock(simulation)).get(planned.target_id), "location_id", "")
                place = _s(_d(_d(_d(simulation.get("world_model")).get("locations")).get(place_id)).get("name"))
                line = f"{name} is not here: at this hour, {_called(name)} is at {place}." if place else f"{name} is not here."
                return Resolution([_counted(session)], [line], refused=True, told=False)
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


__all__ = ["FREE_ACTION_MINUTES", "Resolution", "free_action", "met_on_the_road", "resolve_turn"]
