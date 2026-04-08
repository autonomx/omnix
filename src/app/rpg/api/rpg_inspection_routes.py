from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.rpg.analytics import (
    build_tick_diff,
    build_timeline_row_diff,
    build_timeline_summary,
    get_timeline_tick,
    gm_append_debug_note,
    gm_force_faction_trend,
    gm_force_npc_goal,
    inspect_npc_reasoning,
)
from app.rpg.persistence.save_schema import CURRENT_RPG_SCHEMA_VERSION

rpg_inspection_bp = Blueprint("rpg_inspection_bp", __name__)


def _get_setup_payload():
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


@rpg_inspection_bp.post("/api/rpg/inspect/timeline")
def inspect_timeline():
    setup_payload = _get_setup_payload()
    simulation_state = _get_simulation_state(setup_payload)
    timeline_summary = build_timeline_summary(simulation_state)
    ticks = timeline_summary.get("timeline", {}).get("ticks") or []
    if len(ticks) >= 2:
        diff = build_timeline_row_diff(ticks[-2], ticks[-1])
    else:
        diff = {}
    return jsonify({
        "ok": True,
        "schema_version": CURRENT_RPG_SCHEMA_VERSION,
        "timeline": timeline_summary,
        "latest_diff": diff,
    })


@rpg_inspection_bp.post("/api/rpg/inspect/timeline_tick")
def inspect_timeline_tick():
    data = request.get_json(silent=True) or {}
    setup_payload = dict(data.get("setup_payload") or {})
    tick = int(data.get("tick", 0) or 0)
    simulation_state = _get_simulation_state(setup_payload)
    return jsonify({
        "ok": True,
        "tick_view": get_timeline_tick(simulation_state, tick),
    })


@rpg_inspection_bp.post("/api/rpg/inspect/tick_diff")
def inspect_tick_diff():
    data = request.get_json(silent=True) or {}
    before_state = dict(data.get("before_state") or {})
    after_state = dict(data.get("after_state") or {})
    return jsonify({
        "ok": True,
        "tick_diff": build_tick_diff(before_state, after_state),
    })


@rpg_inspection_bp.post("/api/rpg/inspect/npc_reasoning")
def inspect_npc():
    data = request.get_json(silent=True) or {}
    setup_payload = dict(data.get("setup_payload") or {})
    npc_id = str(data.get("npc_id") or "")
    simulation_state = _get_simulation_state(setup_payload)
    return jsonify({
        "ok": True,
        "npc_reasoning": inspect_npc_reasoning(simulation_state, npc_id),
    })


@rpg_inspection_bp.post("/api/rpg/gm/force_npc_goal")
def force_npc_goal():
    data = request.get_json(silent=True) or {}
    setup_payload = dict(data.get("setup_payload") or {})
    npc_id = str(data.get("npc_id") or "")
    goal = dict(data.get("goal") or {})
    simulation_state = _get_simulation_state(setup_payload)
    simulation_state = gm_force_npc_goal(simulation_state, npc_id, goal)
    setup_payload = _write_simulation_state(setup_payload, simulation_state)
    return jsonify({
        "ok": True,
        "setup_payload": setup_payload,
    })


@rpg_inspection_bp.post("/api/rpg/gm/force_faction_trend")
def force_faction_trend():
    data = request.get_json(silent=True) or {}
    setup_payload = dict(data.get("setup_payload") or {})
    faction_id = str(data.get("faction_id") or "")
    trend_patch = dict(data.get("trend_patch") or {})
    simulation_state = _get_simulation_state(setup_payload)
    simulation_state = gm_force_faction_trend(simulation_state, faction_id, trend_patch)
    setup_payload = _write_simulation_state(setup_payload, simulation_state)
    return jsonify({
        "ok": True,
        "setup_payload": setup_payload,
    })


@rpg_inspection_bp.post("/api/rpg/gm/debug_note")
def gm_debug_note():
    data = request.get_json(silent=True) or {}
    setup_payload = dict(data.get("setup_payload") or {})
    note = str(data.get("note") or "")
    simulation_state = _get_simulation_state(setup_payload)
    simulation_state = gm_append_debug_note(simulation_state, note)
    setup_payload = _write_simulation_state(setup_payload, simulation_state)
    return jsonify({
        "ok": True,
        "setup_payload": setup_payload,
    })