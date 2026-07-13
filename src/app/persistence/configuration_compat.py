"""PostgreSQL-backed compatibility functions for small configuration domains."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from .document_store import PostgresDocumentStore


def read_assist_pending() -> dict[str, Any]:
    value = PostgresDocumentStore().read(
        module="assist-core",
        record_type="pending-reviews",
        default={},
    )
    return dict(value or {})


def write_assist_pending(data: dict[str, Any]) -> None:
    PostgresDocumentStore().write(
        dict(data),
        module="assist-core",
        record_type="pending-reviews",
    )


def add_assist_pending(item: Any) -> None:
    data = read_assist_pending()
    data[str(item.confirmation_id)] = asdict(item)
    write_assist_pending(data)


def append_assist_action_log(entry: Any) -> None:
    payload = asdict(entry)
    record_id = str(
        payload.get("action_id")
        or payload.get("confirmation_id")
        or payload.get("id")
        or f"action:{payload.get('created_at') or payload.get('timestamp')}"
    )
    PostgresDocumentStore().write(
        payload,
        module="assist-core",
        record_type="action-log",
        record_id=record_id,
    )


def load_assistant_tools_config(path: Path | None = None):
    from app.assistant_tools.config_store import (
        AssistantToolsConfigPayload,
        _merge_known_config,
        default_assistant_tools_config,
    )

    if path is not None:
        raise RuntimeError(
            "file-backed assistant tool configuration is retired; use the legacy importer"
        )
    payload = PostgresDocumentStore().read(
        module="assistant-tools",
        record_type="configuration",
        default=None,
    )
    if payload is None:
        return default_assistant_tools_config()
    return _merge_known_config(AssistantToolsConfigPayload.model_validate(payload))


def save_assistant_tools_config(payload: Any, path: Path | None = None):
    from app.assistant_tools.config_store import _merge_known_config
    from app.assistant_tools.credentials import delete_tool_credential

    if path is not None:
        raise RuntimeError(
            "file-backed assistant tool configuration is retired; use the legacy importer"
        )
    normalized = _merge_known_config(payload)
    for tool in normalized.tools:
        if tool.connection_status != "connected":
            delete_tool_credential(tool.tool_id)
    PostgresDocumentStore().write(
        normalized.model_dump(mode="json"),
        module="assistant-tools",
        record_type="configuration",
    )
    return normalized
