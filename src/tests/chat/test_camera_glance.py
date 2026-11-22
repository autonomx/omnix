"""A shared front camera (camera share, 2026-11-21): glances described ahead of the turn.

The web sends a frame as the person begins; the vision model describes it in the background and the turn takes the
description without waiting long. Only the description is kept, never the image.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone

import pytest

from app.platform.chat import ChatSessionStore, CreateChatSessionRequest
from app.platform.chat import camera_glance
from app.platform.chat.camera_glance import (
    GLANCE_FRESH_SECONDS,
    GLANCE_QUESTION,
    begin_glance,
    camera_share_look,
    reset_camera_glances_for_tests,
)
from app.platform.chat.live_call_camera import CAMERA_SOURCE_ID
from tests.chat.test_live_call_camera import IMAGE, LOCAL, FakeVision, ScriptedStore
from tests.support.in_memory_jobs import InMemoryJobStore

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def fresh_glances():
    reset_camera_glances_for_tests()
    yield
    reset_camera_glances_for_tests()


def _begin(session_id: str, vision: FakeVision, *, clock=lambda: 100.0, settings=LOCAL) -> str:
    return begin_glance(session_id, IMAGE, client_factory=lambda: vision, assistant_settings=lambda: settings,
                        clock=clock, now=lambda: NOW)


def test_a_glance_is_described_for_the_next_turn_and_keeps_no_image():
    vision = FakeVision(reply="They are smiling and holding a green mug.")

    assert _begin("s1", vision) == "started"
    look = camera_share_look("s1", wait_seconds=2, clock=lambda: 101.0)

    # The question is the template's text: a vision client builds its prompt from a string.
    assert vision.calls == [(IMAGE, GLANCE_QUESTION.text, "vision-test")]
    assert isinstance(vision.calls[0][1], str)
    assert look.items == [{
        "source_id": CAMERA_SOURCE_ID,
        "title": camera_glance._SEEN_TITLE,
        "content": "They are smiling and holding a green mug.",
    }]
    assert look.snapshot == {"description": "They are smiling and holding a green mug.",
                             "described_at": NOW.isoformat()}
    assert "base64" not in json.dumps(look.items)


def test_a_turn_without_a_fresh_glance_is_told_it_cannot_see():
    vision = FakeVision()
    _begin("s1", vision, clock=lambda: 100.0)

    stale = camera_share_look("s1", wait_seconds=2, clock=lambda: 100.0 + GLANCE_FRESH_SECONDS + 1)
    other_chat = camera_share_look("s2", wait_seconds=2)

    for look in (stale, other_chat):
        assert look.snapshot is None
        assert look.items[0]["source_id"] == CAMERA_SOURCE_ID
        assert "Do not claim to see anything" in look.items[0]["content"]


def test_a_slow_glance_is_not_waited_on_past_the_turns_wait():
    release = threading.Event()
    vision = FakeVision(block=release)
    _begin("s1", vision)
    try:
        look = camera_share_look("s1", wait_seconds=0.05, clock=lambda: 100.5)
        assert look.snapshot is None
        # The view is on its way: the reply must not tell the person it cannot see them.
        assert "do not say the camera is not working or that you cannot see them" in look.items[0]["content"]
        # One glance per chat at a time: a second frame while the first is described is not sent.
        assert _begin("s1", vision) == "in_progress"
    finally:
        release.set()
    assert camera_share_look("s1", wait_seconds=2, clock=lambda: 101.0).snapshot is not None
    assert len(vision.calls) == 1


def test_a_slow_new_glance_falls_back_to_the_previous_fresh_description():
    # A remote vision model can take longer than a spoken turn waits; the turn then sees one glance behind.
    _begin("s1", FakeVision(reply="They are holding a blue pen."), clock=lambda: 100.0)
    assert camera_share_look("s1", wait_seconds=2, clock=lambda: 101.0).snapshot is not None
    release = threading.Event()
    slow = FakeVision(reply="They are drinking tea.", block=release)
    assert _begin("s1", slow, clock=lambda: 110.0) == "started"
    try:
        behind = camera_share_look("s1", wait_seconds=0.05, clock=lambda: 111.0)
        too_old = camera_share_look("s1", wait_seconds=0.05, clock=lambda: 100.0 + GLANCE_FRESH_SECONDS + 1)
    finally:
        release.set()
    current = camera_share_look("s1", wait_seconds=2, clock=lambda: 112.0)

    assert behind.snapshot == {"description": "They are holding a blue pen.", "described_at": NOW.isoformat()}
    assert too_old.snapshot is None
    assert current.items[0]["content"] == "They are drinking tea."


def test_a_failed_glance_counts_as_unseen():
    _begin("s1", FakeVision(error=RuntimeError("vision down")))

    assert camera_share_look("s1", wait_seconds=2, clock=lambda: 101.0).snapshot is None


def test_a_remote_vision_model_needs_the_owners_consent_before_any_glance():
    remote = FakeVision(base_url="https://vision.example.com/v1")

    assert _begin("s1", remote) == "remote_vision_not_allowed"
    assert remote.calls == []


# Chat sessions open a conversation segment in PostgreSQL; these run in the test-postgres job.
@pytest.fixture
def local_identity():
    if os.environ.get("OMNIX_TEST_DATABASE_URL") or os.environ.get("OMNIX_DATABASE_URL"):
        from app.persistence.database import default_database
        from app.persistence.identity_service import ensure_local_identity

        ensure_local_identity(default_database())
    yield


def _gateway(chat_store, job_store, monkeypatch, vision: FakeVision):
    from fastapi.testclient import TestClient

    from app.composition.gateway.main import create_gateway_app
    from app.platform.chat import live_call_camera

    monkeypatch.setattr(live_call_camera, "_default_client", lambda: vision)
    monkeypatch.setattr(live_call_camera, "_assistant_settings", lambda: LOCAL)
    app = create_gateway_app(chat_store_factory=lambda: chat_store, job_store_factory=lambda: job_store)
    return TestClient(app, base_url="http://127.0.0.1", headers={"X-Omnix-Client": "test"})


def _session(chat_store: ChatSessionStore):
    return chat_store.create_session(CreateChatSessionRequest(
        title="Call", provider_id="llm:lmstudio", model_id="llm:lmstudio:test-model",
    ))


@pytest.mark.postgres
@pytest.mark.usefixtures("local_identity")
def test_a_streamed_call_turn_takes_the_glance_without_a_filler(tmp_path, monkeypatch):
    chat_store = ScriptedStore(tmp_path / "chat.json")
    job_store = InMemoryJobStore(tmp_path / "jobs.sqlite")
    session = _session(chat_store)
    vision = FakeVision(reply="They are waving at the camera.")
    client = _gateway(chat_store, job_store, monkeypatch, vision)

    glance = client.post(f"/api/chat/sessions/{session.id}/camera/glance", json={"image": IMAGE})
    response = client.post(
        f"/api/chat/sessions/{session.id}/messages/stream",
        json={"content": "can you see me?", "user_turn_id": "voice-user-turn:3", "speech_segment_id": "seg-3",
              "camera_shared": True},
    )

    assert glance.status_code == 200 and glance.json() == {"status": "started"}
    assert response.status_code == 200
    events = [json.loads(line.removeprefix("data: ")) for line in response.text.splitlines()
              if line.startswith("data: ")]
    assert "text_chunk" not in [event["type"] for event in events]
    assert chat_store.context_items[0]["content"] == "They are waving at the camera."
    assert "base64" not in (tmp_path / "chat.json").read_text(encoding="utf-8")
    messages = chat_store.get_session(session.id).messages
    assert messages[-2].metadata["camera_snapshot"]["description"] == "They are waving at the camera."


@pytest.mark.postgres
@pytest.mark.usefixtures("local_identity")
def test_a_glance_refuses_a_foreign_image_and_an_unknown_chat(tmp_path, monkeypatch):
    chat_store = ScriptedStore(tmp_path / "chat.json")
    job_store = InMemoryJobStore(tmp_path / "jobs.sqlite")
    session = _session(chat_store)
    vision = FakeVision()
    client = _gateway(chat_store, job_store, monkeypatch, vision)

    gif = client.post(f"/api/chat/sessions/{session.id}/camera/glance",
                      json={"image": "data:image/gif;base64,R0lGODlhAQABAAAAACw="})
    unknown = client.post("/api/chat/sessions/missing/camera/glance", json={"image": IMAGE})

    assert gif.status_code == 422
    assert unknown.status_code == 404
    assert vision.calls == []
