"""PostgreSQL-backed assistant-memory runtime settings."""
from __future__ import annotations

from pathlib import Path

from app.assistant_memory.settings import (
    AssistantMemoryRuntimeSettings,
    AssistantMemorySettingsStore,
)
from app.persistence.document_store import PostgresDocumentStore


class PostgresAssistantMemorySettingsStore(AssistantMemorySettingsStore):
    def __init__(self, path: str | Path | None = None) -> None:
        if path is not None:
            raise RuntimeError("file-backed assistant-memory settings are retired")
        self.path = Path("postgresql:/assistant-memory-settings")
        self._documents = PostgresDocumentStore()

    def load_persisted(self) -> AssistantMemoryRuntimeSettings:
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
