from __future__ import annotations

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
