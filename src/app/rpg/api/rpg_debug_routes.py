from __future__ import annotations

from fastapi import APIRouter, Request

from app.logging import write_rpg_log
from app.rpg.creator.world_debug import (
    explain_faction,
    explain_npc,
    summarize_npc_minds,
    summarize_social_state,
    summarize_world_pressures,
)
from app.rpg.creator.world_gm_tools import (
    force_alliance,
    force_faction_position,
    force_npc_belief,
    inject_event,
    seed_rumor,
    step_ticks,
)
from app.rpg.creator.world_replay import (
    get_snapshot,
    list_snapshots,
    rollback_to_snapshot,
    summarize_timeline,
)
from app.rpg.creator.world_simulation import step_simulation_state

rpg_debug_bp = APIRouter()


async def _load_setup_payload(request: Request):
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


@rpg_debug_bp.post("/api/rpg/debug/state")
async def debug_state(request: Request):
    setup_payload = await _load_setup_payload(request)
    state = _get_simulation_state(setup_payload)
    return {
        "ok": True,
        "tick": int(state.get("tick", 0) or 0),
        "npc_minds": summarize_npc_minds(state),
        "social": summarize_social_state(state),
        "pressures": summarize_world_pressures(state),
        "timeline": summarize_timeline(state),
    }


@rpg_debug_bp.post("/api/rpg/debug/npc")
async def debug_npc(request: Request):
    data = await request.json() or {}
    setup_payload = dict(data.get("setup_payload") or {})
    npc_id = str(data.get("npc_id") or "")
    state = _get_simulation_state(setup_payload)
    return {"ok": True, "npc": explain_npc(state, npc_id)}


@rpg_debug_bp.post("/api/rpg/debug/faction")
async def debug_faction(request: Request):
    data = await request.json() or {}
    setup_payload = dict(data.get("setup_payload") or {})
    faction_id = str(data.get("faction_id") or "")
    state = _get_simulation_state(setup_payload)
    return {"ok": True, "faction": explain_faction(state, faction_id)}


@rpg_debug_bp.post("/api/rpg/debug/step")
async def debug_step(request: Request):
    data = await request.json() or {}
    setup_payload = dict(data.get("setup_payload") or {})
    count = int(data.get("count", 1) or 1)
    result = step_ticks(setup_payload, step_simulation_state, count=count)
    next_setup = result.get("next_setup", result)
    return {"ok": True, "setup_payload": next_setup}


@rpg_debug_bp.post("/api/rpg/debug/inject_event")
async def debug_inject_event(request: Request):
    data = await request.json() or {}
    setup_payload = dict(data.get("setup_payload") or {})
    event = dict(data.get("event") or {})
    state = _get_simulation_state(setup_payload)
    state = inject_event(state, event, reason="gm_injection")
    setup_payload = _write_simulation_state(setup_payload, state)
    return {"ok": True, "setup_payload": setup_payload}


@rpg_debug_bp.post("/api/rpg/debug/seed_rumor")
async def debug_seed_rumor(request: Request):
    data = await request.json() or {}
    setup_payload = dict(data.get("setup_payload") or {})
    rumor = dict(data.get("rumor") or {})
    state = _get_simulation_state(setup_payload)
    state = seed_rumor(state, rumor)
    setup_payload = _write_simulation_state(setup_payload, state)
    return {"ok": True, "setup_payload": setup_payload}


@rpg_debug_bp.post("/api/rpg/debug/force_alliance")
async def debug_force_alliance(request: Request):
    data = await request.json() or {}
    setup_payload = dict(data.get("setup_payload") or {})
    alliance = dict(data.get("alliance") or {})
    state = _get_simulation_state(setup_payload)
    state = force_alliance(state, alliance)
    setup_payload = _write_simulation_state(setup_payload, state)
    return {"ok": True, "setup_payload": setup_payload}


@rpg_debug_bp.post("/api/rpg/debug/force_faction_position")
async def debug_force_faction_position(request: Request):
    data = await request.json() or {}
    setup_payload = dict(data.get("setup_payload") or {})
    faction_id = str(data.get("faction_id") or "")
    position = dict(data.get("position") or {})
    state = _get_simulation_state(setup_payload)
    state = force_faction_position(state, faction_id, position)
    setup_payload = _write_simulation_state(setup_payload, state)
    return {"ok": True, "setup_payload": setup_payload}


@rpg_debug_bp.post("/api/rpg/debug/force_npc_belief")
async def debug_force_npc_belief(request: Request):
    data = await request.json() or {}
    setup_payload = dict(data.get("setup_payload") or {})
    npc_id = str(data.get("npc_id") or "")
    target_id = str(data.get("target_id") or "")
    belief_patch = dict(data.get("belief_patch") or {})
    state = _get_simulation_state(setup_payload)
    state = force_npc_belief(state, npc_id, target_id, belief_patch)
    setup_payload = _write_simulation_state(setup_payload, state)
    return {"ok": True, "setup_payload": setup_payload}


@rpg_debug_bp.post("/api/rpg/debug/snapshots")
async def debug_snapshots(request: Request):
    setup_payload = await _load_setup_payload(request)
    state = _get_simulation_state(setup_payload)
    return {"ok": True, "snapshots": list_snapshots(state)}


@rpg_debug_bp.post("/api/rpg/debug/snapshot")
async def debug_snapshot(request: Request):
    data = await request.json() or {}
    setup_payload = dict(data.get("setup_payload") or {})
    snapshot_id = str(data.get("snapshot_id") or "")
    state = _get_simulation_state(setup_payload)
    return {"ok": True, "snapshot": get_snapshot(state, snapshot_id)}


@rpg_debug_bp.post("/api/rpg/debug/rollback")
async def debug_rollback(request: Request):
    data = await request.json() or {}
    setup_payload = dict(data.get("setup_payload") or {})
    snapshot_id = str(data.get("snapshot_id") or "")
    state = _get_simulation_state(setup_payload)
    rolled = rollback_to_snapshot(state, snapshot_id)
    setup_payload = _write_simulation_state(setup_payload, rolled)
    return {"ok": True, "setup_payload": setup_payload}


@rpg_debug_bp.post("/api/rpg/log")
async def rpg_log_endpoint(request: Request):
    data = await request.json() or {}
    write_rpg_log(
        message=data.get("tag", "frontend_log"),
        extra={
            "payload": data.get("payload"),
            "timestamp": data.get("timestamp"),
            "source": "frontend"
        }
    )
    return {"ok": True}
