"""Phase 10.7 — Provider adapter interface.

This module defines the narrow execution boundary for live provider calls.
It supports:
    - deterministic mock execution for tests / local runs
    - explicit live execution adapter shell

It never mutates simulation truth directly.
"""
from __future__ import annotations

from typing import Any, Dict, List


def _safe_dict(v: Any) -> Dict[str, Any]:
    return dict(v) if isinstance(v, dict) else {}


def _safe_list(v: Any) -> List[Any]:
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


class BaseLLMProviderAdapter:
    """Narrow provider adapter interface."""

    def execute(self, request_payload: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError


class DeterministicMockProviderAdapter(BaseLLMProviderAdapter):
    """Deterministic provider adapter for tests and local orchestration.

    Behavior:
        - if request_payload contains mock_response.text, use it
        - else synthesize compact deterministic text from request context
        - returns structured provider result with bounded stream events
    """

    def execute(self, request_payload: Dict[str, Any]) -> Dict[str, Any]:
        request_payload = _safe_dict(request_payload)
        turn = _safe_dict(request_payload.get("turn"))
        context = _safe_dict(request_payload.get("context"))
        mock_response = _safe_dict(request_payload.get("mock_response"))

        turn_id = _safe_str(turn.get("turn_id"))
        speaker_name = _safe_str(turn.get("speaker_name"))
        emotion = _safe_str(turn.get("emotion") or "neutral")
        topic = _safe_str(context.get("topic"))

        output_text = _safe_str(mock_response.get("text"))
        if not output_text:
            parts: List[str] = []
            if speaker_name:
                parts.append(f"{speaker_name}:")
            if topic:
                parts.append(f" {topic}.")
            else:
                parts.append(" Ready.")
            if emotion and emotion != "neutral":
                parts.append(f" [{emotion}]")
            output_text = "".join(parts).strip()

        chunk_size = max(1, _safe_int(mock_response.get("chunk_size"), 24))
        stream_events: List[Dict[str, Any]] = []
        for idx, start in enumerate(range(0, len(output_text), chunk_size)):
            text = output_text[start:start + chunk_size]
            stream_events.append({
                "event_index": idx,
                "event_type": "text_chunk",
                "text": text,
                "final": (start + chunk_size) >= len(output_text),
                "raw": {},
            })

        if not stream_events:
            stream_events = [{
                "event_index": 0,
                "event_type": "text_chunk",
                "text": "",
                "final": True,
                "raw": {},
            }]

        return {
            "provider_mode": "mock",
            "provider": "deterministic_mock",
            "model": _safe_str(mock_response.get("model") or "deterministic-mock-v1"),
            "status": "complete",
            "turn_id": turn_id,
            "output_text": output_text,
            "stream_events": stream_events,
            "error": "",
        }


class LiveLLMProviderAdapter(BaseLLMProviderAdapter):
    """Explicit live provider adapter shell.

    This phase provides a strict adapter boundary only.
    Actual network/provider implementation must be added in project-specific
    code paths without changing orchestration semantics.
    """

    def execute(self, request_payload: Dict[str, Any]) -> Dict[str, Any]:
        request_payload = _safe_dict(request_payload)
        turn = _safe_dict(request_payload.get("turn"))
        raise NotImplementedError(
            f"Live provider execution not configured for turn {_safe_str(turn.get('turn_id'))}"
        )


def get_provider_adapter(provider_mode: str) -> BaseLLMProviderAdapter:
    """Return provider adapter for the requested mode."""
    provider_mode = _safe_str(provider_mode).strip().lower()
    if provider_mode == "live":
        return LiveLLMProviderAdapter()
    if provider_mode == "capture":
        return DeterministicMockProviderAdapter()
    return DeterministicMockProviderAdapter()