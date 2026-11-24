"""A shared screen in a live call (D2, 2026-11-23): glances described ahead of the turn, like the camera's."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.platform.chat.camera_glance import begin_glance, camera_share_look, reset_camera_glances_for_tests
from app.platform.chat.screen_glance import (
    SCREEN_GLANCE_QUESTION,
    SCREEN_SOURCE_ID,
    begin_screen_glance,
    reset_screen_glances_for_tests,
    screen_share_look,
)
from tests.chat.test_camera_glance import _gateway, _session, local_identity  # noqa: F401 - fixture
from tests.chat.test_live_call_camera import IMAGE, LOCAL, FakeVision, ScriptedStore
from tests.support.in_memory_jobs import InMemoryJobStore

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def fresh_glances():
    reset_camera_glances_for_tests()
    reset_screen_glances_for_tests()
    yield
    reset_camera_glances_for_tests()
    reset_screen_glances_for_tests()


def _begin(session_id: str, vision: FakeVision, *, settings=LOCAL) -> str:
    return begin_screen_glance(session_id, IMAGE, client_factory=lambda: vision, assistant_settings=lambda: settings,
                               clock=lambda: 100.0, now=lambda: NOW)


def test_a_screen_glance_is_described_with_the_screen_question_and_kept_apart_from_the_camera():
    vision = FakeVision(reply="A code editor with a failing test highlighted.")

    assert _begin("s1", vision) == "started"
    look = screen_share_look("s1", wait_seconds=2, clock=lambda: 101.0)

    assert vision.calls == [(IMAGE, SCREEN_GLANCE_QUESTION.text, "vision-test")]
    assert look.items[0]["source_id"] == SCREEN_SOURCE_ID
    assert look.items[0]["content"] == "A code editor with a failing test highlighted."
    assert "untrusted" in look.items[0]["title"]
    assert "base64" not in json.dumps(look.items)
    # The camera has seen nothing: a screen glance is not a view of the person.
    assert camera_share_look("s1", wait_seconds=0, clock=lambda: 101.0).snapshot is None


def test_a_camera_glance_does_not_answer_for_the_screen():
    begin_glance("s1", IMAGE, client_factory=lambda: FakeVision(reply="They wave."), assistant_settings=lambda: LOCAL,
                 clock=lambda: 100.0, now=lambda: NOW)

    look = screen_share_look("s1", wait_seconds=0, clock=lambda: 101.0)
    assert look.snapshot is None
    assert "Do not claim to see anything on it" in look.items[0]["content"]


def test_a_screen_glance_needs_the_owners_consent_for_a_remote_vision_model():
    remote = FakeVision(base_url="https://vision.example.com/v1")

    assert _begin("s1", remote) == "remote_vision_not_allowed"
    assert remote.calls == []


@pytest.mark.postgres
@pytest.mark.usefixtures("local_identity")
def test_a_streamed_call_turn_takes_the_screen_and_camera_glances(tmp_path, monkeypatch):
    chat_store = ScriptedStore(tmp_path / "chat.json")
    job_store = InMemoryJobStore(tmp_path / "jobs.sqlite")
    session = _session(chat_store)
    vision = FakeVision(reply="A spreadsheet with a chart of monthly sales.")
    client = _gateway(chat_store, job_store, monkeypatch, vision)

    glance = client.post(f"/api/chat/sessions/{session.id}/screen/glance", json={"image": IMAGE})
    response = client.post(
        f"/api/chat/sessions/{session.id}/messages/stream",
        json={"content": "what do you think of this?", "user_turn_id": "voice-user-turn:4", "speech_segment_id": "seg-4",
              "camera_shared": True, "screen_shared": True},
    )

    assert glance.status_code == 200 and glance.json() == {"status": "started"}
    assert response.status_code == 200
    sources = [item["source_id"] for item in chat_store.context_items]
    assert sources == ["camera", SCREEN_SOURCE_ID]
    assert chat_store.context_items[1]["content"] == "A spreadsheet with a chart of monthly sales."
    assert "base64" not in (tmp_path / "chat.json").read_text(encoding="utf-8")
    messages = chat_store.get_session(session.id).messages
    assert messages[-2].metadata["screen_snapshot"]["description"] == "A spreadsheet with a chart of monthly sales."
    assert "camera_snapshot" not in messages[-2].metadata
