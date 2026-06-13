from __future__ import annotations

# Generated split module for app.rpg.session.runtime.
from .runtime_part01 import *
from .runtime_part02 import *
from .runtime_part03 import *
from .runtime_part04 import *
from .runtime_part05 import *
from .runtime_part06 import *
from .runtime_part07 import *
from .runtime_part08 import *
from .runtime_part09 import *
from .runtime_part10 import *
from .runtime_part11 import *
from .runtime_part12 import *
from .runtime_part13 import *
from .runtime_part14 import *
from .runtime_part15 import *
from .runtime_part16 import *
from .runtime_part17 import *
from .runtime_part18 import *
from .runtime_part19 import *
from .runtime_part20 import *

def _make_initiative_update_from_candidate(
    candidate: Dict[str, Any],
) -> Dict[str, Any]:
    """Convert an NPC initiative candidate into an ambient update."""
    candidate = _safe_dict(candidate)
    kind = _safe_str(candidate.get("kind") or "npc_to_player")
    speaker_name = _safe_str(candidate.get("speaker_name"))
    reason = _safe_str(candidate.get("reason"))
    action_intent = _safe_str(candidate.get("action_intent"))

    # Build default text from candidate metadata
    text = _safe_str(candidate.get("text_hint"))
    if not text:
        if kind == "quest_prompt":
            text = f"{speaker_name} has something important to share about your quest."
        elif kind == "recruitment_offer":
            text = f"{speaker_name} approaches with an offer."
        elif kind == "plea_for_help":
            text = f"{speaker_name} urgently needs your help."
        elif kind in ("taunt", "demand"):
            text = f"{speaker_name} confronts you."
        elif kind == "warning":
            text = f"{speaker_name} warns you of danger."
        elif kind == "companion_comment":
            reason = _safe_str(_safe_dict(candidate.get("structured")).get("reason") or candidate.get("reason"))
            if reason == "companion_idle_presence":
                text = f"{speaker_name} glances around, then leans closer to you."
            else:
                text = f"{speaker_name} murmurs a quick thought under their breath."
        else:
            text = f"{speaker_name} wants your attention."

    return {
        "tick": int(candidate.get("tick", 0) or 0),
        "kind": kind,
        "priority": float(candidate.get("salience", 0.0) or 0.0),
        "interrupt": bool(candidate.get("interrupt")),
        "speaker_id": _safe_str(candidate.get("speaker_id")),
        "speaker_name": speaker_name,
        "target_id": _safe_str(candidate.get("target_id")),
        "target_name": _safe_str(candidate.get("target_name")),
        "scene_id": "",
        "location_id": _safe_str(candidate.get("location_id")),
        "text": text,
        "structured": {
            "reason": reason,
            "action_intent": action_intent,
        },
        "source_event_ids": [],
        "source": "initiative",
        "created_at": _utc_now_iso(),
    }


def _make_scene_update_from_beat(beat: Dict[str, Any]) -> Dict[str, Any]:
    beat = _safe_dict(beat)
    return {
        "tick": 0,
        "kind": _safe_str(beat.get("kind") or "npc_to_npc"),
        "priority": float(beat.get("priority", 0.0) or 0.0),
        "interrupt": False,
        "speaker_id": _safe_str(beat.get("speaker_id")),
        "speaker_name": _safe_str(beat.get("speaker_name")),
        "target_id": _safe_str(beat.get("target_id")),
        "target_name": _safe_str(beat.get("target_name")),
        "scene_id": _safe_str(beat.get("scene_id")),
        "location_id": _safe_str(beat.get("location_id")),
        "text": _safe_str(beat.get("text_hint")),
        "structured": {
            "reason": _safe_str(beat.get("reason")),
            "scene_id": _safe_str(beat.get("scene_id")),
            "scene_kind": _safe_str(beat.get("scene_kind")),
            "beat_index": int(beat.get("beat_index", 0) or 0),
        },
        "source": "scene_weaver",
    }


def _apply_ambient_narration_and_delivery(
    *,
    session: Dict[str, Any],
    updates: List[Dict[str, Any]],
    after_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    idle_capture_key: str,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    session = _copy_dict(session)
    runtime_state = _copy_dict(runtime_state)
    current_scene = _safe_dict(runtime_state.get("current_scene"))
    narrated_updates: List[Dict[str, Any]] = []

    llm_gateway = None
    try:
        from app.shared import get_provider
        llm_gateway = get_provider()
    except Exception:
        llm_gateway = None

    runtime_state.setdefault("llm_records", [])
    runtime_state.setdefault("llm_records_index", {})

    # Defensive contract: this helper expects already-enqueued updates
    # so that seq/ambient_id are stable for capture and replacement.
    for idx, update in enumerate(updates):
        update = _safe_dict(update)
        if int(update.get("seq", 0) or 0) <= 0 or not _safe_str(update.get("ambient_id")):
            raise ValueError(
                f"_apply_ambient_narration_and_delivery requires enqueued updates with seq/ambient_id (index={idx})"
            )

    for idx, update in enumerate(updates):
        update = _copy_dict(update)
        narration = narrate_ambient_update(
            ambient_update=update,
            simulation_state=after_state,
            current_scene=current_scene,
            llm_gateway=llm_gateway,
        )
        update["text"] = _safe_str(narration.get("text"))
        update["speaker_turns"] = _safe_list(narration.get("speaker_turns"))
        update["narration"] = {
            "used_app_llm": bool(narration.get("used_app_llm")),
            "raw_llm_narrative": _safe_str(narration.get("raw_llm_narrative")),
            "structured": _safe_dict(narration.get("structured")),
        }
        update["delivery"] = classify_ambient_delivery(session, update, is_typing=False)

        if update["delivery"] == "interrupt":
            session = record_interrupt(session, update)
            runtime_state = _safe_dict(session.get("runtime_state"))
            runtime_state.setdefault("llm_records", [])
            runtime_state.setdefault("llm_records_index", {})

        capture_record = {
            "type": "ambient_narration",
            "idle_capture_key": idle_capture_key,
            "index": idx,
            "ambient_id": _safe_str(update.get("ambient_id")),
            "kind": _safe_str(update.get("kind")),
            "text": _safe_str(update.get("text")),
            "speaker_turns": _safe_list(update.get("speaker_turns")),
            "delivery": _safe_str(update.get("delivery")),
            "narration": _safe_dict(update.get("narration")),
        }
        runtime_state["llm_records"].append(capture_record)
        runtime_state["llm_records_index"][f"{idle_capture_key}:ambient:{idx}"] = capture_record
        narrated_updates.append(update)

    return narrated_updates, runtime_state


def apply_idle_tick(session_id: str, *, reason: str = "heartbeat") -> Dict[str, Any]:
    session = load_runtime_session(session_id)
    if session is None:
        return {"ok": False, "error": "session_not_found"}

    session = _copy_dict(session)
    result = _apply_idle_tick_to_session(session, reason=reason)
    if not result.get("ok"):
        return result

    session = save_runtime_session(_safe_dict(result.get("session")))
    runtime_state = _safe_dict(session.get("runtime_state"))

    return {
        "ok": True,
        "session": session,
        "updates": _safe_list(result.get("updates")),
        "latest_seq": int(runtime_state.get("ambient_seq", 0) or 0),
        "idle_streak": int(runtime_state.get("idle_streak", 0) or 0),
        "idle_debug_trace": result.get("idle_debug_trace", {}),
        "idle_seconds": result.get("idle_seconds", 0),
        "idle_gate_open": result.get("idle_gate_open", False),
        "settings": result.get("settings", {}),
    }


def apply_idle_ticks(session_id: str, count: int, *, reason: str = "heartbeat") -> Dict[str, Any]:
    """Apply multiple idle ticks, clamped to _MAX_IDLE_TICKS_PER_REQUEST.

    Coalesces results across ticks in memory and saves once at the end.
    """
    count = max(1, min(int(count), _MAX_IDLE_TICKS_PER_REQUEST))
    session = load_runtime_session(session_id)
    if session is None:
        return {"ok": False, "error": "session_not_found"}

    session = _copy_dict(session)
    all_updates: List[Dict[str, Any]] = []
    ticks_applied = 0

    for _ in range(count):
        result = _apply_idle_tick_to_session(session, reason=reason)
        if not result.get("ok"):
            if ticks_applied == 0:
                return result
            break
        session = _safe_dict(result.get("session"))
        all_updates.extend(_safe_list(result.get("updates")))
        ticks_applied += 1

    session = save_runtime_session(session)
    runtime_state = _safe_dict(session.get("runtime_state"))
    return {
        "ok": True,
        "session": session,
        "updates": all_updates,
        "latest_seq": int(runtime_state.get("ambient_seq", 0) or 0),
        "idle_streak": int(runtime_state.get("idle_streak", 0) or 0),
        "idle_debug_trace": result.get("idle_debug_trace", {}),
        "idle_seconds": result.get("idle_seconds", 0),
        "idle_gate_open": result.get("idle_gate_open", False),
        "settings": result.get("settings", {}),
    }


def apply_resume_catchup(session_id: str, *, elapsed_seconds: int = 0) -> Dict[str, Any]:
    """Apply bounded catch-up ticks on session resume.

    Converts elapsed time to capped idle ticks. If excess ticks would be
    generated, summarizes them into a single catch-up ambient update.
    """
    session = load_runtime_session(session_id)
    if session is None:
        return {"ok": False, "error": "session_not_found"}

    runtime_state = ensure_ambient_runtime_state(_safe_dict(session.get("runtime_state")))

    # Compute ticks from elapsed time (1 tick per ~5 seconds of real time)
    raw_ticks = max(0, elapsed_seconds // 5)
    capped_ticks = min(raw_ticks, _MAX_RESUME_CATCHUP_TICKS)
    excess_ticks = max(0, raw_ticks - capped_ticks)

    if capped_ticks == 0:
        return {
            "ok": True,
            "session": session,
            "updates": [],
            "latest_seq": int(runtime_state.get("ambient_seq", 0) or 0),
            "ticks_applied": 0,
            "excess_summarized": 0,
        }

    # Apply the capped ticks
    result = apply_idle_ticks(session_id, capped_ticks, reason="resume_catchup")
    if not result.get("ok"):
        return result

    excess_ticks = int(result.get("excess_summarized", 0) or 0)
    ticks_applied = int(result.get("ticks_applied", 0) or 0)
    all_updates = _safe_list(result.get("updates"))
    recap = {}

    # If the world advanced at all, build a resume recap
    if ticks_applied > 0:
        session = _safe_dict(result.get("session"))
        runtime_state = ensure_ambient_runtime_state(_safe_dict(session.get("runtime_state")))

        # Preserve bounded resume metadata for the richer recap payload, but do
        # not enqueue the old one-line system_summary update. The frontend will
        # render the recap block from world_advance_recap instead.
        runtime_state["resume_advance_ticks"] = ticks_applied
        session["runtime_state"] = runtime_state
        session = save_runtime_session(session)

        # 🔥 BUILD RECAP (THIS WAS MISSING)
        simulation_state = _safe_dict(session.get("simulation_state"))

        recap = _build_world_advance_recap(
            simulation_state,
            runtime_state,
            {
                "advance_ticks": ticks_applied,
                "summary": "",
                "scene_title": _safe_str(simulation_state.get("scene_title")),
                "location_name": _safe_str(simulation_state.get("location_name")),
            }
        )

        if not _recap_has_renderable_content(recap):
            recap = _build_resume_fallback_recap(session, runtime_state, ticks_applied)

        result["world_advance_recap"] = recap

    response = {
        "ok": True,
        "session": session if ticks_applied > 0 else _safe_dict(result.get("session")),
        "updates": all_updates,
        "latest_seq": int(result.get("latest_seq", 0) or 0),
        "ticks_applied": ticks_applied,
        "excess_summarized": excess_ticks,
        "world_advance_recap": _safe_dict(recap) if ticks_applied > 0 else _safe_dict(result.get("world_advance_recap")),
    }

    return response

__all__ = [name for name in globals() if not name.startswith("__")]
