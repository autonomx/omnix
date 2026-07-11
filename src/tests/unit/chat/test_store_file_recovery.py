import json

from app.chat.models import CreateChatSessionRequest
from app.chat.store import ChatSessionStore


def test_store_recovers_complete_document_with_trailing_fragment(tmp_path):
    path = tmp_path / "sessions.json"
    store = ChatSessionStore(path)
    created = store.create_session(CreateChatSessionRequest(title="Recovered chat"))
    path.write_text(path.read_text(encoding="utf-8") + 'broken": true}', encoding="utf-8")

    sessions = store.list_sessions().sessions

    assert [session.id for session in sessions] == [created.id]


def test_store_save_uses_unique_temporary_file_and_replaces_recoverable_content(tmp_path):
    path = tmp_path / "sessions.json"
    store = ChatSessionStore(path)
    created = store.create_session(CreateChatSessionRequest(title="Atomic chat"))
    path.write_text(path.read_text(encoding="utf-8") + "trailing-fragment", encoding="utf-8")

    store._save_sessions(store._load_sessions())

    assert json.loads(path.read_text(encoding="utf-8"))["sessions"][0]["id"] == created.id
    assert list(tmp_path.glob("*.tmp")) == []
