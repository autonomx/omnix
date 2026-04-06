"""Phase 10.6 — LLM orchestration controller.

This controller owns orchestration flow for one runtime turn:
    - begin request
    - choose disabled / replay path
    - write stream/output into runtime via adapter
    - finalize or fail orchestration request

Live provider execution is intentionally not added yet in this phase chunk.
"""
from __future__ import annotations

from typing import Any, Dict

from app.rpg.runtime.dialogue_runtime import get_runtime_dialogue_state

from .state import (
    begin_llm_request,
    append_llm_stream_event,
    finalize_llm_request,
    fail_llm_request,
    get_llm_orchestration_state,
)
from .request_builder import build_llm_request_payload
from .provider_interface import (
    get_llm_provider_mode,
    build_disabled_provider_result,
    build_replay_provider_result,
)
from .replay import require_replayable_llm_request
from .fallback import (
    should_allow_llm_fallback,
    build_llm_fallback_result,
)
from .stream_adapter import apply_provider_result_to_runtime_turn


def _safe_dict(v: Any) -> Dict[str, Any]:
    return dict(v) if isinstance(v, dict) else {}


def _safe_list(v: Any):
    return list(v) if isinstance(v, list) else []


def _safe_str(v: Any) -> str:
    return "" if v is None else str(v)


def _safe_bool(v: Any) -> bool:
    return bool(v)


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _request_id_counter(request_id: str) -> int:
    request_id = _safe_str(request_id)
    parts = request_id.split(":")
    if not parts:
        return 0
    return _safe_int(parts[-1], 0)


def _find_turn(dialogue_state: Dict[str, Any], turn_id: str) -> Dict[str, Any]:
    turn_id = _safe_str(turn_id)
    for item in _safe_list(dialogue_state.get("turns")):
        item = _safe_dict(item)
        if _safe_str(item.get("turn_id")) == turn_id:
            return item
    return {}


def _latest_active_request_id_for_turn(simulation_state: Dict[str, Any], turn_id: str) -> str:
    llm_state = get_llm_orchestration_state(simulation_state)
    active_requests = [
        _safe_dict(v)
        for v in _safe_list(llm_state.get("active_requests"))
        if isinstance(v, dict)
    ]
    matches = [
        item for item in active_requests
        if _safe_str(item.get("turn_id")) == _safe_str(turn_id)
    ]
    matches = sorted(
        matches,
        key=lambda item: (
            _safe_int(item.get("tick"), 0),
            _request_id_counter(_safe_str(item.get("request_id"))),
            _safe_str(item.get("request_id")),
        ),
    )
    if not matches:
        return ""
    return _safe_str(matches[-1].get("request_id"))


def execute_llm_request_for_turn(
    simulation_state: Dict[str, Any],
    *,
    turn_id: str,
    mode: str = "dialogue",
    scene_state: Dict[str, Any] | None = None,
    dialogue_state: Dict[str, Any] | None = None,
    personality_profile: Dict[str, Any] | None = None,
    provider: str = "",
    model: str = "",
    extra_constraints: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Execute orchestration for one runtime turn.

    Supported in this phase:
        - disabled mode
        - replay mode

    Not yet supported:
        - live provider execution
        - capture mode live call path
    """
    scene_state = _safe_dict(scene_state)
    dialogue_input_state = _safe_dict(dialogue_state)
    personality_profile = _safe_dict(personality_profile)
    extra_constraints = _safe_dict(extra_constraints)

    runtime_dialogue_state = get_runtime_dialogue_state(simulation_state)
    turn = _find_turn(runtime_dialogue_state, turn_id)
    if not turn:
        return simulation_state

    tick = _safe_int(turn.get("tick"), 0)
    sequence_index = _safe_int(turn.get("sequence_index"), 0)
    actor_id = _safe_str(turn.get("actor_id"))
    speaker_id = _safe_str(turn.get("speaker_id")) or actor_id
    sequence_id = _safe_str(turn.get("sequence_id"))

    request_payload = build_llm_request_payload(
        simulation_state,
        turn_id=turn_id,
        mode=mode,
        scene_state=scene_state,
        dialogue_state=dialogue_input_state,
        personality_profile=personality_profile,
        extra_constraints=extra_constraints,
    )

    simulation_state = begin_llm_request(
        simulation_state,
        tick=tick,
        sequence_index=sequence_index,
        actor_id=actor_id,
        turn_id=turn_id,
        sequence_id=sequence_id,
        speaker_id=speaker_id,
        mode=mode,
        provider=provider,
        model=model,
        input_payload=request_payload,
    )

    request_id = _latest_active_request_id_for_turn(simulation_state, turn_id)
    provider_mode = get_llm_provider_mode(simulation_state)
    allow_fallback = should_allow_llm_fallback(
        request_payload,
        provider_mode=provider_mode,
    )

    try:
        if provider_mode == "replay":
            replay_record = require_replayable_llm_request(
                simulation_state,
                turn_id=turn_id,
            )
            provider_result = build_replay_provider_result(replay_record)
            for event in _safe_list(provider_result.get("stream_events")):
                event = _safe_dict(event)
                simulation_state = append_llm_stream_event(
                    simulation_state,
                    request_id=request_id,
                    event_index=_safe_int(event.get("event_index"), 0),
                    event_type=_safe_str(event.get("event_type") or "text_chunk"),
                    text=_safe_str(event.get("text")),
                    final=_safe_bool(event.get("final")),
                    raw=_safe_dict(event.get("raw")),
                )
            simulation_state = apply_provider_result_to_runtime_turn(
                simulation_state,
                turn_id=turn_id,
                actor_id=actor_id,
                speaker_id=speaker_id,
                provider_result=provider_result,
                allow_emotional_fallback=False,
            )
            simulation_state = finalize_llm_request(
                simulation_state,
                request_id=request_id,
                output_text=_safe_str(provider_result.get("output_text")),
                replayed=True,
            )
            return simulation_state

        if provider_mode == "disabled":
            disabled_result = build_disabled_provider_result(request_payload)
            provider_result = build_llm_fallback_result(
                request_payload,
                provider_mode=provider_mode,
                allow_fallback=allow_fallback,
            )
            if _safe_str(provider_result.get("status")) == "disabled":
                provider_result = disabled_result
            simulation_state = apply_provider_result_to_runtime_turn(
                simulation_state,
                turn_id=turn_id,
                actor_id=actor_id,
                speaker_id=speaker_id,
                provider_result=provider_result,
                allow_emotional_fallback=allow_fallback,
            )
            if _safe_str(provider_result.get("status")) == "disabled":
                simulation_state = fail_llm_request(
                    simulation_state,
                    request_id=request_id,
                    error="Provider mode disabled and fallback not allowed",
                )
            else:
                simulation_state = finalize_llm_request(
                    simulation_state,
                    request_id=request_id,
                    output_text=_safe_str(provider_result.get("output_text")),
                    replayed=False,
                )
            return simulation_state

        raise NotImplementedError(
            f"Provider mode '{provider_mode}' is not implemented yet in Phase 10.6"
        )

    except Exception as exc:
        simulation_state = fail_llm_request(
            simulation_state,
            request_id=request_id,
            error=_safe_str(exc),
        )
        return simulation_state