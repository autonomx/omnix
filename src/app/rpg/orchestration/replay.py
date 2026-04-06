"""Phase 10.6 — Replay helpers for captured LLM orchestration artifacts."""
from __future__ import annotations

from typing import Any, Dict, List

from .state import get_llm_orchestration_state


def _safe_dict(v: Any) -> Dict[str, Any]:
    return dict(v) if isinstance(v, dict) else {}


def _safe_list(v: Any) -> List[Any]:
    return list(v) if isinstance(v, list) else []


def _safe_str(v: Any) -> str:
    return "" if v is None else str(v)


def find_replayable_llm_request(
    simulation_state: Dict[str, Any],
    *,
    request_id: str = "",
    turn_id: str = "",
) -> Dict[str, Any]:
    """Find a captured completed request that can be replayed.

    Search preference:
        1. exact request_id
        2. exact turn_id
    """
    llm_state = get_llm_orchestration_state(simulation_state)
    completed_requests = [
        _safe_dict(v)
        for v in _safe_list(llm_state.get("completed_requests"))
        if isinstance(v, dict)
    ]

    request_id = _safe_str(request_id)
    turn_id = _safe_str(turn_id)

    if request_id:
        for item in completed_requests:
            if _safe_str(item.get("request_id")) == request_id and _safe_str(item.get("status")) in {"complete", "replayed", "failed"}:
                return item

    if turn_id:
        matches = [
            item for item in completed_requests
            if _safe_str(item.get("turn_id")) == turn_id
            and _safe_str(item.get("status")) in {"complete", "replayed", "failed"}
        ]
        matches = sorted(
            matches,
            key=lambda item: (
                _safe_str(item.get("request_id")),
                _safe_str(item.get("status")),
            ),
        )
        if matches:
            return matches[-1]

    return {}


def require_replayable_llm_request(
    simulation_state: Dict[str, Any],
    *,
    request_id: str = "",
    turn_id: str = "",
) -> Dict[str, Any]:
    """Return replayable request or raise a deterministic replay error."""
    item = find_replayable_llm_request(
        simulation_state,
        request_id=request_id,
        turn_id=turn_id,
    )
    if item:
        return item

    wanted = _safe_str(request_id or turn_id)
    raise ValueError(f"Missing replay artifact for {wanted}")