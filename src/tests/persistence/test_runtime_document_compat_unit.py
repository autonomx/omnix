from __future__ import annotations

import pytest

from app.assistant_memory.settings import AssistantMemorySettingsUpdate
from app.assistant_tools.ledger import AssistantToolLedgerEntry
from app.characters.live_conversation_profile import LiveConversationProfileUpdate
from app.persistence import runtime_document_compat as compat
from app.persistence.runtime import LegacyPersistenceRetired


class _Documents:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str, str], object] = {}
        self.revisions: dict[tuple[str, str, str], int] = {}

    def read(self, *, module, record_type, record_id="default", default=None):
        return self.values.get((module, record_type, record_id), default)

    def write(
        self,
        payload,
        *,
        module,
        record_type,
        record_id="default",
        status="active",
        expires_at=None,
    ):
        del status, expires_at
        key = (module, record_type, record_id)
        self.values[key] = payload
        self.revisions[key] = self.revisions.get(key, 0) + 1
        return self.revisions[key]

    def list(self, *, module, record_type, limit=500):
        rows = [
            (record_id, payload, self.revisions[(stored_module, stored_type, record_id)])
            for (stored_module, stored_type, record_id), payload in self.values.items()
            if stored_module == module and stored_type == record_type
        ]
        return rows[:limit]


def test_bounded_runtime_documents_use_postgresql_facade(monkeypatch) -> None:
    documents = _Documents()
    monkeypatch.setattr(compat, "PostgresDocumentStore", lambda: documents)
    monkeypatch.setattr(
        compat,
        "PostgresApplicationSettingsStore",
        lambda: _ApplicationSettings(documents),
    )

    compat.save_application_settings({"provider": "lmstudio"})
    compat.save_legacy_chat_sessions({"legacy:1": {"title": "Legacy"}})
    assert compat.load_application_settings() == {"provider": "lmstudio"}
    assert compat.load_legacy_chat_sessions() == {"legacy:1": {"title": "Legacy"}}

    compat.save_assist_house_state({"rooms": {"office": {"lights": "on"}}})
    assert compat.load_assist_house_state()["rooms"]["office"]["lights"] == "on"

    coordinator_type = compat.postgres_assistant_turn_coordinator_class()
    coordinator = coordinator_type()
    turn = coordinator.start(
        session_id="chat:1",
        user_message_id="message:1",
        user_turn_id="turn:1",
    )
    assert coordinator.get(turn.assistant_turn_id) is not None
    assert documents.read(module="chat", record_type="assistant-turns")

    memory_type = compat.postgres_assistant_memory_settings_store_class()
    memory = memory_type()
    memory.update(AssistantMemorySettingsUpdate(suggestions_enabled=True))
    assert memory.load_persisted().suggestions_enabled is True

    profile_type = compat.postgres_live_conversation_profile_store_class()
    profiles = profile_type()
    profiles.update_defaults(LiveConversationProfileUpdate(talkativeness=61))
    assert profiles.get_defaults().talkativeness == 61

    entry = AssistantToolLedgerEntry(tool_id="tool:1", action_id="action:1")
    compat.append_assistant_tool_ledger_entry_postgres(entry)
    ledger = compat.load_assistant_tool_ledger_postgres(limit=10)
    assert [item.execution_id for item in ledger.entries] == [entry.execution_id]


def test_postgresql_secret_surfaces_use_environment_or_fail_closed(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "environment-openrouter")
    monkeypatch.setenv("CEREBRAS_API_KEY", "environment-cerebras")
    assert compat.load_environment_provider_secrets() == {
        "api_keys": {
            "openrouter": "environment-openrouter",
            "cerebras": "environment-cerebras",
        }
    }
    with pytest.raises(LegacyPersistenceRetired):
        compat.reject_plaintext_provider_secret_write({"api_keys": {"openrouter": "x"}})
    with pytest.raises(LegacyPersistenceRetired):
        compat.unavailable_assistant_tool_secret(object())


class _ApplicationSettings:
    def __init__(self, documents: _Documents) -> None:
        self.documents = documents

    def read(self):
        return self.documents.read(
            module="settings",
            record_type="application",
            default={},
        )

    def write(self, payload):
        self.documents.write(
            payload,
            module="settings",
            record_type="application",
        )
