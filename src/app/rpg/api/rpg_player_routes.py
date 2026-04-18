"""Phase 8 — Player-facing API routes.

Exposes the lightweight player state layer via stable JSON endpoints
for UI integration.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from app.rpg.items import apply_item_use, list_item_definitions
from app.rpg.party import (
    add_companion,
    ensure_party_state,
    remove_companion,
)
from app.rpg.player import (
    build_player_inventory_view,
    ensure_player_inventory,
    ensure_player_state,
    enter_dialogue_mode,
    exit_dialogue_mode,
)
from app.rpg.player.player_encounter import build_encounter_view

rpg_player_bp = APIRouter()


async def _load_setup_payload() -> dict:
    data = await request.json() or {}
    return dict(data.get("setup_payload") or {})


async def _get_simulation_state(setup_payload: dict) -> dict:
    meta = dict((setup_payload or {}).get("metadata") or {})
    return dict(meta.get("simulation_state") or {})


async def _write_simulation_state(setup_payload: dict, simulation_state: dict) -> dict:
    setup_payload = dict(setup_payload or {})
    meta = dict(setup_payload.get("metadata") or {})
    meta["simulation_state"] = dict(simulation_state or {})
    setup_payload["metadata"] = meta
    return setup_payload


@rpg_player_bp.post("/api/rpg/player/state")
async def player_state():
    """Return the current player-facing state."""
    setup_payload = _load_setup_payload()
    state = ensure_player_state(_get_simulation_state(setup_payload))
    return jsonify({
        "ok": True,
        "player_state": state.get("player_state", {}),
    })


@rpg_player_bp.post("/api/rpg/player/journal")
async def player_journal():
    """Return the player journal entries (last 50)."""
    setup_payload = _load_setup_payload()
    state = ensure_player_state(_get_simulation_state(setup_payload))
    return jsonify({
        "ok": True,
        "journal_entries": list((state.get("player_state") or {}).get("journal_entries") or [])[-50:],
    })


@rpg_player_bp.post("/api/rpg/player/codex")
async def player_codex():
    """Return the player codex."""
    setup_payload = _load_setup_payload()
    state = ensure_player_state(_get_simulation_state(setup_payload))
    return jsonify({
        "ok": True,
        "codex": dict((state.get("player_state") or {}).get("codex") or {}),
    })


@rpg_player_bp.post("/api/rpg/player/objectives")
async def player_objectives():
    """Return the player active objectives (last 20)."""
    setup_payload = _load_setup_payload()
    state = ensure_player_state(_get_simulation_state(setup_payload))
    return jsonify({
        "ok": True,
        "active_objectives": list((state.get("player_state") or {}).get("active_objectives") or [])[-20:],
    })


@rpg_player_bp.post("/api/rpg/player/dialogue/enter")
async def player_dialogue_enter():
    """Enter dialogue mode with the specified NPC."""
    data = await request.json() or {}
    setup_payload = dict(data.get("setup_payload") or {})
    npc_id = str(data.get("npc_id") or "")
    scene_id = str(data.get("scene_id") or "")

    state = ensure_player_state(_get_simulation_state(setup_payload))
    state = enter_dialogue_mode(state, npc_id=npc_id, scene_id=scene_id)
    setup_payload = _write_simulation_state(setup_payload, state)

    return jsonify({
        "ok": True,
        "setup_payload": setup_payload,
        "player_state": state.get("player_state", {}),
    })


@rpg_player_bp.post("/api/rpg/player/dialogue/exit")
async def player_dialogue_exit():
    """Exit dialogue mode and return to the fallback mode."""
    data = await request.json() or {}
    setup_payload = dict(data.get("setup_payload") or {})
    fallback_mode = str(data.get("fallback_mode") or "scene")

    state = ensure_player_state(_get_simulation_state(setup_payload))
    state = exit_dialogue_mode(state, fallback_mode=fallback_mode)
    setup_payload = _write_simulation_state(setup_payload, state)

    return jsonify({
        "ok": True,
        "setup_payload": setup_payload,
        "player_state": state.get("player_state", {}),
    })


@rpg_player_bp.post("/api/rpg/player/encounter")
async def player_encounter():
    """Build and return an encounter view for a given scene."""
    data = await request.json() or {}
    setup_payload = dict(data.get("setup_payload") or {})
    scene = dict(data.get("scene") or {})
    state = ensure_player_state(_get_simulation_state(setup_payload))
    return jsonify({
        "ok": True,
        "encounter": build_encounter_view(scene, state),
    })


@rpg_player_bp.post("/api/rpg/player/inventory")
async def player_inventory():
    """Return the player inventory state and summary."""
    setup_payload = _load_setup_payload()
    state = ensure_player_state(_get_simulation_state(setup_payload))
    state = ensure_player_inventory(state)
    inventory_view = build_player_inventory_view(state)
    return jsonify({
        "ok": True,
        "inventory_state": inventory_view.get("inventory_state", {}),
        "inventory_summary": inventory_view.get("inventory_summary", {}),
    })


@rpg_player_bp.post("/api/rpg/player/inventory/use")
async def player_inventory_use():
    """Use one inventory item via deterministic item effect hooks."""
    data = await request.json() or {}
    setup_payload = dict(data.get("setup_payload") or {})
    item_id = str(data.get("item_id") or "")

    state = ensure_player_state(_get_simulation_state(setup_payload))
    state = ensure_player_inventory(state)

    result = apply_item_use(state, item_id)
    state = dict(result.get("simulation_state") or {})
    setup_payload = _write_simulation_state(setup_payload, state)

    inventory_view = build_player_inventory_view(state)
    return jsonify({
        "ok": bool((result.get("result") or {}).get("ok")),
        "setup_payload": setup_payload,
        "result": dict(result.get("result") or {}),
        "inventory_state": inventory_view.get("inventory_state", {}),
        "inventory_summary": inventory_view.get("inventory_summary", {}),
    })


@rpg_player_bp.post("/api/rpg/player/inventory/registry")
async def player_inventory_registry():
    """Return the full item registry for debug/GM tools."""
    return jsonify({
        "ok": True,
        "items": list_item_definitions(),
    })


@rpg_player_bp.post("/api/rpg/player/party")
async def player_party():
    """Return the current party state."""
    data = await request.json() or {}
    setup_payload = dict(data.get("setup_payload") or {})

    state = ensure_player_state(_get_simulation_state(setup_payload))
    player_state = ensure_party_state(state.get("player_state") or {})

    return jsonify({
        "ok": True,
        "party_state": player_state.get("party_state"),
    })


@rpg_player_bp.post("/api/rpg/player/party/recruit")
async def recruit_companion():
    """Recruit a new companion to the party."""
    data = await request.json() or {}
    npc_id = str(data.get("npc_id") or "")
    name = str(data.get("name") or "Companion")

    setup_payload = dict(data.get("setup_payload") or {})
    state = ensure_player_state(_get_simulation_state(setup_payload))

    # Validate NPC exists in world state
    npcs = state.get("npcs") or {}
    if npc_id not in npcs:
        return jsonify({
            "ok": False,
            "reason": "npc_not_found",
            "npc_id": npc_id,
        })

    player_state = state.get("player_state") or {}
    player_state = add_companion(player_state, npc_id, name)

    state["player_state"] = player_state
    setup_payload = _write_simulation_state(setup_payload, state)

    return jsonify({
        "ok": True,
        "setup_payload": setup_payload,
        "party_state": player_state.get("party_state"),
    })


@rpg_player_bp.post("/api/rpg/player/party/remove")
async def remove_companion_route():
    """Remove a companion from the party."""
    data = await request.json() or {}
    npc_id = str(data.get("npc_id") or "")

    setup_payload = dict(data.get("setup_payload") or {})
    state = ensure_player_state(_get_simulation_state(setup_payload))

    player_state = state.get("player_state") or {}
    player_state = remove_companion(player_state, npc_id)

    state["player_state"] = player_state
    setup_payload = _write_simulation_state(setup_payload, state)

    return jsonify({
        "ok": True,
        "setup_payload": setup_payload,
        "party_state": player_state.get("party_state"),
    })


# Phase 18.3A — Equipment and progression endpoints (session-aware)

@rpg_player_bp.post("/api/rpg/player/inventory/equip")
async def equip_item_route():
    """Equip an inventory item into equipment slot."""
    from app.rpg.items.inventory_state import equip_inventory_item
    from app.rpg.session.runtime import load_runtime_session, save_runtime_session

    data = await request.json() or {}
    item_id = str(data.get("item_id", ""))
    slot = str(data.get("slot", ""))
    session_id = str(data.get("session_id", ""))

    if not item_id:
        return {"ok": False, "error": "item_id required"}, 400

    if session_id:
        session = load_runtime_session(session_id)
        if session and isinstance(session, dict):
            sim = dict(session.get("simulation_state") or {})
            ps = dict(sim.get("player_state") or {})
            inv = dict(ps.get("inventory_state") or {})
            inv = equip_inventory_item(inv, item_id, slot)
            ps["inventory_state"] = inv
            sim["player_state"] = ps
            session["simulation_state"] = sim
            save_runtime_session(session)
            return {"ok": True, "item_id": item_id, "slot": slot, "equipment": inv.get("equipment", {})}

    return {"ok": True, "item_id": item_id, "slot": slot}


@rpg_player_bp.post("/api/rpg/player/inventory/unequip")
async def unequip_item_route():
    """Unequip an item from equipment slot."""
    from app.rpg.items.inventory_state import unequip_inventory_slot
    from app.rpg.session.runtime import load_runtime_session, save_runtime_session

    data = await request.json() or {}
    slot = str(data.get("slot", ""))
    session_id = str(data.get("session_id", ""))

    if not slot:
        return {"ok": False, "error": "slot required"}, 400

    if session_id:
        session = load_runtime_session(session_id)
        if session and isinstance(session, dict):
            sim = dict(session.get("simulation_state") or {})
            ps = dict(sim.get("player_state") or {})
            inv = dict(ps.get("inventory_state") or {})
            inv = unequip_inventory_slot(inv, slot)
            ps["inventory_state"] = inv
            sim["player_state"] = ps
            session["simulation_state"] = sim
            save_runtime_session(session)
            return {"ok": True, "slot": slot, "equipment": inv.get("equipment", {})}

    return {"ok": True, "slot": slot}


@rpg_player_bp.post("/api/rpg/player/inventory/drop")
async def drop_item_route():
    """Drop an item from inventory into the world."""
    from app.rpg.items.inventory_state import (
        get_inventory_item_for_drop,
        remove_inventory_item,
    )
    from app.rpg.items.world_items import drop_world_item
    from app.rpg.session.runtime import load_runtime_session, save_runtime_session

    data = await request.json() or {}
    item_id = str(data.get("item_id", ""))
    session_id = str(data.get("session_id", ""))

    if not item_id:
        return {"ok": False, "error": "item_id required"}, 400

    if session_id:
        session = load_runtime_session(session_id)
        if session and isinstance(session, dict):
            sim = dict(session.get("simulation_state") or {})
            runtime_state = dict(session.get("runtime_state") or {})
            ps = dict(sim.get("player_state") or {})
            inv = dict(ps.get("inventory_state") or {})
            dropped_item = get_inventory_item_for_drop(inv, item_id)
            inv = remove_inventory_item(inv, item_id, qty=1)
            ps["inventory_state"] = inv
            sim["player_state"] = ps

            location_id = (
                str(ps.get("location_id", "")).strip()
                or str(dict(runtime_state.get("current_scene") or {}).get("location_id", "")).strip()
                or str(dict(runtime_state.get("current_scene") or {}).get("scene_id", "")).strip()
            )
            drop_payload = dropped_item if dropped_item else {"item_id": item_id, "qty": 1}
            drop_result = drop_world_item(sim, drop_payload, location_id, qty=1)
            sim = dict(drop_result.get("simulation_state") or sim)
            ps = dict(sim.get("player_state") or {})
            final_inv = dict(ps.get("inventory_state") or {})
            session["simulation_state"] = sim
            save_runtime_session(session)
            return jsonify({
                "ok": True,
                "item_id": item_id,
                "location_id": location_id,
                "result": dict(drop_result.get("result") or {}),
                "equipment": dict(final_inv.get("equipment") or {}),
            })

    return {"ok": True, "item_id": item_id}


@rpg_player_bp.post("/api/rpg/player/inventory/pickup")
async def pickup_item_route():
    """Pick up a world item into inventory."""
    from app.rpg.items.inventory_state import add_inventory_items
    from app.rpg.items.world_items import pickup_world_item
    from app.rpg.session.runtime import load_runtime_session, save_runtime_session

    data = await request.json() or {}
    instance_id = str(data.get("instance_id", ""))
    session_id = str(data.get("session_id", ""))

    if not instance_id:
        return {"ok": False, "error": "instance_id required"}, 400

    if session_id:
        session = load_runtime_session(session_id)
        if session and isinstance(session, dict):
            sim = dict(session.get("simulation_state") or {})
            pickup_result = pickup_world_item(sim, instance_id)
            sim = dict(pickup_result.get("simulation_state") or sim)
            picked = dict(pickup_result.get("picked_up_item") or {})
            if picked and picked.get("item_id"):
                ps = dict(sim.get("player_state") or {})
                inv = dict(ps.get("inventory_state") or {})
                inv = add_inventory_items(inv, [picked])
                ps["inventory_state"] = inv
                sim["player_state"] = ps
                session["simulation_state"] = sim
                save_runtime_session(session)
                return jsonify({
                    "ok": True,
                    "instance_id": instance_id,
                    "item": picked,
                    "result": dict(pickup_result.get("result") or {}),
                    "equipment": dict(inv.get("equipment") or {}),
                })
            return jsonify({
                "ok": False,
                "error": "item_not_found",
                "instance_id": instance_id,
                "result": dict(pickup_result.get("result") or {}),
            }), 404

    return {"ok": True, "instance_id": instance_id}


@rpg_player_bp.post("/api/rpg/player/progression")
async def player_progression_route():
    """Get player progression data from session."""
    from app.rpg.session.runtime import load_runtime_session

    data = await request.json() or {}
    session_id = str(data.get("session_id", ""))

    if session_id:
        session = load_runtime_session(session_id)
        if session and isinstance(session, dict):
            sim = dict(session.get("simulation_state") or {})
            ps = dict(sim.get("player_state") or {})
            inventory_state = dict(ps.get("inventory_state") or {})
            return jsonify({
                "ok": True,
                "level": int(ps.get("level", 1) or 1),
                "xp": int(ps.get("xp", 0) or 0),
                "xp_to_next": int(ps.get("xp_to_next", 100) or 100),
                "unspent_points": int(ps.get("unspent_points", 0) or 0),
                "unspent_skill_points": int(ps.get("unspent_skill_points", 0) or 0),
                "stats": dict(ps.get("stats") or {}),
                "skills": dict(ps.get("skills") or {}),
                "perk_flags": list(ps.get("perk_flags") or []),
                "inventory_state": inventory_state,
                "equipment": dict(inventory_state.get("equipment") or {}),
            })

    return {"ok": True, "level": 1, "xp": 0, "xp_to_next": 100}


@rpg_player_bp.post("/api/rpg/player/stats/allocate")
async def allocate_stats_route():
    """Allocate stat points from session."""
    from app.rpg.player.player_progression_state import allocate_starting_stats
    from app.rpg.session.runtime import load_runtime_session, save_runtime_session

    data = await request.json() or {}
    allocation = data.get("allocation", {})
    session_id = str(data.get("session_id", ""))

    if not isinstance(allocation, dict) or not allocation:
        return {"ok": False, "error": "allocation required"}, 400

    if session_id:
        session = load_runtime_session(session_id)
        if session and isinstance(session, dict):
            sim = dict(session.get("simulation_state") or {})
            ps = dict(sim.get("player_state") or {})
            unspent = int(ps.get("unspent_points", 0) or 0)
            total_requested = sum(int(v) for v in allocation.values())
            if total_requested > unspent:
                return {"ok": False, "error": "insufficient_points", "unspent": unspent, "requested": total_requested}, 400
            ps = allocate_starting_stats(ps, allocation)
            ps["unspent_points"] = max(0, unspent - total_requested)
            sim["player_state"] = ps
            session["simulation_state"] = sim
            save_runtime_session(session)
            return {"ok": True, "stats": dict(ps.get("stats") or {}), "unspent_points": ps.get("unspent_points", 0)}

    return {"ok": True, "allocation": allocation}
