from __future__ import annotations

from typing import Any

from app.rpg.session.turn_memory_common import i, s


def memory_order(item: tuple[float, dict[str, Any]]) -> tuple[float, int, str]:
    score, entry = item
    return -score, -i(entry.get("tick")), s(entry.get("id"))
