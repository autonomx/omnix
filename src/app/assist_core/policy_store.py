from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .core import ActionLogEntry, ConfirmationRequest
from .house_state import assist_data_root


def pending_path() -> Path:
    return assist_data_root() / "pending_reviews.json"


def log_path() -> Path:
    return assist_data_root() / "action_log.jsonl"


def read_pending() -> dict[str, Any]:
    path = pending_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_pending(data: dict[str, Any]) -> None:
    pending_path().write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def add_pending(item: ConfirmationRequest) -> None:
    data = read_pending()
    data[item.confirmation_id] = asdict(item)
    write_pending(data)


def append_log(entry: ActionLogEntry) -> None:
    with log_path().open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(entry), sort_keys=True) + "\n")
