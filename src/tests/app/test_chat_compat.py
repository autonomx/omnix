from __future__ import annotations

from types import SimpleNamespace

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
