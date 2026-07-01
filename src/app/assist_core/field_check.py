from __future__ import annotations

from typing import Any


NEEDED = ("ok", "item_id", "summary", "review")


def check_fields(payload: dict[str, Any]) -> dict[str, Any]:
    missing = [name for name in NEEDED if name not in payload]
    return {"ok": not missing, "missing": missing}
