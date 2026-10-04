from __future__ import annotations

from app.assistant_tools.ledger import AssistantToolLedgerEntry
from app.assistant_tools.persistence import runtime_documents as tool_documents
from app.chat.assist import house as house_state_store
from app.characters.live_conversation_profile import LiveConversationProfileUpdate
from app.characters.persistence import live_profile_store
from app.chat.persistence import assistant_turn_store, legacy_sessions


class _Lock:
    """In-process stand-in for DocumentLock."""

    def __init__(self, documents, key) -> None:
        self.documents, self.key, self.depth = documents, key, 0

    def __enter__(self):
        self.depth += 1
        return self

    def __exit__(self, *exc_info) -> None:
        self.depth -= 1

    @property
    def held(self) -> bool:
        return self.depth > 0

    def read(self, *, default=None):
        return self.documents.values.get(self.key, default)

    def write(self, payload) -> None:
        self.documents.values[self.key] = payload
        self.documents.revisions[self.key] = self.documents.revisions.get(self.key, 0) + 1


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

    def lock(self, *, module, record_type, record_id="default"):
        return _Lock(self, (module, record_type, record_id))

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


def test_assistant_tool_secrets_are_not_document_services() -> None:
    # Credentials live in the secret store (WP-4.9), not in PostgreSQL documents.
    assert not hasattr(tool_documents, "unavailable_assistant_tool_secret")
