from __future__ import annotations

from typing import Any, Dict, List
from app.apps.rpg.foundation.safe_values import safe_dict as _safe_dict, safe_str as _safe_str


def memory_reference_is_backed(
    line: str,
    recalled_memories: List[Dict[str, Any]],
) -> bool:
    lower = _safe_str(line).lower()
    if not lower:
        return True

    markers = (
        "remember",
        "last time",
        "again",
        "before",
        "earlier",
        "still short",
        "short on coin",
        "you bought",
        "you tried",
        "you asked",
    )
    if not any(marker in lower for marker in markers):
        return True

    if not recalled_memories:
        return False

    for memory in recalled_memories:
        memory = _safe_dict(memory)
        kind = _safe_str(memory.get("kind"))
        summary = _safe_str(memory.get("summary")).lower()
        blocked_reason = _safe_str(memory.get("blocked_reason"))

        if "short" in lower and blocked_reason == "insufficient_funds":
            return True
        if "coin" in lower and blocked_reason == "insufficient_funds":
            return True
        if "bought" in lower and kind == "service_purchase":
            return True
        if "tried" in lower and kind in {"service_purchase_blocked", "social_negative"}:
            return True
        if "asked" in lower and kind in {"service_inquiry", "social_interaction"}:
            return True
        if summary and any(token in summary for token in lower.split() if len(token) > 5):
            return True

    generic_terms = ("again", "before", "earlier", "last time", "remember")
    specific_terms = ("short", "coin", "bought", "paid", "purchased", "failed", "tried")
    if any(term in lower for term in generic_terms) and not any(term in lower for term in specific_terms):
        return bool(recalled_memories)

    return False
