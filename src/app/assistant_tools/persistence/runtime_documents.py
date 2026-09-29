"""PostgreSQL document adapters owned by Assistant Tools."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.persistence.document_store import PostgresDocumentStore
from app.errors import LegacyPersistenceRetired


def load_empty_assistant_tool_credentials(path: Path | None = None):
    if path is not None:
        raise LegacyPersistenceRetired("plaintext assistant-tool credential JSON is retired")
    from app.assistant_tools.credentials import AssistantToolCredentialsPayload
    return AssistantToolCredentialsPayload()


def load_empty_assistant_tool_oauth_clients(path: Path | None = None):
    if path is not None:
        raise LegacyPersistenceRetired("plaintext assistant-tool OAuth client JSON is retired")
    from app.assistant_tools.credentials import AssistantToolOAuthClientsPayload
    return AssistantToolOAuthClientsPayload()


def unavailable_assistant_tool_secret(*args: Any, **kwargs: Any):
    del args, kwargs
    raise LegacyPersistenceRetired(
        "assistant-tool credential persistence requires an encrypted or OS credential store"
    )


def no_assistant_tool_credential(*args: Any, **kwargs: Any) -> None:
    del args, kwargs
    return None


def append_assistant_tool_ledger_entry_postgres(entry: Any, path: Path | None = None) -> Any:
    if path is not None:
        raise RuntimeError("file-backed assistant-tool ledger authority is retired")
    PostgresDocumentStore().write(
        entry.model_dump(mode="json"),
        module="assistant-tools",
        record_type="execution-ledger",
        record_id=str(entry.execution_id),
    )
    return entry


def load_assistant_tool_ledger_postgres(
    path: Path | None = None,
    *,
    limit: int = 100,
):
    if path is not None:
        raise RuntimeError("file-backed assistant-tool ledger authority is retired")
    from app.assistant_tools.ledger import AssistantToolLedgerEntry, AssistantToolLedgerPayload

    entries = []
    for _, payload, _ in PostgresDocumentStore().list(
        module="assistant-tools",
        record_type="execution-ledger",
        limit=max(1, int(limit)),
    ):
        try:
            entries.append(AssistantToolLedgerEntry.model_validate(payload))
        except (TypeError, ValueError):
            continue
    entries.sort(key=lambda item: item.created_at, reverse=True)
    return AssistantToolLedgerPayload(entries=entries[: max(1, int(limit))])
