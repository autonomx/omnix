"""Call recap (D3): one message after a call, from the call's committed lines, checked and formatted by code."""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from app.platform.chat import live_call_recap
from app.platform.chat.live_call_recap import CallRecapResponse, call_messages, recap_document, validated_recap
from app.platform.chat.models import ChatMessage

START = datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc)
END = START + timedelta(minutes=5)


def _at(seconds: float) -> str:
    return (START + timedelta(seconds=seconds)).isoformat()


def _spoken(index: int, text: str, at: float) -> ChatMessage:
    return ChatMessage(id=f"msg:said:{index}", role="user", content=text, created_at=_at(at),
                       metadata={"speech_segment_id": f"voice-segment:{index}"})


def _reply(index: int, text: str, at: float, **metadata: Any) -> ChatMessage:
    return ChatMessage(id=f"msg:reply:{index}", role="assistant", content=text, created_at=_at(at), metadata=metadata)


def _call() -> list[ChatMessage]:
    return [
        ChatMessage(id="msg:before", role="user", content="Typed long before the call.", created_at=_at(-3600)),
        _reply(0, "Hi! Good to hear you.", 1),  # the greeting: before their first spoken turn
        _spoken(1, "Let's plan Saturday's hike.", 5),
        _reply(1, "The ridge trail, then. Start at nine?", 8),
        _spoken(2, "Yes, nine. Remind me Friday night.", 15),
        ChatMessage(id="msg:typed", role="user", content="typed beside the call", created_at=_at(20)),
        _reply(2, "Reminder set for Friday at eight in the evening. [laughs] And I will check the weather too.", 22,
               delivery_status="interrupted", context_delivered_text_end=len("Reminder set for Friday at eight in "
                                                                             "the evening.")),
        _spoken(3, "Who else is coming?", 30),
        _reply(3, "Sam said maybe; you wanted to ask Jo.", 33),
    ]


def test_the_call_lines_are_its_spoken_turns_and_what_answered_them():
    lines = call_messages(SimpleNamespace(messages=_call()), START, END)

    assert [message.id for message in lines] == [
        "msg:said:1", "msg:reply:1", "msg:said:2", "msg:reply:2", "msg:said:3", "msg:reply:3",
    ]
    said = recap_document(lines)["lines"]
    assert said[0] == {"speaker": "person", "said": "Let's plan Saturday's hike."}
    # An interrupted reply is what they heard of it, with no sound tags.
    assert said[3]["said"] == "Reminder set for Friday at eight in the evening."


def test_a_recap_already_written_ends_the_lines_before_it():
    messages = _call()
    messages.insert(5, _reply(9, "**Call recap**", 16, kind="call_recap"))
    lines = call_messages(SimpleNamespace(messages=messages), START, END)

    # The reply after it answered a turn the recap already covered; the next lines start at their next turn.
    assert [message.id for message in lines] == ["msg:said:3", "msg:reply:3"]


def test_the_lists_are_checked_and_trimmed_by_code():
    recap = validated_recap(CallRecapResponse(
        decided=["- Hike Saturday at nine.", "hike saturday at nine.", "  ", "x " * 200],
        started=[f"Task {index}" for index in range(8)],
    ))

    assert recap["decided"][0] == "Hike Saturday at nine."
    assert len(recap["decided"]) == 2 and len(recap["decided"][1]) <= live_call_recap.ITEM_CHARS + 2
    assert recap["started"] == [f"Task {index}" for index in range(5)]
    assert recap["follow_up"] == []
    text = live_call_recap.recap_text(recap)
    assert text.startswith("**Call recap**") and "Decided:\n- Hike Saturday at nine." in text
    assert "To follow up" not in text


class _Chat:
    def __init__(self, messages: list[ChatMessage]) -> None:
        self.session = SimpleNamespace(id="chat:1", messages=messages, provider_id="lmstudio", model_id="qwen")
        self.appended: list[tuple[str, dict[str, Any]]] = []

    def get_session(self, session_id: str) -> Any:
        return self.session if session_id == "chat:1" else None

    def append_assistant_message(self, session_id: str, content: str, metadata: dict[str, Any]) -> Any:
        self.appended.append((content, metadata))
        return self.session, SimpleNamespace(id="msg:recap"), False


@pytest.fixture
def jobs(tmp_path):
    from tests.support.in_memory_jobs import InMemoryJobStore

    return InMemoryJobStore(tmp_path / "jobs")


def _job(jobs: Any) -> Any:
    from app.jobs.models import CreateJobRequest, ResourceClass

    payload = live_call_recap.LiveCallRecapInput(session_id="chat:1", call_started_at=START, requested_at=END)
    return jobs.create_job_once(CreateJobRequest(
        owner_id="chat:1", module="chat", type=live_call_recap.JOB_TYPE, resource_class=ResourceClass.NETWORK,
        input_payload=payload.model_dump(mode="json"),
    ), idempotency_key="call-recap:test")


def test_the_job_writes_one_recap_message_from_the_model_lists(jobs):
    chat = _Chat(_call())
    seen: list[dict[str, Any]] = []

    def ask(session, document):
        seen.append(document)
        return CallRecapResponse(decided=["Hike Saturday at nine."], started=["A reminder for Friday evening."],
                                 follow_up=["Ask Jo whether they are coming."])

    done = live_call_recap.execute_call_recap(jobs, _job(jobs), chat_store=chat, ask=ask)

    assert done.status.value == "completed"
    assert len(seen[0]["lines"]) == 6
    content, metadata = chat.appended[0]
    assert "Started:\n- A reminder for Friday evening." in content
    assert metadata["kind"] == "call_recap" and metadata["recap_through_message_id"] == "msg:reply:3"
    assert metadata["call_recap"]["follow_up"] == ["Ask Jo whether they are coming."]
    assert metadata["turn_id"] == f"call-recap:{START.isoformat()}"


@pytest.mark.parametrize("case", ["nothing_to_recap", "too_short"])
def test_nothing_is_written_when_there_is_nothing_to_recap(jobs, case):
    messages = _call() if case == "nothing_to_recap" else _call()[:5]
    chat = _Chat(messages)
    done = live_call_recap.execute_call_recap(jobs, _job(jobs), chat_store=chat,
                                              ask=lambda session, document: CallRecapResponse())

    assert done.status.value == "completed" and chat.appended == []


def test_a_model_that_cannot_answer_fails_the_job_and_writes_nothing(jobs):
    def ask(session, document):
        raise live_call_recap._RecapFailed("call_recap_unreadable")

    chat = _Chat(_call())
    done = live_call_recap.execute_call_recap(jobs, _job(jobs), chat_store=chat, ask=ask)

    assert done.status.value == "failed" and chat.appended == []


def test_the_route_starts_one_recap_per_call_and_says_when_a_call_was_too_short(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.composition.gateway.main import create_gateway_app
    from app.persistence.runtime import reset_persistence_mode_cache
    from app.platform.chat.character_store import InMemoryChatSessionStore
    from tests.support.in_memory_jobs import InMemoryJobStore

    monkeypatch.setenv("OMNIX_PERSISTENCE_MODE", "legacy_test")
    monkeypatch.setenv("OMNIX_ALLOW_LEGACY_TEST_PERSISTENCE", "1")
    monkeypatch.setenv("OMNIX_CHARACTER_DB_PATH", str(tmp_path / "characters.sqlite3"))
    monkeypatch.setenv("OMNIX_CHAT_STORE_PATH", str(tmp_path / "chat.json"))
    reset_persistence_mode_cache()
    monkeypatch.setattr(live_call_recap, "_ask_model", lambda session, document: CallRecapResponse(
        decided=["Hike Saturday at nine."]))
    written = threading.Event()
    execute = live_call_recap.execute_call_recap

    def execute_and_tell(*args, **kwargs):
        try:
            return execute(*args, **kwargs)
        finally:
            written.set()

    monkeypatch.setattr(live_call_recap, "execute_call_recap", execute_and_tell)
    chat_store = InMemoryChatSessionStore()
    job_store = InMemoryJobStore(tmp_path / "jobs")
    client = TestClient(
        create_gateway_app(chat_store_factory=lambda: chat_store, job_store_factory=lambda: job_store),
        base_url="http://localhost", headers={"X-Omnix-Client": "web"},
    )
    session_id = client.post("/api/chat/sessions", json={"title": "Call"}).json()["id"]
    path = f"/api/chat/sessions/{session_id}/live-call/recap"
    now = datetime.now(timezone.utc)
    call_started = (now - timedelta(minutes=2)).isoformat()

    assert client.post(path, json={"call_started_at": call_started}).json() == {"status": "too_short", "job_id": None}

    session = chat_store.get_session(session_id)
    for index in range(1, 4):
        at = (now - timedelta(seconds=90 - index * 10)).isoformat()
        session.messages.append(ChatMessage(id=f"msg:said:{index}", role="user", content=f"Line {index}",
                                            created_at=at, metadata={"speech_segment_id": f"voice-segment:{index}"}))
        session.messages.append(ChatMessage(id=f"msg:reply:{index}", role="assistant", content=f"Reply {index}",
                                            created_at=at))
    chat_store._save_session(session)

    first = client.post(path, json={"call_started_at": call_started}).json()
    again = client.post(path, json={"call_started_at": call_started}).json()
    assert first["status"] == "started" and again["job_id"] == first["job_id"]
    assert written.wait(5)  # the inline thread ran the job
    assert job_store.get_job(first["job_id"]).status.value == "completed"
    recaps = [message for message in chat_store.get_session(session_id).messages
              if message.metadata.get("kind") == "call_recap"]
    assert len(recaps) == 1 and "Hike Saturday at nine." in recaps[0].content
    assert client.post("/api/chat/sessions/chat%3Amissing/live-call/recap",
                       json={"call_started_at": call_started}).status_code == 404
