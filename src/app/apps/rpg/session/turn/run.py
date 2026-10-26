"""Steps 1-6 of a turn on the pipeline, and the stage that hands it to the commit (RQ-1.4, roadmap §4.1).

``apply_planned_turn_stage`` runs first in the session's turn pipeline. It loads the turn-start campaign, plans
the player's words (the grammar, else one intent call, ``intent.py``), has the mechanic's rule resolve the plan to
changes (``resolution.py``), applies them with the reducer, lets the world tick for the time the turn took, records
the turn in the journal, and leaves the result for the commit and narration stages. A ``world_tick`` turn (the
player's return) and a ``structured_action`` (the play screen's buttons and grid) run here too (RQ-1.4, RQ-3.2).
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import logging
from typing import Any, Iterator, Mapping

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_str as _s
from app.apps.rpg.foundation.state.changes import JournalWritten, PressuresMoved, StateChange, TimeAdvanced, WorldTicked
from app.apps.rpg.foundation.state.reducer import reduce
from app.apps.rpg.rules.intent.grammar import IntentCandidate, SceneView
from app.apps.rpg.rules.ability_use import known as known_abilities
from app.apps.rpg.session.command_reading import read_command, reading_record
from app.apps.rpg.session.turn.planning import PlannedAction, plan_action
from app.apps.rpg.session.turn.request import TurnRequest
from app.apps.rpg.session.turn.resolution import MINUTES_PER_TICK, Resolution, free_action, resolve_turn
from app.apps.rpg.session.turn.resolvers import outcome_lines
from app.apps.rpg.session.turn.world_tick import world_tick
from app.apps.rpg.foundation.state import access as _sections

# Each mechanic as the turn's outcome names it: its action type and family.
_ACTION_TYPE = {"look": "observe", "wait": "ambient_wait", "clarify": "clarification", "travel": "travel",
                "trade": "trade", "use_item": "use_item", "drop": "drop_item", "give": "give_item", "take": "pick_up_item",
                "rest": "rest",
                "quest": "quest_accept", "practice": "skill_practice", "status": "status_report", "party": "party",
                "order": "companion_order", "talk": "npc_interpretive_dialogue", "fight": "attack",
                "equip": "equip_item", "unequip": "unequip_item", "ability": "use_ability", "hotbar": "hotbar_slot",
                "check": "skill_check",
                "grow": "level_choice", "rewind": "rewind", "act": "free_action"}
_FAMILY = {"look": "observation", "wait": "ambient", "clarify": "clarification", "travel": "travel",
           "trade": "commerce", "use_item": "inventory", "drop": "inventory", "give": "inventory", "take": "inventory",
           "rest": "survival",
           "quest": "quest", "practice": "progression", "status": "status", "party": "party", "order": "party",
           "talk": "social", "fight": "combat", "equip": "inventory", "unequip": "inventory", "ability": "combat",
           "hotbar": "loadout",
           "check": "check", "grow": "progression", "rewind": "meta", "act": "action"}
SOURCE = "rpg_turn_pipeline_v1"
logger = logging.getLogger(__name__)
# Turns in which the hero does nothing in the world: a question back, a rewind, a hotbar slot, a level's choice. What
# a turn leads to (quests, pressures) and the foes on the grid do not follow them.
_NOTHING_DONE_IN_THE_WORLD = frozenset({"clarify", "rewind", "hotbar", "grow"})


def _journal(document: dict[str, Any], *, request: TurnRequest, turn_index: int, summary: str) -> JournalWritten:
    from app.apps.rpg.narration.campaign_journal_runtime import advance_campaign_journal_for_turn

    state = _d(document.get("state"))
    runtime_state = advance_campaign_journal_for_turn(
        runtime_state=_d(_sections.runtime_state_of(document)),
        turn_index=turn_index,
        player_input=request.text,
        # The game's own lines are the day's record (the journal reads a resolved result's summary).
        turn_contract={"player_input": request.text, "turn_index": turn_index, "resolved_result": {"summary": summary}},
        turn_result={"player_action": request.text},
        calendar_snapshot=_d(_d(state.get("world")).get("environment") or state.get("environment_snapshot")),
        player_context={
            "personality_profile": _d(state.get("player_personality_profile")),
            "metadata": _d(state.get("metadata")),
            "character_identity": _d(state.get("character_identity")),
        },
    )
    return JournalWritten(calendar=_d(_sections.campaign_calendar_of(runtime_state)),
                          journal=_d(_sections.player_journal_of(runtime_state)))


def _reported(changes: list[StateChange]) -> list[dict[str, Any]]:
    """As the outcome reports them: a world tick's summary, not the sections it replaced (the patch has those)."""
    return [(change.reported() if isinstance(change, (WorldTicked, PressuresMoved)) else change).model_dump(mode="json")
            for change in changes]


def _offered(document: dict[str, Any], planned: PlannedAction | None) -> dict[str, Any]:
    """What the play screen offers after the turn (RQ-7.3): suggestions from the scene, and the answers to the
    game's question when it asked one."""
    from app.apps.rpg.narration.presentation.outcome_facts import Suggestion
    from app.apps.rpg.session.turn.suggestions import choices, suggestions

    asked = planned is not None and planned.mechanic == "clarify"
    answers = ([Suggestion(label=command, command=command).model_dump() for command in planned.options]
               if asked and planned.options else
               [row.model_dump() for row in choices(document, planned.reason)] if asked else [])
    return {"suggestions": [row.model_dump() for row in suggestions(document)], "choices": answers}


def turn_consequences(document: dict[str, Any],
                      applied: list[StateChange]) -> tuple[dict[str, Any], list[StateChange], list[str]]:
    """What the turn led to: the quests of steps it moved on (rules/quest/progress.py), the pressures its deeds pushed
    on, and the side quests a high pressure raises (rules/pressures.py)."""
    from app.apps.rpg.rules.pressures import lever_pulls, pressure_offers
    from app.apps.rpg.world.causal_runtime import pull_levers
    from app.apps.rpg.rules.quest.arrival import quest_rewards
    from app.apps.rpg.rules.quest.progress import quest_progress

    changes: list[StateChange] = []
    lines: list[str] = []
    for step in (lambda simulation: quest_progress(simulation, applied, lambda quest: quest_rewards(simulation, quest)),
                 lambda simulation: lever_pulls(simulation, [*applied, *changes],
                                                pull=lambda runtime, pulls: pull_levers(runtime, pulls, cause="hero")),
                 pressure_offers):
        made, said = step(_d(_sections.simulation_state_of(document)))
        if made:
            document, _ = reduce(document, made)
        changes += made
        lines += said
    return document, changes, lines


def run_planned_turn(
    session: dict[str, Any],
    *,
    request: TurnRequest,
    planned: PlannedAction,
    reading: IntentCandidate,
    resolution: Resolution,
) -> dict[str, Any]:
    """Apply one resolved turn to the turn-start campaign and let the world tick; the result for the commit."""
    document, _ = reduce(session, resolution.changes)
    simulation = _d(_sections.simulation_state_of(document))
    tick = int(simulation.get("tick") or 0)
    turn_index = int(_d(document.get("state")).get("turn_count") or 0)
    turn_id = f"turn:{tick}"
    tick_changes: list[StateChange] = []
    causal: dict[str, Any] = {}
    seen: list[str] = []
    if resolution.minutes:  # the world moves on only when time passed
        tick_changes, causal, seen = world_tick(document, needs=resolution.needs, minutes=resolution.minutes,
                                                turn_key=turn_id)
        document, _ = reduce(document, tick_changes)
    applied = [*resolution.changes, *tick_changes]
    quested: list[StateChange] = []
    quest_lines: list[str] = []
    if planned.mechanic not in _NOTHING_DONE_IN_THE_WORLD and not resolution.refused:  # step 5: what it led to
        document, quested, quest_lines = turn_consequences(document, applied)
    applied += quested
    maps_made: list[dict[str, Any]] = []
    if planned.mechanic not in _NOTHING_DONE_IN_THE_WORLD and not resolution.refused:  # the grid the hero stands on
        from app.apps.rpg.foundation.state.changes import LocationChanged
        from app.apps.rpg.session.turn.local_map import on_the_local_map

        grounded, maps_made = on_the_local_map(
            request.session_id, document, moved=any(isinstance(change, LocationChanged) for change in applied),
            pending_map_event=resolution.map_event, foes_act=planned.reason != "grid_move")
        if grounded:
            document, _ = reduce(document, grounded)
            applied += grounded
    from app.apps.rpg.world.map_world_integration import projected_map_state

    projected = projected_map_state(document)  # the world map the play screen shows, from where the hero now is
    if projected is not None:
        document, _ = reduce(document, [projected])
        applied.append(projected)
    lines = [*resolution.lines, *seen, *quest_lines]  # what the hero did, the comings and goings, what it led to
    # A question back, a refusal or a hotbar slot (the play screen's, not the hero's doing) is no journal entry.
    if planned.mechanic not in {"clarify", "hotbar"} and not resolution.refused:
        journal = _journal(document, request=request, turn_index=turn_index, summary=" ".join(lines))
        document, _ = reduce(document, [journal])
        applied.append(journal)

    outcome = "clarification_required" if planned.mechanic == "clarify" else "refused" if resolution.refused else "success"
    resolved = {
        "ok": True,
        "outcome": outcome,
        "action_type": _ACTION_TYPE[planned.mechanic],
        "semantic_action_type": _ACTION_TYPE[planned.mechanic],
        "semantic_family": _FAMILY[planned.mechanic],
        "target_id": planned.target_id,
        "summary": " ".join(lines),
        "outcome_lines": lines,
        "turn_id": turn_id,
        "tick": tick,
        "source": SOURCE,
    }
    result: dict[str, Any] = {
        "ok": True,
        "session": document,
        "turn_id": turn_id,
        "tick": tick,
        "turn_index": turn_index,
        "player_input": request.text,
        "action_type": resolved["action_type"],
        "semantic_family": resolved["semantic_family"],
        "llm_called": False,
        "llm_purpose": "turn_pipeline",
        "source": SOURCE,
        "resolved_result": resolved,
        "result": dict(resolved),
        "causal_world_runtime": causal,
        "turn_pipeline": {
            "kind": request.kind,
            "mechanic": planned.mechanic,
            "planned": planned.model_dump(mode="json"),
            "intent": reading_record(reading),
            "changes": _reported(applied),
            **({"action_result": resolution.action_result} if resolution.action_result else {}),
            "presentation": _offered(document, planned),
        },
        **({"map_events": [resolution.map_event]} if resolution.map_event else {}),
        **({"map_instances": maps_made} if maps_made else {}),
    }
    if resolution.speech:
        # The person's line is written: the narrative engine adopts it as the turn's spoken answer.
        speech = resolution.speech
        resolved["response_mode"] = result["response_mode"] = "dialogue"
        resolved["target_id"] = speech["speaker_id"]
        result["npc"] = {"speaker": speech["speaker"], "speaker_id": speech["speaker_id"], "line": speech["line"]}
        result["first_call_semantic_advisory"] = {
            "source": "compact_grounded_dialogue_v1",
            "target_id": speech["speaker_id"],
            # What the exchange led to (a quest's step done, who came and went) is said after the line.
            "visible_response": {"narration": "", "npc": dict(result["npc"]), "aftermath": " ".join([*seen, *quest_lines])},
            "first_call_grounding_diagnostics": {"provider_called": True, "source": "rpg_turn_pipeline_dialogue_v1"},
        }
    if not resolution.told:
        # The game asks, or says why not; no model writes it (the narrative engine adopts it as the turn's prose).
        from app.apps.rpg.narration.narrative_engine import BeatKind, BeatPurpose
        from app.apps.rpg.session.narrative_engine_bridge import publish_fixed_narration

        asks = planned.mechanic == "clarify"
        if asks:
            result["clarification"] = planned.question
            result["response_mode"] = resolved["response_mode"] = "clarification"
        result = publish_fixed_narration(
            result, session_id=request.session_id, text=" ".join(lines),
            kind=BeatKind.CLARIFICATION if asks else BeatKind.RESULT,
            purpose=BeatPurpose.CLARIFICATION if asks else BeatPurpose.CONSEQUENCE,
            source=f"rpg_turn_pipeline_{planned.mechanic}_v1")
    return result


# Time away, in campaign ticks: one per five seconds away, at most twelve (the idle catch-up's bounds).
SECONDS_PER_WORLD_TICK = 5
MAX_WORLD_TICKS = 12


def run_world_tick_turn(session: dict[str, Any], *, request: TurnRequest) -> dict[str, Any]:
    """A ``world_tick`` turn (RQ-2.7): the world moves on for the time the player was away, or for the ticks asked
    for (``/spatial-ticks``), and the recap says how.

    The hero did nothing, so no turn is counted and their needs do not rise; the campaign's clock, its people's days
    and its causal pressures advance. The recap is the game's own line, with no model call.
    """
    seconds = int(request.action.get("elapsed_seconds") or request.elapsed_minutes * 60)
    asked = int(request.action.get("ticks") or 0)
    ticks = min(MAX_WORLD_TICKS, max(0, asked or seconds // SECONDS_PER_WORLD_TICK))
    changes: list[StateChange] = [TimeAdvanced(ticks=ticks, minutes=ticks * MINUTES_PER_TICK)] if ticks else []
    document, _ = reduce(session, changes)
    simulation = _d(_sections.simulation_state_of(document))
    tick = int(simulation.get("tick") or 0)
    turn_id = f"turn:{tick}:world"
    causal: dict[str, Any] = {}
    seen: list[str] = []
    if ticks:
        tick_changes, causal, seen = world_tick(document, needs=None, minutes=ticks * MINUTES_PER_TICK,
                                                turn_key=turn_id)
        document, _ = reduce(document, tick_changes)
        changes.extend(tick_changes)
        document, quested, quest_lines = turn_consequences(document, tick_changes)  # a deadline may run out away
        changes.extend(quested)
        seen = [*seen, *quest_lines]
    place = outcome_lines(PlannedAction(mechanic="look"), document)[0].removeprefix("You look around ").rstrip(".")
    if asked:
        opening = f"Time passes in {place}."
    else:
        opening = (f"You return to {place}. The world went on while you were away." if ticks
                   else f"You return to {place}; little time has passed.")
    recap = " ".join([opening, *seen])
    resolved = {"ok": True, "outcome": "success", "action_type": "world_tick", "semantic_action_type": "world_tick",
                "semantic_family": "world", "summary": recap, "outcome_lines": [recap], "turn_id": turn_id,
                "tick": tick, "source": SOURCE, "response_mode": "world_tick"}
    result: dict[str, Any] = {
        "ok": True, "session": document, "turn_id": turn_id, "tick": tick, "player_input": request.text,
        "action_type": "world_tick", "semantic_family": "world", "llm_called": False, "llm_purpose": "turn_pipeline",
        "source": SOURCE, "response_mode": "world_tick", "resolved_result": resolved, "result": dict(resolved),
        "causal_world_runtime": causal, "world_tick": {"elapsed_seconds": seconds, "ticks": ticks},
        "turn_pipeline": {"kind": "world_tick", "mechanic": "world_tick", "changes": _reported(changes),
                          "presentation": _offered(document, None)},
    }
    from app.apps.rpg.narration.narrative_engine import BeatKind, BeatPurpose
    from app.apps.rpg.session.narrative_engine_bridge import publish_fixed_narration

    return publish_fixed_narration(result, session_id=request.session_id, text=recap, kind=BeatKind.NARRATION,
                                   purpose=BeatPurpose.CONTINUATION, source="rpg_turn_pipeline_world_tick_v1")


_TURN_START: ContextVar[dict[str, Any] | None] = ContextVar("RPG_TURN_START", default=None)


@contextmanager
def keeping_turn_start() -> Iterator[dict[str, Any]]:
    """Hand the caller the campaign the turn starts from, as the pipeline loads it (the turn route reports the
    TurnOutcome against it, instead of loading the campaign again: RQ-6.4)."""
    holder: dict[str, Any] = {}
    token = _TURN_START.set(holder)
    try:
        yield holder
    finally:
        _TURN_START.reset(token)


def _load(ctx: Any) -> dict[str, Any]:
    """Step 1: the turn-start campaign (a copy of the caller's, when it hands one in), as stored: the hero's simulation
    record was filled from the sheet when the campaign was created (``upgrades/hero_record.py``)."""
    from copy import deepcopy

    from app.apps.rpg.session.session_runtime_store import load_runtime_session

    override = _d(ctx.session_override)
    session = deepcopy(override) if override else _d(load_runtime_session(ctx.session_id))
    if not session:
        return session
    holder = _TURN_START.get()
    if holder is not None and "document" not in holder:
        holder["document"] = session  # the turn reduces copies of it: it stays as the turn found it
    return session


_LOADOUT = {"use": "use_item", "equip": "equip", "drop": "drop", "unequip": "unequip"}


def _loadout_turn(ctx: Any, session: dict[str, Any], action: dict[str, Any], count: int) -> dict[str, Any]:
    """A pack action from the play screen's loadout (use, equip, take off, drop) as a turn: the item rule's, its
    lines the game's own (no model call); what the rule refuses refuses the request, with no turn taken."""
    from app.apps.rpg.foundation.state.changes import TurnCounted
    from app.apps.rpg.rules.interactions.items import drop_item, equip_item, unequip_item, use_item
    from app.apps.rpg.session.turn.resolution import Resolution

    mechanic = _LOADOUT[_s(action.get("action"))]
    rule = {"use_item": use_item, "equip": equip_item, "drop": drop_item, "unequip": unequip_item}[mechanic]
    simulation = _d(_sections.simulation_state_of(session))
    if mechanic == "use_item" and _d(_sections.combat_state_of(simulation)).get("active") is True:
        return {"ok": False, "error": "loadout_in_a_fight", "status_code": 409,
                "detail": "In a fight, say what you use: the others act after it."}
    outcome = rule(simulation, "", _s(action.get("item_name")))
    if outcome.refused:
        return {"ok": False, "error": "loadout_refused", "status_code": 409, "detail": " ".join(outcome.lines)}
    ticks = -(-outcome.minutes // MINUTES_PER_TICK)
    resolution = Resolution(
        [TurnCounted(turn_count=count), *([TimeAdvanced(ticks=ticks, minutes=outcome.minutes)] if outcome.minutes else []),
         *outcome.changes],
        outcome.lines, minutes=outcome.minutes, needs="standard_turn" if outcome.minutes else None, told=False,
        action_result={"kind": "loadout", "action": _s(action.get("action")), "item_name": _s(action.get("item_name")),
                       "detail": " ".join(outcome.lines)})
    planned = PlannedAction(mechanic=mechanic, ticks=0, reason="loadout")
    reading = IntentCandidate(family=mechanic, confidence=1.0, reason="loadout")  # type: ignore[arg-type]
    request = TurnRequest(kind="structured_action", session_id=ctx.session_id, text=_s(ctx.player_input), action=action)
    return run_planned_turn(session, request=request, planned=planned, reading=reading, resolution=resolution)


def _rewind_turn(ctx: Any, session: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
    """An undo, or a return to a save point (rewind.md): the earlier revision's game, put back as a new revision;
    what cannot be rewound refuses the request, with no turn taken."""
    from app.apps.rpg.foundation.state.changes import RevisionRestored
    from app.apps.rpg.rules.combat.stakes import is_hardcore
    from app.apps.rpg.session.turn.resolution import Resolution
    from app.apps.rpg.session.turn.rewind import undo_target
    from app.persistence.unit_of_work import unit_of_work
    from app.runtime.tenant_context import current_tenant

    def refused(detail: str) -> dict[str, Any]:
        return {"ok": False, "error": "rewind_refused", "status_code": 409, "detail": detail}

    if is_hardcore(_d(_sections.simulation_state_of(session))):
        return refused("There is no going back in a hardcore campaign.")
    revision = int(_d(_sections.runtime_state_of(session)).get("state_revision") or 0)
    name = _s(action.get("save_point"))
    context = current_tenant()
    with unit_of_work() as work:
        if name:
            target = next((point["revision"] for point in work.rpg.save_points(context, ctx.session_id)
                           if point["name"] == name), None)
        else:
            target = undo_target(work.rpg.turn_history(context, ctx.session_id), revision)
        earlier = work.rpg.document_at_revision(context, ctx.session_id, target) if target is not None else None
        if earlier is not None:
            from app.apps.rpg.session.campaign_state import upcast_if_outdated

            try:
                earlier = upcast_if_outdated(earlier)  # an earlier version's game, in the shape this one plays
            except ValueError:  # it does not upgrade (a pydantic ValidationError): that moment cannot be rebuilt
                logger.warning("rpg_rewind_revision_not_upgradable session=%s revision=%s", ctx.session_id, target,
                               exc_info=True)
                earlier = None
        work.rollback()
    if target is None:
        return refused(f'There is no save point named "{name}".' if name else "There is no turn to undo.")
    if earlier is None:
        return refused("That moment can no longer be rebuilt from the campaign's history.")
    said = f'You return to the save point "{name}".' if name else "You return to the moment before your last turn."
    resolution = Resolution([RevisionRestored(source_revision=target, document=earlier)], [said], told=False,
                            action_result={"kind": "rewind", "restored_revision": target, "save_point": name,
                                           "detail": said})
    planned = PlannedAction(mechanic="rewind", ticks=0, reason="save_point" if name else "undo")
    reading = IntentCandidate(family="status", confidence=1.0, reason="rewind")
    request = TurnRequest(kind="structured_action", session_id=ctx.session_id, text=_s(ctx.player_input), action=action)
    return run_planned_turn(session, request=request, planned=planned, reading=reading, resolution=resolution)


def _ability_turn(ctx: Any, session: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
    """An ability from the play screen's hotbar or ability tree, in a fight or not: the ability rule's turn, its lines
    the game's own; what cannot be used now refuses the request, with no turn taken."""
    from dataclasses import replace

    from app.apps.rpg.session.turn.resolution import resolve_turn

    planned = PlannedAction(mechanic="ability", target_id=_s(action.get("ability")), ticks=0,
                            second_target_id=_s(action.get("target")), reason="hotbar")
    resolution = resolve_turn(planned, session, _s(ctx.player_input))
    if resolution is None or resolution.refused:
        detail = " ".join(resolution.lines) if resolution else "You do not know that ability."
        return {"ok": False, "error": "ability_refused", "status_code": 409, "detail": detail}
    resolution = replace(resolution, told=False, action_result={"kind": "ability", "ability": planned.target_id,
                                                                "detail": " ".join(resolution.lines)})
    reading = IntentCandidate(family="ability", target_id=planned.target_id, confidence=1.0, reason="hotbar")
    request = TurnRequest(kind="structured_action", session_id=ctx.session_id, text=_s(ctx.player_input), action=action)
    return run_planned_turn(session, request=request, planned=planned, reading=reading, resolution=resolution)


def _hotbar_turn(ctx: Any, session: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
    """A hotbar slot given an ability, or cleared, from the play screen: no time passes; what cannot go on the hotbar
    refuses the request, with no turn taken."""
    from app.apps.rpg.rules.ability_use import set_hotbar
    from app.apps.rpg.session.turn.resolution import Resolution

    outcome = set_hotbar(session, _s(action.get("slot")), _s(action.get("ability")))
    if outcome.refused:
        return {"ok": False, "error": "hotbar_refused", "status_code": 409, "detail": " ".join(outcome.lines)}
    resolution = Resolution(outcome.changes, outcome.lines, told=False,
                            action_result={"kind": "hotbar", "slot": _s(action.get("slot")),
                                           "ability": _s(action.get("ability")), "detail": " ".join(outcome.lines)})
    planned = PlannedAction(mechanic="hotbar", ticks=0, reason="hotbar")
    reading = IntentCandidate(family="status", confidence=1.0, reason="hotbar")
    request = TurnRequest(kind="structured_action", session_id=ctx.session_id, text=_s(ctx.player_input), action=action)
    return run_planned_turn(session, request=request, planned=planned, reading=reading, resolution=resolution)


def _learn_turn(ctx: Any, session: dict[str, Any], action: dict[str, Any], count: int) -> dict[str, Any]:
    """An ability learned from the play screen's ability tree: a level's choice (progression.md), so only when one is
    waiting; what cannot be learned now refuses the request, with no turn taken."""
    from app.apps.rpg.foundation.state.changes import TurnCounted
    from app.apps.rpg.rules.player.progression import choose
    from app.apps.rpg.session.turn.resolution import Resolution

    wanted = _s(action.get("ability"))
    tree = [_d(row) for row in _d(_d(session.get("state")).get("ability_tree")).get("abilities") or ()]
    name = next((_s(row.get("name")) for row in tree if wanted in {_s(row.get("ability_id")), _s(row.get("name"))}),
                wanted)
    grown = choose(session, f"learn {name}")
    if grown.refused:
        return {"ok": False, "error": "level_choice_refused", "status_code": 409, "detail": " ".join(grown.lines)}
    resolution = Resolution([TurnCounted(turn_count=count), *grown.changes], grown.lines, told=False,
                            action_result={"kind": "level_choice", **grown.detail, "detail": " ".join(grown.lines)})
    planned = PlannedAction(mechanic="grow", ticks=0, reason="level_choice")
    reading = IntentCandidate(family="grow", confidence=1.0, reason="learn")
    request = TurnRequest(kind="structured_action", session_id=ctx.session_id, text=_s(ctx.player_input), action=action)
    return run_planned_turn(session, request=request, planned=planned, reading=reading, resolution=resolution)


def _map_travel_turn(ctx: Any, session: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
    """A journey chosen on the world map: the travel rule's, its lines the game's own; a road that cannot be taken
    refuses the request, with no turn taken."""
    from app.apps.rpg.session.turn.resolution import Resolution, met_on_the_road
    from app.apps.rpg.session.turn.travel import resolve_travel

    planned = PlannedAction(mechanic="travel", target_id=_s(action.get("location_id")), reason="map_travel")
    travel = resolve_travel(planned, session)
    if travel.refused:
        return {"ok": False, "error": "map_travel_refused", "status_code": 409, "detail": " ".join(travel.lines)}
    changes, lines = met_on_the_road(session, travel)
    resolution = Resolution(changes, lines, minutes=travel.minutes, needs="travel", told=False,
                            action_result={"kind": "map_travel", "current_location_id": travel.destination,
                                           "detail": " ".join(travel.lines)})
    reading = IntentCandidate(family="move", target_id=planned.target_id, target_kind="place", confidence=1.0,
                              reason="map_travel")
    request = TurnRequest(kind="structured_action", session_id=ctx.session_id, text=_s(ctx.player_input), action=action)
    return run_planned_turn(session, request=request, planned=planned, reading=reading, resolution=resolution)


def _structured_turn(ctx: Any, action: dict[str, Any]) -> dict[str, Any]:
    """A grid move or attack in a fight (``session/turn/tactical.py``): the campaign revision the player saw is its
    only token; what the grid refuses refuses the request, with no turn taken."""
    from app.apps.rpg.foundation.state.changes import TurnCounted
    from app.apps.rpg.session.turn.resolution import Resolution
    from app.apps.rpg.session.turn.tactical import grid_attack, grid_move, map_for_turn
    from app.apps.rpg.world.tactical_spatial import TacticalSpatialError

    session = _load(ctx)
    if not session:
        return {"ok": False, "error": "session_not_found"}
    revision = int(_d(_sections.runtime_state_of(session)).get("state_revision") or 0)
    if action.get("expected_campaign_revision") is not None and int(action["expected_campaign_revision"]) != revision:
        return {"ok": False, "error": "stale_tactical_campaign_revision", "status_code": 409,
                "message": f"expected={action['expected_campaign_revision']}:current={revision}"}
    simulation = _d(_sections.simulation_state_of(session))
    state, manifest = _d(session.get("state")), _d(session.get("manifest"))
    count = int(state.get("turn_count") or manifest.get("turn_count") or 0) + 1
    if action.get("type") == "loadout":
        return _loadout_turn(ctx, session, action, count)
    if action.get("type") == "map_travel":
        return _map_travel_turn(ctx, session, action)
    if action.get("type") == "ability":
        return _ability_turn(ctx, session, action)
    if action.get("type") == "hotbar":
        return _hotbar_turn(ctx, session, action)
    if action.get("type") == "learn":
        return _learn_turn(ctx, session, action, count)
    if action.get("type") == "rewind":
        return _rewind_turn(ctx, session, action)
    try:
        definition, snapshot = map_for_turn(_s(action.get("map_instance_id")), campaign_id=ctx.session_id)
        if action.get("type") == "tactical_move":
            grid = grid_move(ctx.session_id, simulation, definition, snapshot,
                             destination=tuple(action.get("destination") or ()),  # type: ignore[arg-type]
                             command_id=_s(action.get("command_id")) or f"grid:{count}")
            planned = PlannedAction(mechanic="fight", ticks=0, reason="grid_move")
        else:
            grid = grid_attack(ctx.session_id, simulation, definition, snapshot, target_id=_s(action.get("target_id")),
                               attack=_s(action.get("attack")) or "melee_attack", turn_key=str(count))
            planned = PlannedAction(mechanic="fight", target_id=_s(action.get("target_id")), ticks=0,
                                    reason="grid_attack")
    except (KeyError, TacticalSpatialError) as exc:
        return {"ok": False, "error": str(exc).strip("'"), "status_code": 404 if isinstance(exc, KeyError) else 409}
    ticks = -(-grid.minutes // MINUTES_PER_TICK)
    resolution = Resolution(
        [TurnCounted(turn_count=count), *([TimeAdvanced(ticks=ticks, minutes=grid.minutes)] if grid.minutes else []),
         *grid.changes],
        grid.lines, minutes=grid.minutes, needs="standard_turn" if grid.minutes else None, told=False,
        map_event=grid.map_event, action_result=grid.action_result)
    reading = IntentCandidate(family="attack" if planned.reason == "grid_attack" else "move",
                              target_id=planned.target_id or None, confidence=1.0, reason=planned.reason)
    request = TurnRequest(kind="structured_action", session_id=ctx.session_id, text=_s(ctx.player_input), action=action)
    return run_planned_turn(session, request=request, planned=planned, reading=reading, resolution=resolution)


def _refused(ctx: Any, error: str, status_code: int, message: str) -> Any:
    ctx.result = {"ok": False, "error": error, "session_id": ctx.session_id, "status_code": status_code,
                  "message": message, "trace_id": ctx.trace_id}
    ctx.resolved = True
    return ctx


def apply_planned_turn_stage(ctx: Any) -> Any:
    """The session pipeline's first stage: the player's words, a return or a structured action, run on the
    pipeline; anything else is refused, with no turn taken."""
    if ctx.resolved:
        return ctx
    kind = _s(_d(ctx.action).get("turn_kind"))
    if kind == "structured_action":
        ctx.result = _structured_turn(ctx, _d(ctx.action))
        ctx.result.setdefault("trace_id", ctx.trace_id)
        ctx.resolved = True
        return ctx
    if ctx.action and kind != "world_tick":
        return _refused(ctx, "rpg_turn_kind_unknown", 400, f"No turn of the kind {kind or 'unnamed'!r} runs.")
    if kind != "world_tick" and not _s(ctx.player_input).strip():
        return _refused(ctx, "rpg_turn_empty", 400, "Say what your hero does.")
    session = _load(ctx)
    if not session:
        return _refused(ctx, "session_not_found", 404, "No campaign has this id.")
    if kind == "world_tick":
        request = TurnRequest(kind="world_tick", session_id=ctx.session_id, text=_s(ctx.player_input),
                              action=_d(ctx.action))
        ctx.result = run_world_tick_turn(session, request=request)
        ctx.result.setdefault("trace_id", ctx.trace_id)
        ctx.resolved = True
        return ctx
    text = _s(ctx.player_input)
    planned, reading = plan_player_text(session, text)
    resolution = resolve_turn(planned, session, text)
    if resolution is None:  # the rule found nothing to do here: the attempt is told, and changes nothing
        planned, resolution = PlannedAction(mechanic="act", ticks=1, reason=f"unresolved:{planned.mechanic}"), free_action(session)
    request = TurnRequest(kind="player_text", session_id=ctx.session_id, text=text)
    ctx.result = run_planned_turn(session, request=request, planned=planned, reading=reading, resolution=resolution)
    ctx.result.setdefault("trace_id", ctx.trace_id)
    ctx.resolved = True
    return ctx


def plan_player_text(session: Mapping[str, Any], text: str) -> tuple[PlannedAction, IntentCandidate]:
    """What a player's command will do (steps 2 and 3): the grammar's reading; else the intent call's (RQ-3.2); a
    question when two readings stay close; in a fight, the fight's moves only; else a free action."""
    from app.apps.rpg.session.command_reading import scene_view
    from app.apps.rpg.session.turn.intent import read_with_model

    simulation = _d(_sections.simulation_state_of(session))
    runtime = _d(_sections.runtime_state_of(session))
    abilities = tuple((_s(row.get("ability_id")), _s(row.get("name"))) for row in known_abilities(session))
    fighting = _d(_sections.combat_state_of(simulation)).get("active") is True
    reading = read_command(simulation, text, runtime, abilities=abilities)
    planned = plan_action(reading, fighting=fighting)
    if planned is not None:
        return planned, reading
    scene = scene_view(simulation, runtime, abilities)
    model = read_with_model(simulation, scene, text, remark=reading.reason == "remark")
    if model.unavailable:  # the storyteller is down: only what the grammar read runs (RQ-8.8), and it says what does
        from app.apps.rpg.narration.presentation.visible_response import NOTHING_COMES_OF_IT

        return PlannedAction(mechanic="clarify", ticks=0, reason="storyteller_unavailable",
                             question=NOTHING_COMES_OF_IT), reading
    if model.between:
        options = tuple(command_for(candidate, scene) for candidate in model.between)
        return PlannedAction(mechanic="clarify", ticks=0, reason="two_readings",
                             question=f"Do you mean {options[0]!r} or {options[1]!r}?", options=options), reading
    if model.reading is not None:
        planned = plan_action(model.reading, fighting=fighting, decided=True)
        if planned is not None:
            return planned, model.reading
    if fighting:  # a fight goes on: strike, break away, or use something
        return PlannedAction(mechanic="fight", ticks=0, reason="busy"), reading
    return PlannedAction(mechanic="act", ticks=1, reason="free_action"), reading


def command_for(reading: IntentCandidate, scene: SceneView) -> str:
    """A reading as the command that says it, for a question's answers."""
    names = {entity.entity_id: (entity.names[0] if entity.names else entity.entity_id) for entity in scene.entities}
    name = names.get(reading.target_id or "", "")
    if reading.family == "check":
        return f"I try to {reading.reason.removeprefix('check:').replace('_', ' ')}" + (f" {name}" if name else "")
    said = {"move": f"go to {name}", "talk": f"Talk to {name}", "attack": f"I attack {name}", "buy": f"I buy {name}",
            "sell": f"I sell my {name}", "take": f"I take the {name}", "drop": f"I drop the {name}",
            "use_item": f"I use the {name}", "equip": f"I equip the {name}", "unequip": f"I take off the {name}",
            "quest": f"I accept the quest {name}", "practice": f"I practise {name}", "party": f"I invite {name} to join me",
            "ability": f"I use {name}", "look": f"look at {name}" if name else "look around"}
    return said.get(reading.family, reading.family.replace("_", " "))


__all__ = ["apply_planned_turn_stage", "command_for", "plan_player_text", "run_planned_turn", "run_world_tick_turn",
           "turn_consequences"]
