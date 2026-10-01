from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from app.chat.persistence import chat_compat
from app.chat.persistence.chat_compat import PostgresChatRepositoryAdapter


def test_postgres_chat_adapter_paginates_full_message_history() -> None:
    adapter = object.__new__(PostgresChatRepositoryAdapter)
    adapter.context = object()

    page_size = chat_compat._MESSAGE_PAGE_SIZE
    first_page = [{"id": f"msg:{index}", "position": index} for index in range(page_size)]
    second_page = [{"id": f"msg:{page_size}", "position": page_size}]

    class FakeChats:
        def list_messages(self, context, session_id, *, limit: int, after_position: int):
            assert context is adapter.context
            assert session_id == "chat:test"
            assert limit == page_size
            if after_position == -1:
                return first_page
            if after_position == page_size - 1:
                return second_page
            assert after_position == page_size
            return []

    work = SimpleNamespace(chats=FakeChats())

    messages = adapter._list_all_messages(work, "chat:test")

    assert len(messages) == page_size + 1
    assert messages[0]["id"] == "msg:0"
    assert messages[-1]["id"] == f"msg:{page_size}"


def test_postgres_chat_adapter_lists_summaries_without_loading_messages(monkeypatch) -> None:
    adapter = object.__new__(PostgresChatRepositoryAdapter)
    adapter.database = object()
    adapter.context = object()
    record = {
        "id": "chat:test",
        "title": "Test chat",
        "workspace_id": "workspace:local",
        "profile_id": "profile:default",
        "interaction_mode": "system",
        "message_count": 37,
        "created_at": "2026-09-21T00:00:00+00:00",
        "updated_at": "2026-09-21T01:00:00+00:00",
        "settings": {},
    }

    class FakeChats:
        def list_sessions(self, context, *, limit: int, **_cursor):
            assert context is adapter.context
            assert limit == 101  # one page of 100 plus a has-more probe
            return [record]

        def list_messages(self, *_args, **_kwargs):
            raise AssertionError("session listing must not load transcripts")

    class FakeWork:
        chats = FakeChats()

        def rollback(self):
            return None

    @contextmanager
    def fake_unit_of_work(database):
        assert database is adapter.database
        yield FakeWork()

    monkeypatch.setattr(chat_compat, "unit_of_work", fake_unit_of_work)

    summaries, next_cursor = adapter.list_session_summaries()

    assert next_cursor is None
    assert len(summaries) == 1
    assert summaries[0].id == "chat:test"
    assert summaries[0].message_count == 37


def test_postgres_chat_adapter_gets_only_the_requested_transcript(monkeypatch) -> None:
    adapter = object.__new__(PostgresChatRepositoryAdapter)
    adapter.database = object()
    adapter.context = object()
    record = {
        "id": "chat:test",
        "title": "Test chat",
        "workspace_id": "workspace:local",
        "profile_id": "profile:default",
        "interaction_mode": "system",
        "message_count": 1,
        "created_at": "2026-09-21T00:00:00+00:00",
        "updated_at": "2026-09-21T01:00:00+00:00",
        "settings": {},
    }
    message = {
        "id": "msg:test",
        "position": 0,
        "role": "user",
        "content": "hello",
        "created_at": "2026-09-21T01:00:00+00:00",
        "metadata": {},
    }

    class FakeChats:
        def get_session(self, context, session_id):
            assert context is adapter.context
            assert session_id == "chat:test"
            return record

        def list_sessions(self, *_args, **_kwargs):
            raise AssertionError("point lookup must not list the workspace")

        def list_messages(self, context, session_id, *, limit: int, after_position: int):
            assert context is adapter.context
            assert session_id == "chat:test"
            assert limit == chat_compat._MESSAGE_PAGE_SIZE
            return [message] if after_position == -1 else []

    class FakeWork:
        chats = FakeChats()

        def rollback(self):
            return None

    @contextmanager
    def fake_unit_of_work(database):
        assert database is adapter.database
        yield FakeWork()

    monkeypatch.setattr(chat_compat, "unit_of_work", fake_unit_of_work)

    session = adapter.get_session("chat:test")

    assert session is not None
    assert session.id == "chat:test"
    assert [item.content for item in session.messages] == ["hello"]
