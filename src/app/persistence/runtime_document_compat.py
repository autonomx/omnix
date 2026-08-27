"""PostgreSQL adapters for bounded runtime documents that formerly used JSON files."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Callable, TypeVar

from .database import PostgresDatabase, default_database
from .document_store import PostgresDocumentStore
from .identity_service import bootstrap_local_tenant
from .runtime import LegacyPersistenceRetired, ensure_postgresql_runtime_ready
from .unit_of_work import unit_of_work


_LegacySessionMutationResult = TypeVar("_LegacySessionMutationResult")


class PostgresApplicationSettingsStore:
    """Compatibility facade over the canonical ``omnix_settings`` row."""

    scope = "workspace"
    key = "application.settings"

    def __init__(self, database: PostgresDatabase | None = None) -> None:
        self.database = database or default_database()
        ensure_postgresql_runtime_ready(self.database)
        self.context = bootstrap_local_tenant(self.database)

    def read(self) -> dict[str, Any]:
        with unit_of_work(self.database) as work:
            record = work.settings.get(
                self.context,
                scope=self.scope,
                key=self.key,
            )
            work.rollback()
        value = record.get("value") if record is not None else None
        return dict(value) if isinstance(value, dict) else {}

    def write(self, payload: dict[str, Any]) -> None:
        with unit_of_work(self.database) as work:
            current = work.settings.get(
                self.context,
                scope=self.scope,
                key=self.key,
            )
            work.settings.put(
                self.context,
                scope=self.scope,
                key=self.key,
                value=dict(payload),
                expected_revision=(
                    int(current["revision"]) if current is not None else None
                ),
            )
            work.commit()


def load_application_settings() -> dict[str, Any]:
    return PostgresApplicationSettingsStore().read()


def save_application_settings(payload: dict[str, Any]) -> None:
    PostgresApplicationSettingsStore().write(payload)


def load_legacy_chat_sessions() -> dict[str, Any]:
    payload = PostgresDocumentStore().read(
        module="platform",
        record_type="legacy-chat-sessions",
        default={},
    )
    return dict(payload or {})


def save_legacy_chat_sessions(payload: dict[str, Any]) -> None:
    PostgresDocumentStore().write(
        dict(payload),
        module="platform",
        record_type="legacy-chat-sessions",
    )


def mutate_legacy_chat_sessions(
    mutator: Callable[[dict[str, Any]], _LegacySessionMutationResult],
) -> tuple[dict[str, Any], _LegacySessionMutationResult]:
    """Apply one legacy-session document mutation under a PostgreSQL row lock."""

    database = default_database()
    ensure_postgresql_runtime_ready(database)
    context = bootstrap_local_tenant(database)
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO omnix_module_records (
                workspace_id, module, record_type, record_id, owner_user_id, payload
            ) VALUES (%s, 'platform', 'legacy-chat-sessions', 'default', %s, '{}'::jsonb)
            ON CONFLICT (workspace_id, module, record_type, record_id) DO NOTHING
            """,
            (context.workspace_id, context.user_id),
        )
        row = connection.execute(
            """
            SELECT payload
              FROM omnix_module_records
             WHERE workspace_id = %s AND module = 'platform'
               AND record_type = 'legacy-chat-sessions' AND record_id = 'default'
             FOR UPDATE
            """,
            (context.workspace_id,),
        ).fetchone()
        current = dict(row[0] or {}) if row is not None else {}
        result = mutator(current)
        connection.execute(
            """
            UPDATE omnix_module_records
               SET payload = %s::jsonb, status = 'active',
                   revision = revision + 1, updated_at = CURRENT_TIMESTAMP
             WHERE workspace_id = %s AND module = 'platform'
               AND record_type = 'legacy-chat-sessions' AND record_id = 'default'
            """,
            (json.dumps(current), context.workspace_id),
        )
    return current, result


def load_environment_provider_secrets() -> dict[str, Any]:
    return {
        "api_keys": {
            "openrouter": os.environ.get("OPENROUTER_API_KEY", "").strip(),
            "cerebras": os.environ.get("CEREBRAS_API_KEY", "").strip(),
        }
    }


def reject_plaintext_provider_secret_write(payload: dict[str, Any]) -> None:
    del payload
    raise LegacyPersistenceRetired(
        "plaintext provider-secret JSON is retired; configure provider keys in the "
        "process environment or an operator-owned secret provider"
    )


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


def load_assist_house_state() -> dict[str, Any]:
    from app.assist_core.house_state import DEFAULT_HOUSE_STATE

    payload = PostgresDocumentStore().read(
        module="assist-core",
        record_type="house-state",
        default=DEFAULT_HOUSE_STATE,
    )
    return dict(payload) if isinstance(payload, dict) else dict(DEFAULT_HOUSE_STATE)


def save_assist_house_state(payload: dict[str, Any]) -> None:
    PostgresDocumentStore().write(
        dict(payload),
        module="assist-core",
        record_type="house-state",
    )


class PostgresAssistantTurnCoordinator:
    """Drop-in assistant-turn coordinator backed by one PostgreSQL document."""

    def __init__(self, path: str | Path | None = None) -> None:
        if path is not None:
            raise RuntimeError(
                "file-backed assistant-turn authority is retired; use the legacy importer"
            )
        from app.chat.assistant_turns import AssistantTurnRecord

        self._record_type = AssistantTurnRecord
        self.path = Path("postgresql:/assistant-turns")
        self._lock = threading.RLock()
        self._documents = PostgresDocumentStore()
        self._records = self._load()

    def _load(self) -> dict[str, Any]:
        payload = self._documents.read(
            module="chat",
            record_type="assistant-turns",
            default=[],
        )
        records: dict[str, Any] = {}
        for item in payload if isinstance(payload, list) else []:
            try:
                record = self._record_type.model_validate(item)
            except Exception:
                continue
            records[record.assistant_turn_id] = record
        return records

    def _save(self) -> None:
        payload = [
            record.model_dump(mode="json")
            for record in sorted(self._records.values(), key=lambda item: item.created_at)
        ]
        self._documents.write(
            payload,
            module="chat",
            record_type="assistant-turns",
        )


def postgres_assistant_turn_coordinator_class() -> type:
    """Compose with the behavior class lazily to avoid a module-import cycle."""

    from app.chat.assistant_turns import AssistantTurnCoordinator

    if issubclass(AssistantTurnCoordinator, PostgresAssistantTurnCoordinator):
        return AssistantTurnCoordinator

    return type(
        "PostgresAssistantTurnCoordinator",
        (PostgresAssistantTurnCoordinator, AssistantTurnCoordinator),
        {},
    )


class PostgresAssistantMemorySettingsStore:
    def __init__(self, path: str | Path | None = None) -> None:
        if path is not None:
            raise RuntimeError(
                "file-backed assistant-memory settings are retired; use the legacy importer"
            )
        self.path = Path("postgresql:/assistant-memory-settings")
        self._documents = PostgresDocumentStore()

    def load_persisted(self):
        from app.assistant_memory.settings import AssistantMemoryRuntimeSettings

        payload = self._documents.read(
            module="assistant-memory",
            record_type="runtime-settings",
            default={},
        )
        try:
            return AssistantMemoryRuntimeSettings.model_validate(payload or {})
        except (TypeError, ValueError):
            return AssistantMemoryRuntimeSettings()

    def update(self, request):
        current = self.load_persisted()
        changes = request.model_dump(exclude_none=True)
        if changes.get("require_approval_for_inferred_memory") is False:
            raise ValueError("approval is required for inferred memory")
        changes["require_approval_for_inferred_memory"] = True
        updated = current.model_copy(update=changes)
        self._documents.write(
            updated.model_dump(mode="json"),
            module="assistant-memory",
            record_type="runtime-settings",
        )
        return self.load_effective()


def postgres_assistant_memory_settings_store_class() -> type:
    from app.assistant_memory.settings import AssistantMemorySettingsStore

    if issubclass(AssistantMemorySettingsStore, PostgresAssistantMemorySettingsStore):
        return AssistantMemorySettingsStore

    return type(
        "PostgresAssistantMemorySettingsStore",
        (PostgresAssistantMemorySettingsStore, AssistantMemorySettingsStore),
        {},
    )


class PostgresLiveConversationProfileStore:
    def __init__(self, path: Path | None = None) -> None:
        if path is not None:
            raise RuntimeError(
                "file-backed live-conversation profiles are retired; use the legacy importer"
            )
        self.path = Path("postgresql:/live-conversation-profiles")
        self._lock = threading.RLock()
        self._documents = PostgresDocumentStore()

    def _read(self) -> dict[str, Any]:
        payload = self._documents.read(
            module="live-chat",
            record_type="conversation-profiles",
            default=None,
        )
        if not isinstance(payload, dict):
            return {"format_version": 1, "defaults": {}, "sessions": {}}
        result = dict(payload)
        result.setdefault("format_version", 1)
        result.setdefault("defaults", {})
        result.setdefault("sessions", {})
        return result

    def _write(self, payload: dict[str, Any]) -> None:
        self._documents.write(
            dict(payload),
            module="live-chat",
            record_type="conversation-profiles",
        )


def postgres_live_conversation_profile_store_class() -> type:
    from app.characters.live_conversation_profile import LiveConversationProfileStore

    if issubclass(LiveConversationProfileStore, PostgresLiveConversationProfileStore):
        return LiveConversationProfileStore

    return type(
        "PostgresLiveConversationProfileStore",
        (PostgresLiveConversationProfileStore, LiveConversationProfileStore),
        {},
    )


def default_postgres_live_conversation_profile_store():
    return postgres_live_conversation_profile_store_class()()


def append_assistant_tool_ledger_entry_postgres(entry: Any, path: Path | None = None) -> Any:
    if path is not None:
        raise RuntimeError(
            "file-backed assistant-tool ledger authority is retired; use the legacy importer"
        )
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
        raise RuntimeError(
            "file-backed assistant-tool ledger authority is retired; use the legacy importer"
        )
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
