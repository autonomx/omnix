from __future__ import annotations

from typing import Any, Dict

from app.rpg.ai.conversation_threads import build_conversation_thread_prompt_context
from app.rpg.ai.world_scene_narrator import narrate_scene
from app.rpg.llm_app_gateway import build_app_llm_gateway
from app.rpg.memory.service_memory_recall import recall_service_memories_for_narration
from app.rpg.session.state_normalization import (
    _safe_bool,
    _safe_dict,
    _safe_int,
    _safe_list,
    _safe_str,
)


def build_turn_narration_context(
    *,
    after_state: Dict[str, Any],
    player_input: str,
    resolved_result: Dict[str, Any],
    turn_contract: Dict[str, Any],
    progression: Dict[str, Any],
    runtime_state: Dict[str, Any],
    current_tick: int,
    combat_result: Dict[str, Any],
    npc_combat_result: Dict[str, Any],
    combat_state: Dict[str, Any],
) -> Dict[str, Any]:
    service_result = _safe_dict(resolved_result.get("service_result"))
    service_application = _safe_dict(resolved_result.get("service_application"))
    transaction_record = _safe_dict(
        resolved_result.get("transaction_record")
        or service_application.get("transaction_record")
    )
    recall_payload = recall_service_memories_for_narration(
        after_state,
        turn_contract=turn_contract,
        service_result=service_result,
        current_memory_entry=_safe_dict(
            resolved_result.get("memory_entry")
            or service_application.get("memory_entry")
        ),
        current_tick=int(
            _safe_dict(
                resolved_result.get("memory_entry")
                or service_application.get("memory_entry")
            ).get("tick")
            or _safe_dict(after_state).get("tick")
            or 0
        ),
    )
    resolved_result["recalled_service_memories"] = (
        recall_payload.get("recalled_service_memories") or []
    )
    resolved_result["service_memory_recall_debug"] = (
        recall_payload.get("debug") or {}
    )
    return {
        "simulation_state": after_state,
        "player_input": player_input,
        "resolved_result": resolved_result,
        "turn_contract": turn_contract,
        "service_result": service_result,
        "service_application": service_application,
        "transaction_record": transaction_record,
        "recalled_service_memories": recall_payload.get("recalled_service_memories") or [],
        "service_memory_recall_debug": recall_payload.get("debug") or {},
        "narration_brief": _safe_dict(turn_contract.get("narration_brief")),
        "state_delta": _safe_dict(turn_contract.get("state_delta")),
        "npc_behavior_context": _safe_dict(turn_contract.get("npc_behavior_context")),
        "xp_result": _safe_dict(progression.get("xp_result")),
        "skill_xp_result": _safe_dict(progression.get("skill_xp_result")),
        "level_up": _safe_list(progression.get("level_up")),
        "skill_level_ups": _safe_list(progression.get("skill_level_ups")),
        "settings": runtime_state.get("runtime_settings", {}),
        "conversation_threads": build_conversation_thread_prompt_context(
            runtime_state,
            current_tick=_safe_int(after_state.get("tick"), current_tick),
            limit=4,
        ),
        "combat_result": combat_result,
        "npc_combat_result": npc_combat_result,
        "combat_state": combat_state,
    }


def build_turn_narration_request(
    *,
    turn_id: str,
    tick: int,
    session_id: str,
    scene: Dict[str, Any],
    narration_context: Dict[str, Any],
    performance: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "turn_id": turn_id,
        "tick": tick,
        "session_id": session_id,
        "scene": _safe_dict(scene),
        "narration_context": _safe_dict(narration_context),
        "performance": _safe_dict(performance),
    }


def assemble_turn_narration_response(
    *,
    session: Dict[str, Any],
    authoritative: Dict[str, Any],
    turn_contract: Dict[str, Any],
    narration_request: Dict[str, Any],
    runtime_state: Dict[str, Any],
    perf: Dict[str, Any],
    resolved_result: Dict[str, Any],
) -> Dict[str, Any]:
    authoritative = _safe_dict(authoritative)
    narration_request = _safe_dict(narration_request)
    runtime_state = _safe_dict(runtime_state)
    perf = _safe_dict(perf)
    turn_contract = _safe_dict(turn_contract)
    resolved_result = _safe_dict(resolved_result)

    force_sync = bool(runtime_state.get("force_sync_narration", False))

    if force_sync:
        print("[RPG][narration][sync] calling narrate_scene")

        sync_scene = _safe_dict(narration_request.get("scene") or runtime_state.get("current_scene"))
        sync_context = _safe_dict(narration_request.get("narration_context"))
        runtime_performance = _safe_dict(runtime_state.get("performance"))
        runtime_settings = _safe_dict(runtime_state.get("runtime_settings") or runtime_state.get("settings"))
        sync_simulation_state = _safe_dict(sync_context.get("simulation_state"))
        if _safe_dict(resolved_result.get("memory_state")):
            sync_simulation_state["memory_state"] = _safe_dict(resolved_result.get("memory_state"))
        if _safe_dict(resolved_result.get("relationship_state")):
            sync_simulation_state["relationship_state"] = _safe_dict(resolved_result.get("relationship_state"))
        if _safe_dict(resolved_result.get("npc_emotion_state")):
            sync_simulation_state["npc_emotion_state"] = _safe_dict(resolved_result.get("npc_emotion_state"))
        if _safe_dict(resolved_result.get("service_offer_state")):
            sync_simulation_state["service_offer_state"] = _safe_dict(resolved_result.get("service_offer_state"))
        sync_context["simulation_state"] = sync_simulation_state
        sync_context["turn_contract"] = turn_contract
        sync_context["resolved_result"] = resolved_result
        sync_context["narration_brief"] = _safe_dict(turn_contract.get("narration_brief"))
        sync_context["state_delta"] = _safe_dict(turn_contract.get("state_delta"))
        sync_context["npc_behavior_context"] = _safe_dict(turn_contract.get("npc_behavior_context"))
        sync_context["force_sync_narration"] = True
        sync_context["require_live_llm_narration"] = bool(
            sync_context.get("require_live_llm_narration")
            or runtime_settings.get("require_live_llm_narration")
            or runtime_performance.get("require_live_llm_narration")
        )
        sync_context["performance"] = runtime_performance
        sync_context["runtime_settings"] = runtime_settings

        if not sync_context.get("recalled_service_memories"):
            recall_payload = recall_service_memories_for_narration(
                _safe_dict(sync_context.get("simulation_state")),
                narration_context=sync_context,
                turn_contract=turn_contract,
                service_result=_safe_dict(resolved_result.get("service_result")),
            )
            sync_context["recalled_service_memories"] = (
                recall_payload.get("recalled_service_memories") or []
            )
            sync_context["service_memory_recall_debug"] = recall_payload.get("debug") or {}
            resolved_result["recalled_service_memories"] = sync_context["recalled_service_memories"]
            resolved_result["service_memory_recall_debug"] = sync_context["service_memory_recall_debug"]

        llm_enabled = bool(perf.get("enable_live_narration_llm", True))
        llm_gateway = build_app_llm_gateway() if llm_enabled else None

        try:
            narration_payload = narrate_scene(sync_scene, sync_context, llm_gateway=llm_gateway)
        except Exception as exc:
            print("[RPG][narration][sync] failed", {"error": repr(exc)})
            raise

        authoritative["narration"] = _safe_str(narration_payload.get("narration"))
        authoritative["narration_json"] = _safe_dict(narration_payload.get("narration_json"))
        authoritative["raw_llm_narrative"] = narration_payload
        authoritative["used_llm"] = _safe_bool(narration_payload.get("used_llm"), False)
        authoritative["narration_status"] = "completed"
        authoritative["turn_contract"] = turn_contract
        authoritative["narration_debug"] = {
            "narration_json": authoritative["narration_json"],
            "used_llm": authoritative["used_llm"],
            "narration_status": authoritative["narration_status"],
            "recalled_service_memories": sync_context.get("recalled_service_memories") or [],
            "service_memory_recall_debug": sync_context.get("service_memory_recall_debug") or {},
        }

        print(
            "[RPG][narration][sync] completed",
            {
                "used_llm": authoritative["used_llm"],
                "has_text": bool(authoritative["narration"].strip()),
                "has_turn_contract": bool(turn_contract),
            },
        )
        narration = _safe_str(authoritative.get("narration"))
        raw_llm_narrative = authoritative.get("raw_llm_narrative")
        used_llm = _safe_bool(authoritative.get("used_llm"), False)
        narration_status = _safe_str(authoritative.get("narration_status"))
    else:
        narration = _safe_str(authoritative.get("deterministic_fallback_narration"))
        raw_llm_narrative = ""
        used_llm = False
        narration_status = "queued"

    return {
        "ok": True,
        "session": session,
        "turn_contract": _safe_dict(authoritative.get("turn_contract") or turn_contract),
        "result": {
            "turn_id": authoritative.get("turn_id"),
            "tick": authoritative.get("tick"),
            "resolved_result": authoritative.get("resolved_result"),
            "combat_result": authoritative.get("combat_result"),
            "xp_result": authoritative.get("xp_result"),
            "skill_xp_result": authoritative.get("skill_xp_result"),
            "level_up": authoritative.get("level_up"),
            "skill_level_ups": authoritative.get("skill_level_ups"),
            "summary": authoritative.get("summary"),
            "presentation": authoritative.get("presentation"),
            "response_length": authoritative.get("response_length"),
            "narration": narration,
            "raw_llm_narrative": raw_llm_narrative,
            "used_llm": used_llm,
            "narration_status": narration_status,
            "narration_debug": _safe_dict(authoritative.get("narration_debug")),
        },
    }
