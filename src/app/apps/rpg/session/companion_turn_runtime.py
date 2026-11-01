from __future__ import annotations

# RPG session runtime responsibility module.
from app.apps.rpg.session.state_normalization import (
    _copy_dict as _copy_dict,
    _safe_dict as _safe_dict,
    _safe_str as _safe_str,
)
from app.apps.rpg.foundation.safe_values import safe_list as _safe_list
from typing import (
    Any as Any, Dict as Dict, List as List,
)


# Phase F — quiet-window ticks after player action


def _ensure_narration_artifact_state(runtime_state: dict[str, Any]) -> dict[str, Any]:
    runtime_state = _copy_dict(runtime_state)
    runtime_state.setdefault("narration_artifacts", [])
    runtime_state.setdefault("narration_artifacts_by_turn", {})
    return runtime_state


def _prune_narration_artifacts(runtime_state: dict[str, Any], max_items: int = 48) -> dict[str, Any]:
    runtime_state = _ensure_narration_artifact_state(runtime_state)
    artifacts = _safe_list(runtime_state.get("narration_artifacts"))
    if len(artifacts) > max_items:
        artifacts = artifacts[-max_items:]
    runtime_state["narration_artifacts"] = artifacts

    by_turn = _safe_dict(runtime_state.get("narration_artifacts_by_turn"))
    allowed_turn_ids = {
        _safe_str(item.get("turn_id")).strip()
        for item in artifacts
        if isinstance(item, dict)
    }
    runtime_state["narration_artifacts_by_turn"] = {
        k: v for k, v in by_turn.items() if k in allowed_turn_ids
    }
    return runtime_state


def _store_narration_artifact(runtime_state: dict[str, Any], artifact: dict[str, Any]) -> dict[str, Any]:
    runtime_state = _ensure_narration_artifact_state(runtime_state)
    artifact = _safe_dict(artifact)
    turn_id = _safe_str(artifact.get("turn_id")).strip()
    if not turn_id:
        return runtime_state

    artifacts = _safe_list(runtime_state.get("narration_artifacts"))
    artifacts = [a for a in artifacts if _safe_str(_safe_dict(a).get("turn_id")).strip() != turn_id]
    artifacts.append(artifact)
    runtime_state["narration_artifacts"] = artifacts

    by_turn = _safe_dict(runtime_state.get("narration_artifacts_by_turn"))
    by_turn[turn_id] = artifact
    runtime_state["narration_artifacts_by_turn"] = by_turn

    return _prune_narration_artifacts(runtime_state)


_COMPLETED_NARRATION_ARTIFACT_SOURCES = {
    "provider_sync_visible_turn_narration",
    "phase8_sync_narration_stream_payload_mirror",
    "phase8_llm_narration_authority_over_deterministic_fallback",
    "phase8_current_turn_bound_semantic_visible_response",
    "semantic_classifier_visible_response",
    "phase8_fast_semantic_direct_dialogue_response",
    "phase8_turn_bound_llm_visible_response",
    "phase8_player_turn_late_narration_artifact_store",
}
_DETERMINISTIC_NARRATION_ARTIFACT_SOURCES = {
    "deterministic_phase8_queued_narration_visible_fallback_gate",
    "phase8_part30_deterministic_dialogue_fallback",
    "deterministic",
    "deterministic_fallback",
}


def _narration_artifact_text(artifact: dict[str, Any]) -> str:
    artifact = _safe_dict(artifact)
    return _safe_str(
        artifact.get("final_narration")
        or artifact.get("narration")
        or artifact.get("raw_payload_narration")
        or artifact.get("deterministic_fallback_narration")
    ).strip()


def _narration_artifact_norm_text(value: Any) -> str:
    text = _safe_str(value).strip().casefold()
    return " ".join("".join(ch if ch.isalnum() else " " for ch in text).split())


def _narration_artifact_is_echo_fallback(artifact: dict[str, Any]) -> bool:
    text = _narration_artifact_norm_text(_narration_artifact_text(artifact))
    return bool(text.startswith("you continue "))


def _narration_artifact_has_structured_llm_content(artifact: dict[str, Any]) -> bool:
    artifact = _safe_dict(artifact)
    narration_json = _safe_dict(artifact.get("narration_json"))
    raw = artifact.get("raw_llm_narrative")
    npc = _safe_dict(artifact.get("npc")) or _safe_dict(narration_json.get("npc"))
    semantic_visible = _safe_dict(
        artifact.get("semantic_visible_response")
        or artifact.get("visible_response")
    )
    if isinstance(raw, dict) and raw:
        return True
    if isinstance(raw, str) and raw.strip():
        return True
    if _safe_str(narration_json.get("format_version")).strip():
        return True
    if _safe_str(narration_json.get("narration")).strip() or npc:
        return True
    if semantic_visible:
        return True
    return False


def _narration_artifact_completes_turn(artifact: dict[str, Any]) -> bool:
    artifact = _safe_dict(artifact)
    if not artifact:
        return False
    if not _narration_artifact_text(artifact):
        return False
    if _narration_artifact_is_echo_fallback(artifact):
        return False

    source = _safe_str(
        artifact.get("fallback_narration_source")
        or artifact.get("source")
        or artifact.get("late_artifact_policy")
    ).strip()
    if source in _DETERMINISTIC_NARRATION_ARTIFACT_SOURCES:
        return False
    if source in _COMPLETED_NARRATION_ARTIFACT_SOURCES:
        return True
    if _narration_artifact_has_structured_llm_content(artifact):
        return True
    if artifact.get("used_llm") is True or artifact.get("llm_called") is True:
        return _narration_artifact_has_structured_llm_content(artifact)

    # Backwards compatibility for older stored artifacts that predate source
    # metadata.  They still block duplicates unless they look like the generic
    # player-input echo fallback above.
    return True


def _build_ambient_turn_id(thread_id: str, beat_id: str) -> str:
    thread_id = _safe_str(thread_id).strip() or "conv:unknown"
    beat_id = _safe_str(beat_id).strip() or "beat:unknown"
    return f"ambient:{thread_id}:{beat_id}"


_AMBIENT_NARRATION_THREAD_COOLDOWN_TICKS = 2
_MAX_AMBIENT_NARRATION_ENQUEUES_PER_TICK = 2


def _ensure_ambient_narration_state(runtime_state: dict[str, Any]) -> dict[str, Any]:
    runtime_state = _copy_dict(runtime_state)
    runtime_state.setdefault("ambient_narration_state", {})
    ambient = _safe_dict(runtime_state.get("ambient_narration_state"))
    ambient.setdefault("last_narrated_tick_by_thread", {})
    ambient.setdefault("last_enqueued_turn_ids", [])
    runtime_state["ambient_narration_state"] = ambient
    return runtime_state


def _get_last_ambient_narrated_tick(runtime_state: dict[str, Any], thread_id: str) -> int:
    runtime_state = _ensure_ambient_narration_state(runtime_state)
    ambient = _safe_dict(runtime_state.get("ambient_narration_state"))
    by_thread = _safe_dict(ambient.get("last_narrated_tick_by_thread"))
    return int(by_thread.get(_safe_str(thread_id).strip(), -999999) or -999999)


def _record_ambient_narration_enqueue(runtime_state: dict[str, Any], thread_id: str, tick: int, turn_id: str) -> dict[str, Any]:
    runtime_state = _ensure_ambient_narration_state(runtime_state)
    ambient = _safe_dict(runtime_state.get("ambient_narration_state"))

    by_thread = _safe_dict(ambient.get("last_narrated_tick_by_thread"))
    by_thread[_safe_str(thread_id).strip()] = int(tick or 0)
    ambient["last_narrated_tick_by_thread"] = by_thread

    recent_turn_ids = _safe_list(ambient.get("last_enqueued_turn_ids"))
    recent_turn_ids.append(_safe_str(turn_id).strip())
    ambient["last_enqueued_turn_ids"] = recent_turn_ids[-64:]

    runtime_state["ambient_narration_state"] = ambient
    return runtime_state


def _has_narration_artifact_for_turn(runtime_state: dict[str, Any], turn_id: str) -> bool:
    runtime_state = _safe_dict(runtime_state)
    by_turn = _safe_dict(runtime_state.get("narration_artifacts_by_turn"))
    artifact = _safe_dict(by_turn.get(_safe_str(turn_id).strip()))
    return _narration_artifact_completes_turn(artifact)


def _select_latest_ambient_conversation_beats_per_active_thread(
    simulation_state: dict[str, Any],
    runtime_state: dict[str, Any],
) -> list[dict[str, Any]]:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _safe_dict(runtime_state)

    conversations = _safe_dict(_safe_dict(simulation_state.get("social_state")).get("conversations"))
    beats_by_thread = _safe_dict(conversations.get("beats_by_thread"))
    if not beats_by_thread:
        return []

    active_ids = [
        _safe_str(_safe_dict(c).get("conversation_id")).strip()
        for c in _safe_list(conversations.get("active"))
        if isinstance(c, dict)
    ]

    selected: list[dict[str, Any]] = []
    for thread_id in active_ids:
        rows = [b for b in _safe_list(beats_by_thread.get(thread_id)) if isinstance(b, dict)]
        if not rows:
            continue
        selected.append(_safe_dict(rows[-1]))

    selected.sort(
        key=lambda b: (
            -int(_safe_dict(b).get("tick", 0) or 0),
            _safe_str(_safe_dict(b).get("thread_id")),
        )
    )
    return selected


def _build_ambient_conversation_narration_request(
    simulation_state: dict[str, Any],
    runtime_state: dict[str, Any],
    beat: dict[str, Any],
) -> dict[str, Any]:
    beat = _safe_dict(beat)
    if not beat:
        return {}

    thread_id = _safe_str(beat.get("thread_id")).strip()
    beat_id = _safe_str(beat.get("beat_id")).strip()
    turn_id = _build_ambient_turn_id(thread_id, beat_id)

    current_scene = _safe_dict(runtime_state.get("current_scene"))
    return {
        "turn_id": turn_id,
        "tick": int(beat.get("tick", runtime_state.get("tick", 0)) or 0),
        "session_id": _safe_str(runtime_state.get("session_id")),
        "scene": current_scene,
        "narration_context": {
            "mode": "ambient_conversation",
            "beat": beat,
            "thread_id": thread_id,
            "speaker_id": _safe_str(beat.get("speaker_id")),
            "addressed_to": _safe_list(beat.get("addressed_to")),
            "summary": _safe_str(beat.get("summary")),
            "stance": _safe_str(beat.get("stance")),
            "mentions": _safe_list(beat.get("mentions")),
            "player_relevant": bool(beat.get("player_relevant")),
        },
        "performance": {
            "enable_live_narration_llm": True,
            "enable_narration_retry": False,
        },
        "job_kind": "ambient_conversation",
        "priority": 20,
    }


def _maybe_enqueue_latest_ambient_conversation_narration(
    session_id: str,
    simulation_state: dict[str, Any],
    runtime_state: dict[str, Any],
) -> dict[str, Any]:
    from app.apps.rpg.session.jobs.narration_job import enqueue_rpg_narration

    runtime_state = _ensure_ambient_narration_state(runtime_state)
    settings = _safe_dict(runtime_state.get("conversation_settings"))
    if not bool(settings.get("ambient_conversations_enabled", True)):
        return {"ok": True, "status": "disabled", "enqueued": 0}

    beats = _select_latest_ambient_conversation_beats_per_active_thread(simulation_state, runtime_state)
    if not beats:
        return {"ok": True, "status": "no_beats", "enqueued": 0}

    enqueued = 0
    results = []

    for beat in beats:
        if enqueued >= _MAX_AMBIENT_NARRATION_ENQUEUES_PER_TICK:
            break

        beat = _safe_dict(beat)
        thread_id = _safe_str(beat.get("thread_id")).strip()
        beat_tick = int(beat.get("tick", runtime_state.get("tick", 0)) or 0)

        last_tick = _get_last_ambient_narrated_tick(runtime_state, thread_id)
        if (beat_tick - last_tick) < _AMBIENT_NARRATION_THREAD_COOLDOWN_TICKS:
            continue

        request = _build_ambient_conversation_narration_request(simulation_state, runtime_state, beat)
        turn_id = _safe_str(request.get("turn_id")).strip()
        if not turn_id:
            continue

        if _has_narration_artifact_for_turn(runtime_state, turn_id):
            continue

        job = enqueue_rpg_narration(
            session_id, turn_id, request, tick=beat_tick, job_kind="ambient_conversation",
        )
        results.append({"ok": bool(job), "job": job})

        if job:
            enqueued += 1
            runtime_state = _record_ambient_narration_enqueue(runtime_state, thread_id, beat_tick, turn_id)

    return {
        "ok": True,
        "status": "processed",
        "enqueued": enqueued,
        "results": results,
        "runtime_state": runtime_state,
    }


__all__ = [
    "_AMBIENT_NARRATION_THREAD_COOLDOWN_TICKS",
    "_COMPLETED_NARRATION_ARTIFACT_SOURCES",
    "_DETERMINISTIC_NARRATION_ARTIFACT_SOURCES",
    "_MAX_AMBIENT_NARRATION_ENQUEUES_PER_TICK",
    "_build_ambient_conversation_narration_request",
    "_build_ambient_turn_id",
    "_ensure_ambient_narration_state",
    "_ensure_narration_artifact_state",
    "_get_last_ambient_narrated_tick",
    "_has_narration_artifact_for_turn",
    "_maybe_enqueue_latest_ambient_conversation_narration",
    "_narration_artifact_completes_turn",
    "_narration_artifact_has_structured_llm_content",
    "_narration_artifact_is_echo_fallback",
    "_narration_artifact_norm_text",
    "_narration_artifact_text",
    "_prune_narration_artifacts",
    "_record_ambient_narration_enqueue",
    "_select_latest_ambient_conversation_beats_per_active_thread",
    "_store_narration_artifact",
]
