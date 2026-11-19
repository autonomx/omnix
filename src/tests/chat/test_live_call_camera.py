"""A picture shown through the call's front camera (companion roadmap 4.2).

Only the description is kept: the image never reaches the job, the message or the memory, and the turn never waits
on the camera past its timeout.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.platform.chat import ChatSessionStore, CreateChatSessionRequest, SendChatMessageRequest
from app.platform.chat.admission import admit_chat_turn, stream_chat_turn
from app.platform.chat.live_call_camera import (
    CAMERA_FILLER,
    CAMERA_SOURCE_ID,
    CAMERA_UNSEEN_LINE,
    CameraTurn,
    camera_vision,
    look_at_camera_image,
)
from tests.support.in_memory_jobs import InMemoryJobStore

# A 1x1 PNG: a real image data URL the request validator accepts.
IMAGE = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
# Chat sessions open a conversation segment in PostgreSQL; runs in the test-postgres job.
pytestmark = pytest.mark.postgres


@pytest.fixture(autouse=True)
def local_identity():
    if os.environ.get("OMNIX_TEST_DATABASE_URL") or os.environ.get("OMNIX_DATABASE_URL"):
        from app.persistence.database import default_database
        from app.persistence.identity_service import ensure_local_identity

        ensure_local_identity(default_database())
    yield


LOCAL = {"desktopCompanionVisionModelId": "vision-test"}
NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)


class FakeVision:
    def __init__(self, base_url: str = "http://127.0.0.1:1234/v1", reply: str = "A blue mug on a desk.",
                 error: Exception | None = None, block: threading.Event | None = None) -> None:
        self.base_url = base_url
        self.reply = reply
        self.error = error
        self.block = block
        self.calls: list[tuple[str, str, str | None]] = []

    def describe(self, image: str, question: str, model_id: str | None):
        self.calls.append((image, question, model_id))
        if self.block is not None:
            self.block.wait(5)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(content=self.reply)


class ScriptedStore(ChatSessionStore):
    def __init__(self, path) -> None:
        from app.platform.live_voice.chat_integration import create_live_voice_chat_port

        super().__init__(path, live_voice_chat_port=create_live_voice_chat_port())
        self.context_items = None

    def stream_provider_reply_chunks(self, session, user_message, **kwargs):
        self.context_items = kwargs.get("context_items")
        yield {"type": "delta", "content": "It's a mug."}
        yield {"type": "complete", "content": "It's a mug.", "metadata": {"generation_status": "completed"}}


def _turn(tmp_path, *, voice: bool = True, image: str | None = IMAGE):
    chat_store = ScriptedStore(tmp_path / "chat.json")
    job_store = InMemoryJobStore(tmp_path / "jobs.sqlite")
    session = chat_store.create_session(CreateChatSessionRequest(
        title="Call", provider_id="llm:lmstudio", model_id="llm:lmstudio:test-model",
    ))
    request = SendChatMessageRequest(
        content="what is this?",
        user_turn_id="voice-user-turn:1" if voice else "turn-1",
        speech_segment_id="segment-1" if voice else None,
        camera_image=image,
    )
    admission = admit_chat_turn(chat_store, job_store, session.id, request)
    return chat_store, job_store, session, request, admission


def _run(chat_store, job_store, admission, request, vision: FakeVision, settings=LOCAL, **options):
    looking = CameraTurn(chat_store, admission.session.id, admission.user_message, request.camera_image,
                         client_factory=lambda: vision, assistant_settings=lambda: settings, now=lambda: NOW,
                         **options)
    before = list(looking)
    after = list(stream_chat_turn(chat_store, job_store, admission, request, **looking.options))
    return before, after


def test_the_image_is_never_in_the_job_or_the_message(tmp_path):
    chat_store, job_store, session, request, admission = _turn(tmp_path)

    assert "camera_image" not in request.model_dump(mode="json")
    payload = json.dumps(job_store.get_job(admission.job.id).model_dump(mode="json"))
    assert "base64" not in payload
    _run(chat_store, job_store, admission, request, FakeVision())

    stored = (tmp_path / "chat.json").read_text(encoding="utf-8")
    assert "base64" not in stored
    assert "base64" not in json.dumps(job_store.get_job(admission.job.id).model_dump(mode="json"))


def test_a_seen_picture_says_the_filler_and_keeps_only_its_description(tmp_path):
    chat_store, job_store, session, request, admission = _turn(tmp_path)
    vision = FakeVision()

    before, after = _run(chat_store, job_store, admission, request, vision)

    assert before == [{"type": "text_chunk", "text": CAMERA_FILLER}]
    assert vision.calls[0][0] == IMAGE and vision.calls[0][2] == "vision-test"
    assert '"what is this?"' in vision.calls[0][1]
    assert chat_store.context_items == [{
        "source_id": CAMERA_SOURCE_ID,
        "title": "What the person's camera shows (a vision model's description, not the image)",
        "content": "A blue mug on a desk.",
    }]
    messages = chat_store.get_session(session.id).messages
    user, reply = messages[-2], messages[-1]
    # The snapshot was written before the reply's commit, and the commit kept it.
    assert user.metadata["camera_snapshot"] == {
        "description": "A blue mug on a desk.", "described_at": NOW.isoformat(),
    }
    assert reply.content == f"{CAMERA_FILLER} It's a mug."
    complete = next(event for event in after if event["type"] == "complete")
    assert complete["content"] == reply.content


def test_a_failed_look_says_so_and_the_reply_goes_on(tmp_path):
    chat_store, job_store, session, request, admission = _turn(tmp_path)

    before, _after = _run(chat_store, job_store, admission, request, FakeVision(error=RuntimeError("bad")))

    assert [event["text"] for event in before] == [CAMERA_FILLER, CAMERA_UNSEEN_LINE]
    assert "could not be read" in chat_store.context_items[0]["content"]
    messages = chat_store.get_session(session.id).messages
    assert "camera_snapshot" not in messages[-2].metadata
    assert messages[-1].content == f"{CAMERA_FILLER} {CAMERA_UNSEEN_LINE} It's a mug."


def test_a_slow_vision_model_is_given_up_on(tmp_path):
    release = threading.Event()
    try:
        look = look_at_camera_image(IMAGE, "look", client_factory=lambda: FakeVision(block=release),
                                    assistant_settings=lambda: LOCAL, timeout_seconds=0.05)
    finally:
        release.set()
    assert look.snapshot is None
    assert look.outcome == "it took too long"


def test_an_empty_description_counts_as_unseen():
    look = look_at_camera_image(IMAGE, "look", client_factory=lambda: FakeVision(reply="  "),
                                assistant_settings=lambda: LOCAL)
    assert look.snapshot is None and look.outcome == "nothing came back"


def test_a_remote_vision_model_needs_the_owners_consent():
    remote = FakeVision(base_url="https://vision.example.com/v1")

    refused = look_at_camera_image(IMAGE, "look", client_factory=lambda: remote, assistant_settings=lambda: LOCAL)
    assert refused.outcome == "remote_vision_not_allowed"
    assert remote.calls == []  # nothing left the machine

    allowed = {**LOCAL, "desktopCompanionRemoteVisionAllowed": True}
    assert camera_vision(client_factory=lambda: remote, assistant_settings=lambda: allowed).available


def test_no_vision_model_configured_is_not_offered(monkeypatch):
    for name in ("OMNIX_VISION_BASE_URL", "OMNIX_VISION_MODEL", "OMNIX_VISION_PROVIDER"):
        monkeypatch.delenv(name, raising=False)
    status = camera_vision(client_factory=lambda: FakeVision(), assistant_settings=lambda: {})
    assert (status.available, status.reason) == (False, "vision_not_configured")


def test_a_typed_turn_ignores_the_picture(tmp_path):
    chat_store, job_store, session, request, admission = _turn(tmp_path, voice=False)
    vision = FakeVision()

    before, _after = _run(chat_store, job_store, admission, request, vision)

    assert before == []
    assert vision.calls == []
    assert chat_store.context_items is None
    assert chat_store.get_session(session.id).messages[-1].content == "It's a mug."


def test_an_oversized_or_foreign_image_is_refused_at_the_request():
    with pytest.raises(ValueError):
        SendChatMessageRequest(content="x", camera_image="data:image/gif;base64,R0lGODlhAQABAAAAACw=")
    with pytest.raises(ValueError):
        SendChatMessageRequest(content="x", camera_image="data:image/png;base64," + "A" * 3_000_001)



def _gateway(chat_store, job_store, monkeypatch, vision: FakeVision, settings=LOCAL):
    from fastapi.testclient import TestClient

    from app.composition.gateway.main import create_gateway_app
    from app.platform.chat import live_call_camera

    monkeypatch.setattr(live_call_camera, "_default_client", lambda: vision)
    monkeypatch.setattr(live_call_camera, "_assistant_settings", lambda: settings)
    app = create_gateway_app(chat_store_factory=lambda: chat_store, job_store_factory=lambda: job_store)
    return TestClient(app, base_url="http://127.0.0.1", headers={"X-Omnix-Client": "test"})


def test_the_call_asks_whether_it_may_offer_show(tmp_path, monkeypatch):
    chat_store = ScriptedStore(tmp_path / "chat.json")
    job_store = InMemoryJobStore(tmp_path / "jobs.sqlite")
    session = chat_store.create_session(CreateChatSessionRequest(title="Call"))
    remote = FakeVision(base_url="https://vision.example.com/v1")

    response = _gateway(chat_store, job_store, monkeypatch, remote).get(
        f"/api/chat/sessions/{session.id}/live-call/camera")

    assert response.status_code == 200
    assert response.json() == {"available": False, "remote": True, "reason": "remote_vision_not_allowed"}
    assert remote.calls == []


def test_a_streamed_call_turn_with_a_picture_keeps_only_its_description(tmp_path, monkeypatch):
    chat_store = ScriptedStore(tmp_path / "chat.json")
    job_store = InMemoryJobStore(tmp_path / "jobs.sqlite")
    session = chat_store.create_session(CreateChatSessionRequest(
        title="Call", provider_id="llm:lmstudio", model_id="llm:lmstudio:test-model",
    ))
    vision = FakeVision()

    response = _gateway(chat_store, job_store, monkeypatch, vision).post(
        f"/api/chat/sessions/{session.id}/messages/stream",
        json={"content": "what is this?", "user_turn_id": "voice-user-turn:9", "speech_segment_id": "seg-9",
              "camera_image": IMAGE},
    )

    assert response.status_code == 200
    events = [json.loads(line.removeprefix("data: ")) for line in response.text.splitlines()
              if line.startswith("data: ")]
    types = [event["type"] for event in events]
    assert types.index("text_chunk") < types.index("delta")
    job_event = next(event for event in events if event["type"] == "job")
    assert "base64" not in json.dumps(job_store.get_job(job_event["job"]["id"]).model_dump(mode="json"))
    assert "base64" not in (tmp_path / "chat.json").read_text(encoding="utf-8")
    assert len(vision.calls) == 1
    messages = chat_store.get_session(session.id).messages
    assert messages[-2].metadata["camera_snapshot"]["description"] == "A blue mug on a desk."
    assert messages[-1].content == f"{CAMERA_FILLER} It's a mug."
