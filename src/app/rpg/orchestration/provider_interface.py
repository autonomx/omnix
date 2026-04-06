"""Phase 10.6 — Provider boundary helpers.

This module does not perform live provider calls yet. It defines explicit
provider-mode helpers and deterministic result shaping for disabled/replay
paths. Live execution will be added in later chunks through the controller.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .state import (
    ensure_llm_orchestration_state,
    get_llm_orchestration_state,
    trim_llm_orchestration_state,
)


def _safe_dict(v: Any) -> Dict[str, Any]:
    return dict(v) if isinstance(v, dict) else {}


def _safe_list(v: Any) -> List[Any]:
    return list(v) if isinstance(v, list) else []


def _safe_str(v: Any) -> str:
    return "" if v is None else str(v)


def get_llm_provider_mode(simulation_state: Dict[str, Any]) -> str:
    """Return the normalized provider mode for orchestration."""
    llm_state = get_llm_orchestration_state(simulation_state)
    return _safe_str(llm_state.get("provider_mode") or "disabled")


def set_llm_provider_mode(simulation_state: Dict[str, Any], mode: str) -> Dict[str, Any]:
    """Set provider mode deterministically on orchestration state."""
    simulation_state = ensure_llm_orchestration_state(simulation_state)
    orchestration_state = _safe_dict(simulation_state.get("orchestration_state"))
    llm_state = _safe_dict(orchestration_state.get("llm"))

    mode = _safe_str(mode).strip().lower()
    if mode not in {"disabled", "capture", "replay", "live"}:
        mode = "disabled"

    llm_state["provider_mode"] = mode
    orchestration_state["llm"] = llm_state
    simulation_state["orchestration_state"] = orchestration_state
    return trim_llm_orchestration_state(simulation_state)


def build_disabled_provider_result(request_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Build a deterministic provider result for disabled mode."""
    request_payload = _safe_dict(request_payload)
    turn = _safe_dict(request_payload.get("turn"))
    return {
        "provider_mode": "disabled",
        "provider": "",
        "model": "",
        "status": "disabled",
        "turn_id": _safe_str(turn.get("turn_id")),
        "output_text": "",
        "stream_events": [],
        "error": "",
    }


def build_replay_provider_result(request_record: Dict[str, Any]) -> Dict[str, Any]:
    """Build a deterministic provider result from a captured completed request."""
    request_record = _safe_dict(request_record)
    return {
        "provider_mode": "replay",
        "provider": _safe_str(request_record.get("provider")),
        "model": _safe_str(request_record.get("model")),
        "status": "replayed",
        "turn_id": _safe_str(request_record.get("turn_id")),
        "output_text": _safe_str(request_record.get("output_text")),
        "stream_events": [
            _safe_dict(v)
            for v in _safe_list(request_record.get("stream_events"))
            if isinstance(v, dict)
        ],
        "error": _safe_str(request_record.get("error")),
    }