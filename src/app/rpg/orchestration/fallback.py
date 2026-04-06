"""Phase 10.6 — Deterministic fallback policy helpers."""
from __future__ import annotations

from typing import Any, Dict


def _safe_dict(v: Any) -> Dict[str, Any]:
    return dict(v) if isinstance(v, dict) else {}


def _safe_str(v: Any) -> str:
    return "" if v is None else str(v)


def _safe_bool(v: Any) -> bool:
    return bool(v)


def should_allow_llm_fallback(
    request_payload: Dict[str, Any],
    *,
    provider_mode: str,
) -> bool:
    """Return whether deterministic fallback is allowed for this request.

    Policy:
        - disabled mode: allowed if request explicitly allows emotional fallback
        - replay mode: not allowed; replay must fail hard if artifact missing
        - capture/live mode: allowed only if explicitly requested
    """
    request_payload = _safe_dict(request_payload)
    constraints = _safe_dict(request_payload.get("constraints"))
    explicit = _safe_bool(constraints.get("allow_emotional_fallback"))
    provider_mode = _safe_str(provider_mode).strip().lower()

    if provider_mode == "replay":
        return False
    if provider_mode == "disabled":
        return explicit
    if provider_mode in {"capture", "live"}:
        return explicit
    return False


def build_llm_fallback_result(
    request_payload: Dict[str, Any],
    *,
    provider_mode: str,
    allow_fallback: bool,
) -> Dict[str, Any]:
    """Build a deterministic fallback execution result."""
    request_payload = _safe_dict(request_payload)
    turn = _safe_dict(request_payload.get("turn"))

    return {
        "provider_mode": _safe_str(provider_mode),
        "provider": "",
        "model": "",
        "status": "fallback" if allow_fallback else "disabled",
        "turn_id": _safe_str(turn.get("turn_id")),
        "output_text": "",
        "stream_events": [],
        "error": "" if allow_fallback else "",
        "allow_fallback": _safe_bool(allow_fallback),
    }