"""Phase 10.7 — Capture persistence helpers.

These helpers persist live/capture provider outputs back into completed LLM
request artifacts so replay mode can consume the exact same structured result.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .state import (
    get_llm_orchestration_state,
    trim_llm_orchestration_state,
)


def _safe_dict(v: Any) -> Dict[str, Any]:
    return dict(v) if isinstance(v, dict) else {}


def _safe_list(v: Any) -> List[Any]:
    return list(v) if isinstance(v, list) else []


def _safe_str(v: Any) -> str:
    return "" if v is None else str(v)


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _find_completed_request_index(completed_requests: List[Dict[str, Any]], request_id: str) -> int:
    request_id = _safe_str(request_id)
    for idx, item in enumerate(completed_requests):
        if _safe_str(_safe_dict(item).get("request_id")) == request_id:
            return idx
    return -1


def persist_captured_provider_result(
    simulation_state: Dict[str, Any],
    *,
    request_id: str,
    provider_result: Dict[str, Any],
    provider: str,
    model: str,
) -> Dict[str, Any]:
    """Persist provider result into completed orchestration request artifact.

    This keeps replay-mode inputs identical to what live/capture execution saw.
    """
    simulation_state = trim_llm_orchestration_state(simulation_state)
    llm_state = get_llm_orchestration_state(simulation_state)

    request_id = _safe_str(request_id)
    provider_result = _safe_dict(provider_result)
    provider = _safe_str(provider)
    model = _safe_str(model)
    if not request_id:
        return simulation_state

    completed_requests = [
        _safe_dict(v)
        for v in _safe_list(llm_state.get("completed_requests"))
        if isinstance(v, dict)
    ]
    idx = _find_completed_request_index(completed_requests, request_id)
    if idx < 0:
        return simulation_state

    request = _safe_dict(completed_requests[idx])
    request["provider"] = provider or _safe_str(provider_result.get("provider"))
    request["model"] = model or _safe_str(provider_result.get("model"))
    request["output_text"] = _safe_str(provider_result.get("output_text"))
    request["stream_events"] = [
        _safe_dict(v)
        for v in _safe_list(provider_result.get("stream_events"))
        if isinstance(v, dict)
    ]
    request["error"] = _safe_str(provider_result.get("error"))

    completed_requests[idx] = request
    llm_state["completed_requests"] = completed_requests
    simulation_state["orchestration_state"]["llm"] = llm_state
    return trim_llm_orchestration_state(simulation_state)