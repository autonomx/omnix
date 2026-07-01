from __future__ import annotations

from typing import TypedDict


class ResultShape(TypedDict):
    ok: bool
    item_id: str
    summary: str
    review: bool
    allowed: bool


def result_shape_payload(item_id: str, summary: str) -> ResultShape:
    return {
        "ok": True,
        "item_id": item_id.strip(),
        "summary": summary.strip(),
        "review": True,
        "allowed": False,
    }
