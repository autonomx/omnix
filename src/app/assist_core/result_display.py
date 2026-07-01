from __future__ import annotations

from typing import Any, TypedDict


class ResultDisplay(TypedDict):
    ok: bool
    item_id: str
    summary: str
    review: bool


def result_display_payload(payload: dict[str, Any]) -> ResultDisplay:
    return {
        "ok": bool(payload.get("ok")),
        "item_id": str(payload.get("item_id") or ""),
        "summary": str(payload.get("summary") or ""),
        "review": bool(payload.get("review", True)),
    }
