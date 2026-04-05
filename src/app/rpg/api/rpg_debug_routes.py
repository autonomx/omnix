from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.rpg.creator.world_debug import (
    summarize_npc_minds,
    summarize_social_state,
    summarize_world_pressures,
    explain_npc,
    explain_faction,
)
from app.rpg.creator.world_gm_tools import (
    inject_event,
    seed_rumor,
    force_alliance,
    force_faction_position,
    force_npc_belief,
    step_ticks,
)
from app.rpg.creator.world_replay import (
    list_snapshots,
    get_snapshot,
    rollback_to_snapshot,
    summarize_timeline,
)
from app.rpg.creator.world_simulation import step_simulation_state


rpg_debug_bp = Blueprint("rpg_debug_bp", __name__)


def _load_setup_payload():
    data = request.get_json(silent=True) or {}
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
def debug_state():
    setup_payload = _load_setup_payload()
    state = _get_simulation_state(setup_payload)
    return jsonify({
        "ok": True,
        "tick": int(state.get("tick", 0) or 0),
        "npc_minds": summarize_npc_minds(state),
        "social": summarize_social_state(state),
        "pressures": summarize_world_pressures(state),
        "timeline": summarize_timeline(state),
    })


@rpg_debug_bp.post("/api/rpg/debug/npc")
def debug_npc():
    data = request.get_json(silent=True) or {}
    setup_payload = dict(data.get("setup_payload") or {})
    npc_id = str(data.get("npc_id") or "")
    state = _get_simulation_state(setup_payload)
    return jsonify({"ok": True, "npc": explain_npc(state, npc_id)})


@rpg_debug_bp.post("/api/rpg/debug/faction")
def debug_faction():
    data = request.get_json(silent=True) or {}
    setup_payload = dict(data.get("setup_payload") or {})
    faction_id = str(data.get("faction_id") or "")
    state = _get_simulation_state(setup_payload)
    return jsonify({"ok": True, "faction": explain_faction(state, faction_id)})


@rpg_debug_bp.post("/api/rpg/debug/step")
def debug_step():
    data = request.get_json(silent=True) or {}
    setup_payload = dict(data.get("setup_payload") or {})
    count = int(data.get("count", 1) or 1)
    result = step_ticks(setup_payload, step_simulation_state, count=count)
    next_setup = result.get("next_setup", result)
    return jsonify({"ok": True, "setup_payload": next_setup})


@rpg_debug_bp.post("/api/rpg/debug/inject_event")
def debug_inject_event():
    data = request.get_json(silent=True) or {}
    setup_payload = dict(data.get("setup_payload") or {})
    event = dict(data.get("event") or {})
    state = _get_simulation_state(setup_payload)
    state = inject_event(state, event, reason="gm_injection")
    setup_payload = _write_simulation_state(setup_payload, state)
    return jsonify({"ok": True, "setup_payload": setup_payload})


@rpg_debug_bp.post("/api/rpg/debug/seed_rumor")
def debug_seed_rumor():
    data = request.get_json(silent=True) or {}
    setup_payload = dict(data.get("setup_payload") or {})
    rumor = dict(data.get("rumor") or {})
    state = _get_simulation_state(setup_payload)
    state = seed_rumor(state, rumor)
    setup_payload = _write_simulation_state(setup_payload, state)
    return jsonify({"ok": True, "setup_payload": setup_payload})


@rpg_debug_bp.post("/api/rpg/debug/force_alliance")
def debug_force_alliance():
    data = request.get_json(silent=True) or {}
    setup_payload = dict(data.get("setup_payload") or {})
    alliance = dict(data.get("alliance") or {})
    state = _get_simulation_state(setup_payload)
    state = force_alliance(state, alliance)
    setup_payload = _write_simulation_state(setup_payload, state)
    return jsonify({"ok": True, "setup_payload": setup_payload})


@rpg_debug_bp.post("/api/rpg/debug/force_faction_position")
def debug_force_faction_position():
    data = request.get_json(silent=True) or {}
    setup_payload = dict(data.get("setup_payload") or {})
    faction_id = str(data.get("faction_id") or "")
    position = dict(data.get("position") or {})
    state = _get_simulation_state(setup_payload)
    state = force_faction_position(state, faction_id, position)
    setup_payload = _write_simulation_state(setup_payload, state)
    return jsonify({"ok": True, "setup_payload": setup_payload})


@rpg_debug_bp.post("/api/rpg/debug/force_npc_belief")
def debug_force_npc_belief():
    data = request.get_json(silent=True) or {}
    setup_payload = dict(data.get("setup_payload") or {})
    npc_id = str(data.get("npc_id") or "")
    target_id = str(data.get("target_id") or "")
    belief_patch = dict(data.get("belief_patch") or {})
    state = _get_simulation_state(setup_payload)
    state = force_npc_belief(state, npc_id, target_id, belief_patch)
    setup_payload = _write_simulation_state(setup_payload, state)
    return jsonify({"ok": True, "setup_payload": setup_payload})


@rpg_debug_bp.post("/api/rpg/debug/snapshots")
def debug_snapshots():
    setup_payload = _load_setup_payload()
    state = _get_simulation_state(setup_payload)
    return jsonify({"ok": True, "snapshots": list_snapshots(state)})


@rpg_debug_bp.post("/api/rpg/debug/snapshot")
def debug_snapshot():
    data = request.get_json(silent=True) or {}
    setup_payload = dict(data.get("setup_payload") or {})
    snapshot_id = str(data.get("snapshot_id") or "")
    state = _get_simulation_state(setup_payload)
    return jsonify({"ok": True, "snapshot": get_snapshot(state, snapshot_id)})


@rpg_debug_bp.post("/api/rpg/debug/rollback")
def debug_rollback():
    data = request.get_json(silent=True) or {}
    setup_payload = dict(data.get("setup_payload") or {})
    snapshot_id = str(data.get("snapshot_id") or "")
    state = _get_simulation_state(setup_payload)
    rolled = rollback_to_snapshot(state, snapshot_id)
    setup_payload = _write_simulation_state(setup_payload, rolled)
    return jsonify({"ok": True, "setup_payload": setup_payload})