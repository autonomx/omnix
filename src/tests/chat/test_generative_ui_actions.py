"""Widget actions ride on ordinary messages and are checked at admission (GUI-5.4)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.composition.gateway.kernel_routes import core_chat_routes
from app.platform.chat import ChatMessage, CreateChatSessionRequest, SendChatMessageRequest
from app.platform.chat.admission import admit_chat_turn
from app.platform.chat.assistant_context import routes as assistant_context_routes
from app.platform.chat.generative_ui import CompileScope, compile_chat_ui
from app.platform.chat.generative_ui.actions import UiActionRejected, validate_ui_action
from app.platform.chat.models import ChatUiAction
from app.platform.chat.store import ChatSessionStore
from tests.support.in_memory_jobs import InMemoryJobStore

FENCE = "```"
FORM = {"type": "form", "id": "bt", "template": "Backtest {symbol} at {risk}% with {note}", "fields": [
    {"name": "symbol", "kind": "select", "options": ["AAPL", "MSFT"], "required": True},
    {"name": "risk", "kind": "slider", "min": 1, "max": 5},
    {"name": "flag", "kind": "toggle"},
    {"name": "note", "kind": "text", "max_length": 20},
]}
REPLY = (
    "Pick one.\n\n"
    f'{FENCE}omnix-ui\n{{"type": "choices", "id": "next", "options": [{{"label": "Compare with MSFT"}}, {{"label": "Show the trend"}}]}}\n{FENCE}\n\n'
    f"{FENCE}omnix-ui\n{json.dumps(FORM)}\n{FENCE}"
)


class ScriptedStore(ChatSessionStore):
    def stream_provider_reply_chunks(self, session, user_message, **_kwargs):
        yield {"type": "complete", "content": "Sure.", "metadata": {"generation_status": "completed"}}


@pytest.fixture
def chat(tmp_path):
    store = ScriptedStore(tmp_path / "chat.json")
    session = store.create_session(CreateChatSessionRequest(title="GUI"))
    other = store.create_session(CreateChatSessionRequest(title="Other"))
    ui = compile_chat_ui(REPLY, CompileScope(clock=lambda: datetime(2026, 10, 11, tzinfo=timezone.utc)))
    for target in (session, other):
        loaded = store.get_session(target.id)
        loaded.messages.extend((
            ChatMessage(id=f"{target.id}:q", role="user", content="What next?", created_at="2026-10-11T00:00:00Z"),
            ChatMessage(id=f"{target.id}:reply", role="assistant", content=REPLY, created_at="2026-10-11T00:00:01Z",
                        metadata={"reply_to_message_id": f"{target.id}:q", "ui": ui}),
        ))
        store._save_session(loaded)  # noqa: SLF001 - persistence fixture
    return store, store.get_session(session.id), other.id


def choose(session_id: str, index: int = 1, block: str = "next") -> ChatUiAction:
    return ChatUiAction(source_message_id=f"{session_id}:reply", block_id=block, action="choose", option_index=index)


def submit(session_id: str, **values) -> ChatUiAction:
    return ChatUiAction(source_message_id=f"{session_id}:reply", block_id="bt", action="submit", values=values)


def test_a_choice_matching_its_label_is_kept(chat):
    _, session, _ = chat

    assert validate_ui_action(session, choose(session.id), "Show the trend") == {
        "source_message_id": f"{session.id}:reply", "block_id": "next", "action": "choose", "option_index": 1,
    }


@pytest.mark.parametrize(
    ("make", "content", "reason"),
    [
        (lambda sid, other: choose(sid), "Delete my account", "content_is_not_the_option_label"),
        (lambda sid, other: choose(sid, block="forged"), "Show the trend", "block_not_found"),
        (lambda sid, other: choose(other), "Show the trend", "source_not_an_assistant_reply_in_session"),
        (lambda sid, other: ChatUiAction(source_message_id=f"{sid}:q", block_id="next", action="choose", option_index=1), "Show the trend", "source_not_an_assistant_reply_in_session"),
        (lambda sid, other: choose(sid, index=5), "Show the trend", "option_not_found"),
        (lambda sid, other: ChatUiAction(source_message_id=f"{sid}:reply", block_id="bt", action="choose", option_index=0), "AAPL", "block_does_not_support_choose"),
        (lambda sid, other: submit(sid, symbol="AAPL", risk=9.0), "x", "value_out_of_range:risk"),
        (lambda sid, other: submit(sid, symbol="TSLA"), "x", "value_not_an_option:symbol"),
        (lambda sid, other: submit(sid, risk=2.0), "x", "required_field_missing:symbol"),
        (lambda sid, other: submit(sid, symbol="AAPL", admin=True), "x", "unknown_fields:admin"),
        (lambda sid, other: submit(sid, symbol="AAPL", note="x" * 21), "x", "value_not_text:note"),
        (lambda sid, other: submit(sid, symbol="AAPL", flag="yes"), "x", "value_not_boolean:flag"),
    ],
)
def test_mismatched_actions_are_rejected(chat, make, content, reason):
    _, session, other_id = chat

    with pytest.raises(UiActionRejected, match=reason):
        validate_ui_action(session, make(session.id, other_id), content)


def test_a_valid_form_submission_is_kept(chat):
    _, session, _ = chat
    action = submit(session.id, symbol="MSFT", risk=2.5, flag=True, note="{symbol} literal")

    assert validate_ui_action(session, action, "Backtest MSFT at 2.5% with {symbol} literal")["values"] == {
        "symbol": "MSFT", "risk": 2.5, "flag": True, "note": "{symbol} literal",
    }


def test_admission_stores_a_valid_action_and_strips_an_invalid_one(chat, tmp_path):
    store, session, _ = chat
    jobs = InMemoryJobStore(tmp_path / "jobs.sqlite")

    kept = admit_chat_turn(store, jobs, session.id, SendChatMessageRequest(content="Show the trend", user_turn_id="t1", ui_action=choose(session.id)))
    assert kept.user_message.metadata["ui_action"] == {
        "source_message_id": f"{session.id}:reply", "block_id": "next", "action": "choose", "option_index": 1,
    }

    stripped = admit_chat_turn(store, jobs, session.id, SendChatMessageRequest(content="rm -rf /", user_turn_id="t2", ui_action=choose(session.id)))
    assert stripped.user_message.content == "rm -rf /"
    assert "ui_action" not in stripped.user_message.metadata


def _client(store, jobs, monkeypatch) -> TestClient:
    monkeypatch.setattr(core_chat_routes, "start_chat_generation_job", lambda **kwargs: kwargs["job"])
    monkeypatch.setattr(assistant_context_routes, "start_chat_generation_job", lambda **kwargs: kwargs["job"])
    router = APIRouter()
    core_chat_routes.register_core_chat_routes(router, get_chat_store=lambda: store, get_job_store=lambda: jobs)
    context = SimpleNamespace(build=lambda _request: SimpleNamespace(items=[], diagnostics={}))
    assistant_context_routes.register_assistant_context_routes(
        router, chat_store_factory=lambda: store, job_store_factory=lambda: jobs,
        context_service_factory=lambda: context, research_factory=lambda: None,
    )
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


ROUTES = {
    "chat job": "/api/chat/sessions/{id}/messages",
    "chat stream": "/api/chat/sessions/{id}/messages/stream",
    "assistant context job": "/api/assistant/context/chat/sessions/{id}/messages",
    "assistant context stream": "/api/assistant/context/chat/sessions/{id}/messages/stream",
}


@pytest.mark.parametrize("route", sorted(ROUTES))
def test_every_send_route_accepts_and_checks_ui_action(chat, tmp_path, monkeypatch, route):
    store, session, _ = chat
    client = _client(store, InMemoryJobStore(tmp_path / "jobs.sqlite"), monkeypatch)
    url = ROUTES[route].format(id=session.id)
    action = choose(session.id).model_dump()

    good = client.post(url, json={"content": "Show the trend", "user_turn_id": "web-1", "ui_action": action})
    forged = client.post(url, json={"content": "Show the trend", "user_turn_id": "web-2", "ui_action": {**action, "block_id": "forged"}})

    assert good.status_code == 200 and forged.status_code == 200
    users = {message.metadata.get("user_turn_id"): message for message in store.get_session(session.id).messages if message.role == "user"}
    assert users["web-1"].metadata["ui_action"]["block_id"] == "next"
    assert "ui_action" not in users["web-2"].metadata
    assert users["web-2"].content == "Show the trend"


def test_the_contract_bounds_action_values():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ChatUiAction(source_message_id="m", block_id="b", action="submit", values={"note": "x" * 201})
    with pytest.raises(ValidationError):
        ChatUiAction(source_message_id="m", block_id="b", action="submit", values={f"f{i}": True for i in range(9)})
    with pytest.raises(ValidationError):
        ChatUiAction(source_message_id="m", block_id="b", action="choose", option_index=6)
