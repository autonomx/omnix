from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from app.persistence import chat_compat
from app.persistence.chat_compat import PostgresChatRepositoryAdapter


def test_postgres_chat_adapter_paginates_full_message_history() -> None:
    adapter = object.__new__(PostgresChatRepositoryAdapter)
    adapter.context = object()

    first_page = [{"id": f"msg:{index}", "position": index} for index in range(500)]
    second_page = [{"id": "msg:500", "position": 500}]

    class FakeChats:
        def list_messages(self, context, session_id, *, limit: int, after_position: int):
            assert context is adapter.context
            assert session_id == "chat:test"
            assert limit == 500
            if after_position == -1:
                return first_page
            if after_position == 499:
                return second_page
            assert after_position == 500
            return []

    work = SimpleNamespace(chats=FakeChats())

    messages = adapter._list_all_messages(work, "chat:test")

    assert len(messages) == 501
    assert messages[0]["id"] == "msg:0"
    assert messages[-1]["id"] == "msg:500"


def test_postgres_chat_adapter_lists_summaries_without_loading_messages(monkeypatch) -> None:
    adapter = object.__new__(PostgresChatRepositoryAdapter)
    adapter.context = object()
    record = {
        "id": "chat:summary",
        "title": "Summary",
        "provider_id": None,
        "model_id": None,
        "workspace_id": "workspace:local",
        "profile_id": "profile:default",
        "settings": {},
        "interaction_mode": "system",
        "transcript_policy": "persistent",
        "message_count": 42,
        "created_at": "2026-09-19T00:00:00+00:00",
        "updated_at": "2026-09-19T00:01:00+00:00",
    }

    class FakeChats:
        def list_sessions(self, context, *, limit: int):
            assert context is adapter.context
            assert limit == 200
            return [record]

    work = SimpleNamespace(chats=FakeChats(), rollback=lambda: None)

    @contextmanager
    def fake_unit_of_work(database):
        del database
        yield work

    monkeypatch.setattr(chat_compat, "unit_of_work", fake_unit_of_work)
    adapter.database = object()

    summaries = adapter.load_session_summaries()

    assert len(summaries) == 1
    assert summaries[0].id == "chat:summary"
    assert summaries[0].message_count == 42


def test_postgres_chat_adapter_loads_one_session_without_scanning_other_sessions(monkeypatch) -> None:
    adapter = object.__new__(PostgresChatRepositoryAdapter)
    adapter.context = object()
    record = {
        "id": "chat:selected",
        "title": "Selected",
        "provider_id": None,
        "model_id": None,
        "workspace_id": "workspace:local",
        "profile_id": "profile:default",
        "settings": {},
        "interaction_mode": "system",
        "transcript_policy": "persistent",
        "message_count": 1,
        "created_at": "2026-09-19T00:00:00+00:00",
        "updated_at": "2026-09-19T00:01:00+00:00",
    }

    class FakeChats:
        def get_session(self, context, session_id):
            assert context is adapter.context
            assert session_id == "chat:selected"
            return record

        def list_messages(self, context, session_id, *, limit: int, after_position: int):
            assert context is adapter.context
            assert session_id == "chat:selected"
            assert limit == 500
            if after_position == -1:
                return [{
                    "id": "message:selected",
                    "position": 0,
                    "role": "user",
                    "content": "hello",
                    "created_at": "2026-09-19T00:00:00+00:00",
                    "metadata": {},
                }]
            return []

    work = SimpleNamespace(chats=FakeChats(), rollback=lambda: None)

    @contextmanager
    def fake_unit_of_work(database):
        del database
        yield work

    monkeypatch.setattr(chat_compat, "unit_of_work", fake_unit_of_work)
    adapter.database = object()

    session = adapter.load_session("chat:selected")

    assert session is not None
    assert session.id == "chat:selected"
    assert session.messages[0].content == "hello"


def test_postgres_chat_adapter_drops_redundant_legacy_image_metadata() -> None:
    image = "data:image/png;base64,AAAA"
    message = {
        "id": "message:image",
        "role": "user",
        "content": "look",
        "created_at": "2026-09-19T00:00:00+00:00",
        "metadata": {
            "image_data_urls": [image],
            "image_data_url": image,
            "user_turn_id": "turn:image",
        },
    }

    projected = PostgresChatRepositoryAdapter._message_metadata(message)

    assert projected == {
        "image_data_urls": [image],
        "user_turn_id": "turn:image",
    }
