from __future__ import annotations

import json
from typing import Any

from .house_state import assist_data_root


def history_notes_path():
    return assist_data_root() / "action_log.jsonl"


def read_history_notes(limit: int = 50) -> list[dict[str, Any]]:
    path = history_notes_path()
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows[-max(0, limit):]


def history_notes_summary(limit: int = 20) -> dict[str, Any]:
    rows = read_history_notes(limit=limit)
    return {"count": len(rows), "entries": rows}
