"""Phase 8.2 — Encounter API Routes.

Flask Blueprint with encounter endpoints:
- POST /api/rpg/encounter/start
- POST /api/rpg/encounter/action
- POST /api/rpg/encounter/npc_turn
- POST /api/rpg/encounter/end
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.rpg.player import ensure_player_state
from app.rpg.encounter import (
    ensure_encounter_state,
    build_encounter_from_scene,
    EncounterResolver,
)
from app.rpg.items import (
    ensure_inventory_state,
    record_inventory_loot,
    build_loot_from_encounter_state,
)
from app.rpg.party import run_companion_turns


rpg_encounter_bp = Blueprint("rpg_encounter_bp", __name__)
resolver = EncounterResolver()


def _get_simulation_state(setup_payload):
    """Extract simulation_state from setup_payload metadata."""
    meta = dict((setup_payload or {}).get("metadata") or {})
    return dict(meta.get("simulation_state") or {})


def _write_simulation_state(setup_payload, simulation_state):
    """Write simulation_state back into setup_payload metadata."""
    setup_payload = dict(setup_payload or {})
    meta = dict(setup_payload.get("metadata") or {})
    meta["simulation_state"] = dict(simulation_state or {})
    setup_payload["metadata"] = meta
    return setup_payload


@rpg_encounter_bp.post("/api/rpg/encounter/start")
def encounter_start():
    """Start a new encounter from a scene."""
    data = request.get_json(silent=True) or {}
    setup_payload = dict(data.get("setup_payload") or {})
    scene = dict(data.get("scene") or {})

    state = ensure_player_state(_get_simulation_state(setup_payload))
    state = ensure_encounter_state(state)

    encounter_state = build_encounter_from_scene(scene, state)
    encounter_state = resolver.start(encounter_state)
    state["player_state"]["encounter_state"] = encounter_state
    state["player_state"]["current_mode"] = "encounter"

    setup_payload = _write_simulation_state(setup_payload, state)
    return jsonify({
        "ok": True,
        "setup_payload": setup_payload,
        "encounter_state": encounter_state,
    })


@rpg_encounter_bp.post("/api/rpg/encounter/action")
def encounter_action():
    """Apply a player action in the current encounter."""
    data = request.get_json(silent=True) or {}
    setup_payload = dict(data.get("setup_payload") or {})
    action_type = str(data.get("action_type") or "")
    target_id = str(data.get("target_id") or "")

    state = ensure_player_state(_get_simulation_state(setup_payload))
    state = ensure_encounter_state(state)

    encounter_state = dict((state.get("player_state") or {}).get("encounter_state") or {})
    encounter_state.setdefault("loot_awarded", False)
    encounter_state = resolver.apply_player_action(encounter_state, action_type, target_id)
    encounter_state = resolver.resolve_if_finished(encounter_state)

    encounter_state = run_companion_turns(state, encounter_state)

    if encounter_state.get("status") == "resolved":
        state.setdefault("events", []).append({
            "type": "encounter_resolution",
            "origin": "encounter",
            "target_id": encounter_state.get("scene_id", ""),
            "location_id": encounter_state.get("location_id", ""),
            "summary": "Encounter outcome impacts world state.",
        })

        if not encounter_state.get("loot_awarded"):
            player_state = dict(state.get("player_state") or {})
            player_state = ensure_inventory_state(player_state)
            inventory_state = dict(player_state.get("inventory_state") or {})
            loot_items = build_loot_from_encounter_state(encounter_state)
            inventory_state = record_inventory_loot(inventory_state, loot_items)
            player_state["inventory_state"] = inventory_state
            state["player_state"] = player_state

            if loot_items:
                state.setdefault("events", []).append({
                    "type": "encounter_loot_awarded",
                    "origin": "inventory",
                    "target_id": encounter_state.get("scene_id", ""),
                    "location_id": encounter_state.get("location_id", ""),
                    "summary": "Player received encounter loot.",
                    "loot": loot_items[:10],
                })

            encounter_state["loot_awarded"] = True

    state["player_state"]["encounter_state"] = encounter_state
    setup_payload = _write_simulation_state(setup_payload, state)

    return jsonify({
        "ok": True,
        "setup_payload": setup_payload,
        "encounter_state": encounter_state,
        "inventory_state": dict((state.get("player_state") or {}).get("inventory_state") or {}),
    })


@rpg_encounter_bp.post("/api/rpg/encounter/npc_turn")
def encounter_npc_turn():
    """Advance NPC turn in the current encounter."""
    data = request.get_json(silent=True) or {}
    setup_payload = dict(data.get("setup_payload") or {})

    state = ensure_player_state(_get_simulation_state(setup_payload))
    state = ensure_encounter_state(state)

    encounter_state = dict((state.get("player_state") or {}).get("encounter_state") or {})
    encounter_state.setdefault("loot_awarded", False)
    encounter_state = resolver.apply_npc_turn(encounter_state)

    encounter_state = run_companion_turns(state, encounter_state)
    encounter_state = resolver.resolve_if_finished(encounter_state)

    if encounter_state.get("status") == "resolved" and not encounter_state.get("loot_awarded"):
        player_state = dict(state.get("player_state") or {})
        player_state = ensure_inventory_state(player_state)
        inventory_state = dict(player_state.get("inventory_state") or {})
        loot_items = build_loot_from_encounter_state(encounter_state)
        inventory_state = record_inventory_loot(inventory_state, loot_items)
        player_state["inventory_state"] = inventory_state
        state["player_state"] = player_state

        if loot_items:
            state.setdefault("events", []).append({
                "type": "encounter_loot_awarded",
                "origin": "inventory",
                "target_id": encounter_state.get("scene_id", ""),
                "location_id": encounter_state.get("location_id", ""),
                "summary": "Player received encounter loot.",
                "loot": loot_items[:10],
            })

        encounter_state["loot_awarded"] = True

    state["player_state"]["encounter_state"] = encounter_state
    setup_payload = _write_simulation_state(setup_payload, state)

    return jsonify({
        "ok": True,
        "setup_payload": setup_payload,
        "encounter_state": encounter_state,
        "inventory_state": dict((state.get("player_state") or {}).get("inventory_state") or {}),
    })


@rpg_encounter_bp.post("/api/rpg/encounter/end")
def encounter_end():
    """End the current encounter (abort)."""
    data = request.get_json(silent=True) or {}
    setup_payload = dict(data.get("setup_payload") or {})

    state = ensure_player_state(_get_simulation_state(setup_payload))
    state = ensure_encounter_state(state)

    encounter_state = dict((state.get("player_state") or {}).get("encounter_state") or {})
    encounter_state["active"] = False
    encounter_state["status"] = "aborted"

    state.setdefault("events", []).append({
        "type": "encounter_aborted",
        "origin": "encounter",
        "target_id": encounter_state.get("scene_id", ""),
        "summary": "Encounter was aborted.",
    })

    state["player_state"]["encounter_state"] = encounter_state
    state["player_state"]["current_mode"] = "scene"

    setup_payload = _write_simulation_state(setup_payload, state)
    return jsonify({
        "ok": True,
        "setup_payload": setup_payload,
        "encounter_state": encounter_state,
    })