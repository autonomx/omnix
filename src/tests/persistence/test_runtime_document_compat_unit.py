from __future__ import annotations

import pytest

from app.assistant_memory.persistence import settings_store as memory_store
from app.assistant_memory.settings import AssistantMemorySettingsUpdate
from app.assistant_tools.ledger import AssistantToolLedgerEntry
from app.assistant_tools.persistence import runtime_documents as tool_documents
from app.assist_core.persistence import house_state as house_state_store
from app.characters.live_conversation_profile import LiveConversationProfileUpdate
from app.characters.persistence import live_profile_store
from app.chat.persistence import assistant_turn_store, legacy_sessions
from app.persistence.runtime import LegacyPersistenceRetired


class _Documents:
    def __init__(self) -> None:
        self.database = object()
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


def test_feature_owned_runtime_documents(monkeypatch) -> None:
    documents = _Documents()
    monkeypatch.setattr(legacy_sessions, "PostgresDocumentStore", lambda: documents)
    monkeypatch.setattr(house_state_store, "PostgresDocumentStore", lambda: documents)
    monkeypatch.setattr(assistant_turn_store, "PostgresDocumentStore", lambda: documents)
    monkeypatch.setattr(memory_store, "PostgresDocumentStore", lambda: documents)
    monkeypatch.setattr(live_profile_store, "PostgresDocumentStore", lambda: documents)
    monkeypatch.setattr(tool_documents, "PostgresDocumentStore", lambda: documents)

    legacy_sessions.save_legacy_chat_sessions({"legacy:1": {"title": "Legacy"}})
    assert legacy_sessions.load_legacy_chat_sessions() == {"legacy:1": {"title": "Legacy"}}

    house_state_store.save_house_state_postgres({"rooms": {"office": {"lights": "on"}}})
    assert house_state_store.load_house_state_postgres()["rooms"]["office"]["lights"] == "on"

    coordinator = assistant_turn_store.PostgresAssistantTurnCoordinator()
    turn = coordinator.start(
        session_id="chat:1",
        user_message_id="message:1",
        user_turn_id="turn:1",
    )
    assert coordinator.get(turn.assistant_turn_id) is not None
    assert documents.read(
        module="chat",
        record_type="assistant-turn",
        record_id=turn.assistant_turn_id,
    )

    memory = memory_store.PostgresAssistantMemorySettingsStore()
    memory.update(AssistantMemorySettingsUpdate(suggestions_enabled=True))
    assert memory.load_persisted().suggestions_enabled is True

    profiles = live_profile_store.PostgresLiveConversationProfileStore()
    profiles.update_defaults(LiveConversationProfileUpdate(talkativeness=61))
    assert profiles.get_defaults().talkativeness == 61

    entry = AssistantToolLedgerEntry(tool_id="tool:1", action_id="action:1")
    tool_documents.append_assistant_tool_ledger_entry_postgres(entry)
    ledger = tool_documents.load_assistant_tool_ledger_postgres(limit=10)
    assert [item.execution_id for item in ledger.entries] == [entry.execution_id]


def test_turn_coordinators_preserve_independent_writes_and_read_legacy_records(monkeypatch):
    from app.chat.assistant_turns import AssistantTurnRecord

    documents = _Documents()
    legacy = AssistantTurnRecord(
        assistant_turn_id="legacy",
        session_id="chat:old",
        user_message_id="msg:old",
        user_turn_id="turn:old",
    )
    documents.write(
        [legacy.model_dump(mode="json")],
        module="chat",
        record_type="assistant-turns",
    )
    monkeypatch.setattr(assistant_turn_store, "PostgresDocumentStore", lambda: documents)
    first = assistant_turn_store.PostgresAssistantTurnCoordinator()
    second = assistant_turn_store.PostgresAssistantTurnCoordinator()
    one = first.start(session_id="chat:1", user_message_id="msg:1", user_turn_id="turn:1")
    two = second.start(session_id="chat:2", user_message_id="msg:2", user_turn_id="turn:2")
    first.mark_streaming(one.assistant_turn_id)
    reloaded = assistant_turn_store.PostgresAssistantTurnCoordinator()
    assert reloaded.get(one.assistant_turn_id).lifecycle == "streaming"
    assert reloaded.get(two.assistant_turn_id) is not None
    assert reloaded.get("legacy") is not None
    assert documents.revisions[("chat", "assistant-turn", two.assistant_turn_id)] == 1


def test_assistant_tool_secret_surface_fails_closed() -> None:
    with pytest.raises(LegacyPersistenceRetired):
        tool_documents.unavailable_assistant_tool_secret(object())
