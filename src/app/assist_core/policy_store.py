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
    from app.persistence.runtime import uses_postgresql_runtime
    if uses_postgresql_runtime():
        from app.runtime_document_services import production_document_services
        return production_document_services().read_pending()
    path = pending_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_pending(data: dict[str, Any]) -> None:
    from app.persistence.runtime import uses_postgresql_runtime
    if uses_postgresql_runtime():
        from app.runtime_document_services import production_document_services
        return production_document_services().write_pending(data)
    pending_path().write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def add_pending(item: ConfirmationRequest) -> None:
    from app.persistence.runtime import uses_postgresql_runtime
    if uses_postgresql_runtime():
        from app.runtime_document_services import production_document_services
        return production_document_services().add_pending(item)
    data = read_pending()
    data[item.confirmation_id] = asdict(item)
    write_pending(data)


def append_log(entry: ActionLogEntry) -> None:
    from app.persistence.runtime import uses_postgresql_runtime
    if uses_postgresql_runtime():
        from app.runtime_document_services import production_document_services
        return production_document_services().append_log(entry)
    with log_path().open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(entry), sort_keys=True) + "\n")
