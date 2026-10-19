"""Projections of replies with generative UI (GUI-1.5, roadmap §6.4)."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.platform.chat import ChatMessage, ChatSession
from app.platform.chat.generative_ui import CompileScope, compile_chat_ui
from app.platform.chat.models import MessageContentPurpose, project_message_content
from app.platform.chat.prompt_assembly import build_prompt_assembly
from app.platform.chat.prompt_rendering import render_prompt_assembly
from app.platform.chat.store import ChatSessionStore as JsonChatSessionStore

NOW = "2026-10-11T00:00:00+00:00"
FENCE = "```"
CONTENT = f'Revenue held.\n\n{FENCE}omnix-ui\n{{"type": "stats", "items": [{{"label": "Revenue", "value": "$6,930"}}]}}\n{FENCE}'
UI = compile_chat_ui(CONTENT, CompileScope(clock=lambda: datetime(2026, 10, 11, tzinfo=timezone.utc)))


def reply(metadata: dict | None = None, content: str = CONTENT) -> ChatMessage:
    return ChatMessage(id="msg:reply", role="assistant", content=content, created_at=NOW, metadata=metadata or {})


@pytest.mark.parametrize(
    ("purpose", "expected"),
    [
        (MessageContentPurpose.MODEL_RICH, CONTENT),
        (MessageContentPurpose.MODEL, "Revenue held.\n\nRevenue: $6,930."),
        (MessageContentPurpose.MEMORY, "Revenue held.\n\nRevenue: $6,930."),
        (MessageContentPurpose.SUMMARY, "Revenue held.\n\nRevenue: $6,930."),
        (MessageContentPurpose.SEARCH, "Revenue held.\n\nRevenue: $6,930."),
        (MessageContentPurpose.TRANSCRIPT, "Revenue held.\n\nRevenue: $6,930."),
        (MessageContentPurpose.AUDIT, CONTENT),
        (MessageContentPurpose.EXPORT, CONTENT),
    ],
)
def test_purpose_matrix_with_ui(purpose, expected):
    assert project_message_content(reply({"ui": UI}), purpose) == expected


@pytest.mark.parametrize("purpose", list(MessageContentPurpose))
def test_without_ui_every_purpose_sees_the_content(purpose):
    assert project_message_content(reply(), purpose) == CONTENT
    user = ChatMessage(id="msg:user", role="user", content=CONTENT, created_at=NOW, metadata={"ui": UI})
    assert project_message_content(user, purpose) == CONTENT


def test_interrupted_delivery_keeps_its_own_projection_and_ignores_ui():
    message = reply({"ui": UI, "delivery_status": "interrupted", "context_delivered_text_end": 13, "visual_delivered_text_end": 13})

    assert project_message_content(message, MessageContentPurpose.MODEL) == "Revenue held."
    assert project_message_content(message, MessageContentPurpose.MODEL_RICH) == "Revenue held."
    assert project_message_content(message, MessageContentPurpose.TRANSCRIPT) == "Revenue held.\n\n[Response interrupted]"
    assert project_message_content(message, MessageContentPurpose.AUDIT) == CONTENT


def test_prompt_history_with_a_prior_fenced_reply_holds_its_text_not_the_fence():
    session = ChatSession(
        id="chat:gui", title="GUI", created_at=NOW, updated_at=NOW, message_count=3,
        messages=[
            ChatMessage(id="msg:q", role="user", content="How was the quarter?", created_at=NOW),
            reply({"ui": UI}),
        ],
    )
    current = ChatMessage(id="msg:current", role="user", content="And orders?", created_at=NOW)
    rendered = render_prompt_assembly(build_prompt_assembly(session, current, global_system_prompt="System"))
    prompt = "\n".join(message.content for message in rendered.messages)

    assert "Revenue: $6,930." in prompt
    assert "omnix-ui" not in prompt

    legacy = JsonChatSessionStore()._provider_messages(session, current, [])
    assert all("omnix-ui" not in message.content for message in legacy)
    assert any(message.content == "Revenue held.\n\nRevenue: $6,930." for message in legacy)


def test_memory_reads_only_prose_and_block_text():
    projected = project_message_content(reply({"ui": UI}), MessageContentPurpose.MEMORY)

    assert projected == "Revenue held.\n\nRevenue: $6,930."
    assert "{" not in projected


def test_postgres_history_search_recalls_replies_as_their_text():
    from app.platform.chat.persistence.chat_runtime import PostgresHistorySearchService

    created = datetime(2026, 10, 11, tzinfo=timezone.utc)
    rows = [("msg:reply", "chat:other", "assistant", CONTENT, created, {"ui": UI})]

    class Connection:
        def execute(self, _sql, _params):
            return SimpleNamespace(fetchall=lambda: rows)

    class Database:
        @contextmanager
        def connection(self):
            yield Connection()

    service = PostgresHistorySearchService.__new__(PostgresHistorySearchService)
    service.database = Database()
    service.context = SimpleNamespace(workspace_id="workspace:default")
    result = service.search("revenue", profile_id="profile:default", workspace_id="workspace:default", project_id=None)

    assert [item.content for item in result.items] == ["Revenue held.\n\nRevenue: $6,930."]
