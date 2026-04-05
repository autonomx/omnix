from __future__ import annotations

from typing import Any, Dict, List


def _safe_list(v: Any) -> List[Any]:
    return list(v) if isinstance(v, list) else []


def _safe_str(v: Any) -> str:
    return "" if v is None else str(v)


def parse_dialogue_response(payload: Dict[str, Any] | None) -> Dict[str, Any]:
    payload = dict(payload or {})

    suggested = []
    for item in _safe_list(payload.get("suggested_replies"))[:4]:
        text = _safe_str(item).strip()
        if text:
            suggested.append(text)

    reply_text = _safe_str(payload.get("reply_text")).strip()
    if not reply_text:
        reply_text = "The NPC studies you carefully before responding."

    return {
        "reply_text": reply_text,
        "tone": _safe_str(payload.get("tone")) or "neutral",
        "intent": _safe_str(payload.get("intent")) or "respond",
        "suggested_replies": suggested[:4],
    }