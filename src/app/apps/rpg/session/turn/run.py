"""Steps 1-6 of a turn on the pipeline, and the stage that hands it to the commit (RQ-1.4, roadmap §4.1).

``apply_planned_turn_stage`` runs first in the session's turn pipeline. For a reading the pipeline plans, it loads
the turn-start campaign, has the mechanic's rule resolve the plan to changes (``resolution.py``), applies them
with the reducer, lets the world tick for the time the turn took, records the turn in the journal, and leaves the
result for the commit and narration stages. A ``world_tick`` turn (the player's return) runs here too. Everything
else takes the older path, until its mechanic moves (RQ-2).
"""
from __future__ import annotations

from typing import Any

from app.config.env import env_list
from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_str as _s
from app.apps.rpg.foundation.state.changes import JournalWritten, StateChange, TimeAdvanced, WorldTicked
from app.apps.rpg.foundation.state.reducer import reduce
from app.apps.rpg.rules.intent.grammar import IntentCandidate, SceneView, parse_command
from app.apps.rpg.session.command_reading import read_command, reading_record
from app.apps.rpg.session.turn.planning import PlannedAction, plan_action
from app.apps.rpg.session.turn.request import TurnRequest
from app.apps.rpg.session.turn.resolution import MINUTES_PER_TICK, Resolution, resolve_turn
from app.apps.rpg.session.turn.resolvers import outcome_lines
from app.apps.rpg.session.turn.world_tick import world_tick

# The mechanics to keep on the older path, for development and the operator (e.g. "trade,rest"); each mechanic is
# on once its scenarios pass on the pipeline, and the setting goes when the older path does.
OFF_SETTING = "OMNIX_RPG_TURN_PIPELINE_OFF"
_ACTION_TYPE = {"look": "observe", "wait": "ambient_wait", "clarify": "clarification", "travel": "travel",
                "trade": "trade", "use_item": "use_item", "drop": "drop_item", "take": "pick_up_item", "rest": "rest",
                "quest": "quest_accept", "practice": "skill_practice", "status": "status_report", "party": "party",
                "order": "companion_order", "talk": "npc_interpretive_dialogue", "fight": "attack",
                "equip": "equip_item", "unequip": "unequip_item"}
_FAMILY = {"look": "observation", "wait": "ambient", "clarify": "clarification", "travel": "travel",
           "trade": "commerce", "use_item": "inventory", "drop": "inventory", "take": "inventory", "rest": "survival",
           "quest": "quest", "practice": "progression", "status": "status", "party": "party", "order": "party",
           "talk": "social", "fight": "combat", "equip": "inventory", "unequip": "inventory"}
SOURCE = "rpg_turn_pipeline_v1"


def pipeline_enabled(mechanic: str) -> bool:
    return mechanic in _ACTION_TYPE and mechanic not in set(env_list(OFF_SETTING))


def _journal(document: dict[str, Any], *, request: TurnRequest, turn_index: int, summary: str) -> JournalWritten:
    from app.apps.rpg.narration.campaign_journal_runtime import advance_campaign_journal_for_turn

    state = _d(document.get("state"))
    runtime_state = advance_campaign_journal_for_turn(
        runtime_state=_d(document.get("runtime_state")),
        turn_index=turn_index,
        player_input=request.text,
        turn_contract={"player_input": request.text, "turn_index": turn_index, "summary": summary},
        turn_result={"player_action": request.text},
        calendar_snapshot=_d(_d(state.get("world")).get("environment") or state.get("environment_snapshot")),
        player_context={
            "personality_profile": _d(state.get("player_personality_profile")),
            "metadata": _d(state.get("metadata")),
            "character_identity": _d(state.get("character_identity")),
        },
    )
    return JournalWritten(calendar=_d(runtime_state.get("campaign_calendar")),
                          journal=_d(runtime_state.get("player_journal")))


def _reported(changes: list[StateChange]) -> list[dict[str, Any]]:
    """As the outcome reports them: a world tick's summary, not the sections it replaced (the patch has those)."""
    return [(change.reported() if isinstance(change, WorldTicked) else change).model_dump(mode="json")
            for change in changes]


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
    simulation = _d(document.get("simulation_state"))
    tick = int(simulation.get("tick") or 0)
    turn_index = int(_d(document.get("state")).get("turn_count") or 0)
    turn_id = f"turn:{tick}"
    tick_changes: list[StateChange] = []
    causal: dict[str, Any] = {}
    if resolution.minutes:  # the world moves on only when time passed
        tick_changes, causal = world_tick(document, needs=resolution.needs, minutes=resolution.minutes,
                                          turn_key=turn_id, turn=turn_index)
        document, _ = reduce(document, tick_changes)
    lines = resolution.lines
    applied = [*resolution.changes, *tick_changes]
    if planned.mechanic != "clarify" and not resolution.refused:  # a question back or a refusal is no journal entry
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
        },
        **({"map_events": [resolution.map_event]} if resolution.map_event else {}),
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
            "visible_response": {"narration": "", "npc": dict(result["npc"])},
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
    """A ``world_tick`` turn (RQ-2.7): the world moves on for the time the player was away, and the recap says how.

    The hero did nothing, so no turn is counted and their needs do not rise; the campaign's clock and its causal
    pressures advance. The recap is the game's own line, with no model call.
    """
    seconds = int(request.action.get("elapsed_seconds") or request.elapsed_minutes * 60)
    ticks = min(MAX_WORLD_TICKS, max(0, seconds // SECONDS_PER_WORLD_TICK))
    changes: list[StateChange] = [TimeAdvanced(ticks=ticks, minutes=ticks * MINUTES_PER_TICK)] if ticks else []
    document, _ = reduce(session, changes)
    simulation = _d(document.get("simulation_state"))
    tick = int(simulation.get("tick") or 0)
    turn_id = f"turn:{tick}:world"
    causal: dict[str, Any] = {}
    if ticks:
        tick_changes, causal = world_tick(document, needs=None, minutes=ticks * MINUTES_PER_TICK, turn_key=turn_id,
                                          turn=tick)
        document, _ = reduce(document, tick_changes)
        changes.extend(tick_changes)
    place = outcome_lines(PlannedAction(mechanic="look"), document)[0].removeprefix("You look around ").rstrip(".")
    recap = (f"You return to {place}. The world went on while you were away." if ticks
             else f"You return to {place}; little time has passed.")
    resolved = {"ok": True, "outcome": "success", "action_type": "world_tick", "semantic_action_type": "world_tick",
                "semantic_family": "world", "summary": recap, "outcome_lines": [recap], "turn_id": turn_id,
                "tick": tick, "source": SOURCE, "response_mode": "world_tick"}
    result: dict[str, Any] = {
        "ok": True, "session": document, "turn_id": turn_id, "tick": tick, "player_input": request.text,
        "action_type": "world_tick", "semantic_family": "world", "llm_called": False, "llm_purpose": "turn_pipeline",
        "source": SOURCE, "response_mode": "world_tick", "resolved_result": resolved, "result": dict(resolved),
        "causal_world_runtime": causal, "world_tick": {"elapsed_seconds": seconds, "ticks": ticks},
        "turn_pipeline": {"kind": "world_tick", "mechanic": "world_tick", "changes": _reported(changes)},
    }
    from app.apps.rpg.narration.narrative_engine import BeatKind, BeatPurpose
    from app.apps.rpg.session.narrative_engine_bridge import publish_fixed_narration

    return publish_fixed_narration(result, session_id=request.session_id, text=recap, kind=BeatKind.NARRATION,
                                   purpose=BeatPurpose.CONTINUATION, source="rpg_turn_pipeline_world_tick_v1")


def _load(ctx: Any) -> dict[str, Any]:
    """Step 1: the turn-start campaign, normalized as every older turn path does first: its simulation filled in
    from the play screen's sheet, and the hero's progression (level, skills) given its defaults."""
    from app.apps.rpg.rules.player.player_progression_state import ensure_player_progression_state
    from app.apps.rpg.session.interactive_first_call_runtime import _select_session
    from app.apps.rpg.session.public_state_bridge import hydrate_simulation_player

    session = _select_session(ctx.session_id, session_override=ctx.session_override)
    if not session:
        return session
    session = hydrate_simulation_player(session)
    simulation = _d(session.get("simulation_state"))
    simulation["player_state"] = ensure_player_progression_state(_d(simulation.get("player_state")))
    session["simulation_state"] = simulation
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
    simulation = _d(session.get("simulation_state"))
    if mechanic == "use_item" and _d(simulation.get("combat_state")).get("active") is True:
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


def _map_travel_turn(ctx: Any, session: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
    """A journey chosen on the world map: the travel rule's, its lines the game's own; a road that cannot be taken
    refuses the request, with no turn taken."""
    from app.apps.rpg.session.turn.resolution import Resolution
    from app.apps.rpg.session.turn.travel import resolve_travel

    planned = PlannedAction(mechanic="travel", target_id=_s(action.get("location_id")), reason="map_travel")
    travel = resolve_travel(planned, session)
    if travel.refused:
        return {"ok": False, "error": "map_travel_refused", "status_code": 409, "detail": " ".join(travel.lines)}
    resolution = Resolution(travel.changes, travel.lines, minutes=travel.minutes, needs="travel", told=False,
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
    revision = int(_d(session.get("runtime_state")).get("state_revision") or 0)
    if action.get("expected_campaign_revision") is not None and int(action["expected_campaign_revision"]) != revision:
        return {"ok": False, "error": "stale_tactical_campaign_revision", "status_code": 409,
                "message": f"expected={action['expected_campaign_revision']}:current={revision}"}
    simulation = _d(session.get("simulation_state"))
    state, manifest = _d(session.get("state")), _d(session.get("manifest"))
    count = int(state.get("turn_count") or manifest.get("turn_count") or 0) + 1
    if action.get("type") == "loadout":
        return _loadout_turn(ctx, session, action, count)
    if action.get("type") == "map_travel":
        return _map_travel_turn(ctx, session, action)
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


def apply_planned_turn_stage(ctx: Any) -> Any:
    """The session pipeline's first stage: run the turn here when its mechanic has moved to the pipeline."""
    if not ctx.resolved and _d(ctx.action).get("turn_kind") == "world_tick":
        session = _load(ctx)
        if session:
            request = TurnRequest(kind="world_tick", session_id=ctx.session_id, text=_s(ctx.player_input),
                                  action=_d(ctx.action))
            ctx.result = run_world_tick_turn(session, request=request)
            ctx.result.setdefault("trace_id", ctx.trace_id)
            ctx.resolved = True
        return ctx
    if not ctx.resolved and _d(ctx.action).get("turn_kind") == "structured_action":
        ctx.result = _structured_turn(ctx, _d(ctx.action))
        ctx.result.setdefault("trace_id", ctx.trace_id)
        ctx.resolved = True
        return ctx
    if ctx.resolved or ctx.action or not _s(ctx.player_input).strip():
        return ctx
    # Read against no scene first: only a command that could be one the pipeline runs loads the campaign here.
    unseen = parse_command(_s(ctx.player_input), SceneView(()))
    glance = plan_action(unseen)
    # A journey's destination and a carried or fallen thing are the scene's, which a reading against none cannot name.
    by_family = {"move": "travel", "use_item": "use_item", "drop": "drop", "take": "take", "quest": "quest",
                 "practice": "practice", "party": "party", "talk": "talk", "ask": "talk", "attack": "fight",
                 "flee": "fight", "equip": "equip", "unequip": "unequip"}
    possible = by_family.get(unseen.family) or (glance.mechanic if glance is not None else "")
    if not possible and "," in " ".join(_s(ctx.player_input).split()[:3]):
        possible = "order"  # someone named first ("Liora, keep watch") may be a companion given an order
    if not possible or not pipeline_enabled(possible):
        return ctx
    session = _load(ctx)
    if not session:
        return ctx
    simulation = _d(session.get("simulation_state"))
    reading = read_command(simulation, ctx.player_input, _d(session.get("runtime_state")))
    planned = plan_action(reading, fighting=_d(simulation.get("combat_state")).get("active") is True)
    if planned is None or not pipeline_enabled(planned.mechanic):
        return ctx
    resolution = resolve_turn(planned, session, _s(ctx.player_input))
    if resolution is None:
        return ctx  # the mechanic's rule has nothing to say for this campaign: the older path answers
    request = TurnRequest(kind="player_text", session_id=ctx.session_id, text=_s(ctx.player_input))
    ctx.result = run_planned_turn(session, request=request, planned=planned, reading=reading, resolution=resolution)
    ctx.result.setdefault("trace_id", ctx.trace_id)
    ctx.resolved = True
    return ctx


__all__ = ["OFF_SETTING", "apply_planned_turn_stage", "pipeline_enabled", "run_planned_turn", "run_world_tick_turn"]
