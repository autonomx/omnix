from __future__ import annotations

from fastapi import APIRouter, Request

from app.rpg.ai.dialogue import DialogueManager
from app.rpg.player import ensure_player_state

rpg_dialogue_bp = APIRouter()
dialogue_manager = DialogueManager()


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


def _get_scene(setup_payload, scene_id: str):
    meta = dict((setup_payload or {}).get("metadata") or {})
    scenes = list(meta.get("scenes") or [])
    if not scenes:
        current_scene = meta.get("current_scene")
        if isinstance(current_scene, dict):
            scenes = [current_scene]
    for scene in scenes:
        if isinstance(scene, dict) and str(scene.get("scene_id") or scene.get("id") or "") == str(scene_id):
            return dict(scene)
    return {}


def _get_npc_and_mind(simulation_state, npc_id: str):
    npc_index = dict((simulation_state or {}).get("npc_index") or {})
    npc_minds = dict((simulation_state or {}).get("npc_minds") or {})
    return dict(npc_index.get(npc_id) or {}), dict(npc_minds.get(npc_id) or {})


@rpg_dialogue_bp.post("/api/rpg/dialogue/start")
async def dialogue_start(request: Request):
    data = await request.json() or {}
    setup_payload = dict(data.get("setup_payload") or {})
    npc_id = str(data.get("npc_id") or "")
    scene_id = str(data.get("scene_id") or "")

    state = ensure_player_state(_get_simulation_state(setup_payload))
    state = dialogue_manager.start_dialogue(state, npc_id=npc_id, scene_id=scene_id)
    setup_payload = _write_simulation_state(setup_payload, state)

    return {
        "ok": True,
        "setup_payload": setup_payload,
        "dialogue_state": state.get("player_state", {}).get("dialogue_state", {}),
    }


@rpg_dialogue_bp.post("/api/rpg/dialogue/message")
async def dialogue_message(request: Request):
    data = await request.json() or {}
    setup_payload = dict(data.get("setup_payload") or {})
    npc_id = str(data.get("npc_id") or "")
    scene_id = str(data.get("scene_id") or "")
    player_message = str(data.get("message") or "")

    state = ensure_player_state(_get_simulation_state(setup_payload))
    scene = _get_scene(setup_payload, scene_id)
    npc, npc_mind = _get_npc_and_mind(state, npc_id)

    result = dialogue_manager.send_message(
      simulation_state=state,
      npc=npc,
      scene=scene,
      npc_mind=npc_mind,
      player_message=player_message,
    )

    state = result["simulation_state"]
    setup_payload = _write_simulation_state(setup_payload, state)

    return {
        "ok": True,
        "setup_payload": setup_payload,
        "reply": result["reply"],
        "dialogue_state": result["dialogue_state"],
    }


@rpg_dialogue_bp.post("/api/rpg/dialogue/end")
async def dialogue_end(request: Request):
    data = await request.json() or {}
    setup_payload = dict(data.get("setup_payload") or {})

    state = ensure_player_state(_get_simulation_state(setup_payload))
    state = dialogue_manager.end_dialogue(state)
    setup_payload = _write_simulation_state(setup_payload, state)

    return {
        "ok": True,
        "setup_payload": setup_payload,
        "dialogue_state": state.get("player_state", {}).get("dialogue_state", {}),
    }
