from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.assistant_context.models import AssistantContextChatRequest
from app.assistant_context.routes import _send_request
from app.chat import ChatSessionStore, CreateChatSessionRequest, SendChatMessageRequest


def test_assistant_context_request_carries_workspace_root() -> None:
    request = AssistantContextChatRequest(
        content="inspect the tests",
        workspace_root=r"F:\\LLM\\omnix",
        web_research_mode="quick",
    )
    forwarded = _send_request(request)
    assert forwarded.workspace_root == r"F:\\LLM\\omnix"
    assert forwarded.research_mode == "quick"


def test_assistant_context_request_carries_chat_image() -> None:
    image_data_url = "data:image/png;base64,AAAA"
    forwarded = _send_request(
        AssistantContextChatRequest(
            content="Describe this",
            image_data_url=image_data_url,
        )
    )

    assert forwarded.image_data_url == image_data_url


def test_assistant_context_request_validates_attachments_before_route_work() -> None:
    with pytest.raises(ValidationError, match="PNG, JPEG, or WebP"):
        AssistantContextChatRequest(
            content="Describe this",
            image_data_url="data:image/gif;base64,R0lGODlh",
        )

    request = AssistantContextChatRequest(
        content="Summarize this",
        text_attachment={
            "filename": "notes.md",
            "mime_type": "text/markdown",
            "text": "# Notes",
        },
    )
    assert _send_request(request).text_attachment is not None


def test_chat_turn_contract_accepts_workspace_root() -> None:
    request = SendChatMessageRequest(
        content="inspect the tests",
        workspace_root=r"F:\\LLM\\omnix",
    )
    assert request.workspace_root == r"F:\\LLM\\omnix"


def test_chat_store_persists_workspace_as_turn_metadata(tmp_path) -> None:
    store = ChatSessionStore(tmp_path / "chat.json")
    session = store.create_session(CreateChatSessionRequest(title="workspace"))
    appended = store.begin_user_message(
        session.id,
        SendChatMessageRequest(
            content="inspect the tests",
            workspace_root=r"F:\\LLM\\omnix",
        ),
    )
    assert appended is not None
    _session, message = appended
    assert message.metadata["workspace_root"] == r"F:\\LLM\\omnix"


def test_workspace_root_is_not_added_when_unselected(tmp_path) -> None:
    store = ChatSessionStore(tmp_path / "chat.json")
    session = store.create_session(CreateChatSessionRequest(title="no workspace"))
    appended = store.begin_user_message(
        session.id,
        SendChatMessageRequest(content="hello"),
    )
    assert appended is not None
    _session, message = appended
    assert "workspace_root" not in message.metadata
