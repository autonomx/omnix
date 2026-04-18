from __future__ import annotations

from fastapi import APIRouter, Request

from app.rpg.analytics import (
    build_tick_diff,
    build_timeline_row_diff,
    build_timeline_summary,
    build_world_events_view,
    get_timeline_tick,
    gm_append_debug_note,
    gm_force_faction_trend,
    gm_force_npc_goal,
    inspect_npc_reasoning,
)
from app.rpg.persistence.save_schema import CURRENT_RPG_SCHEMA_VERSION

rpg_inspection_bp = APIRouter()


async def _get_setup_payload(request: Request):
    data = await request.json() or {}
    return dict(data.get("setup_payload") or {})


def _get_simulation_state(setup_payload):
    meta = dict((setup_payload or {}).get("metadata") or {})
    return dict(meta.get("simulation_state") or {})


def _write_simulation_state(setup_payload, simulation_state):
    setup_payload = dict(setup_payload or {})
    meta = dict(setup_payload.get("metadata") or {})
    meta["simulation_state"] = dict(simulation_state or {})
    setup_payload["metadata"] = meta
    return setup_payload


@rpg_inspection_bp.post("/api/rpg/inspect/timeline")
async def inspect_timeline(request: Request):
    setup_payload = await _get_setup_payload(request)
    simulation_state = _get_simulation_state(setup_payload)
    timeline_summary = build_timeline_summary(simulation_state)
    ticks = timeline_summary.get("timeline", {}).get("ticks") or []
    if len(ticks) >= 2:
        diff = build_timeline_row_diff(ticks[-2], ticks[-1])
    else:
        diff = {}
    return {
        "ok": True,
        "schema_version": CURRENT_RPG_SCHEMA_VERSION,
        "timeline": timeline_summary,
        "latest_diff": diff,
    }


@rpg_inspection_bp.post("/api/rpg/inspect/timeline_tick")
async def inspect_timeline_tick(request: Request):
    data = await request.json() or {}
    setup_payload = dict(data.get("setup_payload") or {})
    tick = int(data.get("tick", 0) or 0)
    simulation_state = _get_simulation_state(setup_payload)
    return {
        "ok": True,
        "tick_view": get_timeline_tick(simulation_state, tick),
    }


@rpg_inspection_bp.post("/api/rpg/inspect/tick_diff")
async def inspect_tick_diff(request: Request):
    data = await request.json() or {}
    before_state = dict(data.get("before_state") or {})
    after_state = dict(data.get("after_state") or {})
    return {
        "ok": True,
        "tick_diff": build_tick_diff(before_state, after_state),
    }


@rpg_inspection_bp.post("/api/rpg/inspect/npc_reasoning")
async def inspect_npc(request: Request):
    data = await request.json() or {}
    setup_payload = dict(data.get("setup_payload") or {})
    npc_id = str(data.get("npc_id") or "")
    simulation_state = _get_simulation_state(setup_payload)
    return {
        "ok": True,
        "npc_reasoning": inspect_npc_reasoning(simulation_state, npc_id),
    }


@rpg_inspection_bp.post("/api/rpg/gm/force_npc_goal")
async def force_npc_goal(request: Request):
    data = await request.json() or {}
    setup_payload = dict(data.get("setup_payload") or {})
    npc_id = str(data.get("npc_id") or "")
    goal = dict(data.get("goal") or {})
    simulation_state = _get_simulation_state(setup_payload)
    simulation_state = gm_force_npc_goal(simulation_state, npc_id, goal)
    setup_payload = _write_simulation_state(setup_payload, simulation_state)
    return {
        "ok": True,
        "setup_payload": setup_payload,
    }


@rpg_inspection_bp.post("/api/rpg/gm/force_faction_trend")
async def force_faction_trend(request: Request):
    data = await request.json() or {}
    setup_payload = dict(data.get("setup_payload") or {})
    faction_id = str(data.get("faction_id") or "")
    trend_patch = dict(data.get("trend_patch") or {})
    simulation_state = _get_simulation_state(setup_payload)
    simulation_state = gm_force_faction_trend(simulation_state, faction_id, trend_patch)
    setup_payload = _write_simulation_state(setup_payload, simulation_state)
    return {
        "ok": True,
        "setup_payload": setup_payload,
    }


@rpg_inspection_bp.post("/api/rpg/gm/debug_note")
async def gm_debug_note(request: Request):
    data = await request.json() or {}
    setup_payload = dict(data.get("setup_payload") or {})
    note = str(data.get("note") or "")
    simulation_state = _get_simulation_state(setup_payload)
    simulation_state = gm_append_debug_note(simulation_state, note)
    setup_payload = _write_simulation_state(setup_payload, simulation_state)
    return {
        "ok": True,
        "setup_payload": setup_payload,
    }


@rpg_inspection_bp.post("/api/rpg/inspect/world_events")
async def inspect_world_events(request: Request):
    data = await request.json() or {}
    setup_payload = dict(data.get("setup_payload") or {})
    simulation_state = _get_simulation_state(setup_payload)
    runtime_state = dict(data.get("runtime_state") or {})
    return {
        "ok": True,
        "world_events": build_world_events_view(simulation_state, runtime_state),
    }
