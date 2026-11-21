"""The person's voiceprint and the live speaker score (companion 2.1, 2.2)."""
from __future__ import annotations

import asyncio
import io
import json
import math
import struct
import uuid
import wave
from typing import Any

import numpy as np
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.persistence.document_schemas import DocumentShapeError, validate_document
from app.platform.voice import stt_proxy_routes as proxy
from app.platform.voice import voiceprint
from app.providers.nemotron_eou_live_websocket import install_nemotron_eou_websocket
from app.runtime.tenant_context import current_tenant, pop_tenant, push_tenant, tenant_context
from services.helper_models import HelperModel
from services.stt.speaker_scoring import SpeakerScorer

DIM = 192


def _unit(*hot: int) -> list[float]:
    vector = np.zeros(DIM)
    for index in hot:
        vector[index] = 1.0
    return list(vector / np.linalg.norm(vector))


def _wav(seconds: float, *, amplitude: float = 0.2, rate: int = 16_000, channels: int = 1) -> bytes:
    count = int(seconds * rate)
    samples = [int(amplitude * 32767 * math.sin(2 * math.pi * 220 * i / rate)) for i in range(count)]
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as target:
        target.setnchannels(channels)
        target.setsampwidth(2)
        target.setframerate(rate)
        target.writeframes(struct.pack(f"<{count * channels}h", *[s for s in samples for _ in range(channels)]))
    return buffer.getvalue()


class _Store:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str, str], Any] = {}

    def read(self, *, module: str, record_type: str, record_id: str, default: Any = None) -> Any:
        return self.records.get((module, record_type, record_id), default)

    def write(self, payload: Any, *, module: str, record_type: str, record_id: str) -> None:
        validate_document(module, record_type, payload)
        self.records[(module, record_type, record_id)] = payload

    def delete(self, *, module: str, record_type: str, record_id: str) -> None:
        self.records.pop((module, record_type, record_id), None)


@pytest.fixture
def store(monkeypatch) -> _Store:
    documents = _Store()
    monkeypatch.setattr(voiceprint, "_store", lambda: documents)
    return documents


@pytest.fixture
def guest():
    token = push_tenant(tenant_context(user_id="guest-1", workspace_id="guest-ws", membership_id="m-guest",
                                       roles=["guest"]))
    yield
    pop_tenant(token)


def _embedder(vectors: list[list[float]]):
    given = iter(vectors)
    seen: list[str] = []

    def embed(payload: bytes, filename: str) -> list[float]:
        voiceprint.passage_pcm(payload)  # what reaches the service is a valid passage
        seen.append(filename)
        return next(given)

    embed.seen = seen
    return embed


# -- 2.1 enrolment --------------------------------------------------------------------------------------------


def test_a_print_is_the_unit_mean_of_passages_that_sound_like_one_voice(store) -> None:
    embed = _embedder([_unit(0), _unit(0, 1), _unit(0, 2)])
    status = voiceprint.enrol_voiceprint([_wav(4), _wav(5), _wav(6)], embed=embed)

    assert status.enrolled and status.can_enrol and status.samples == 3 and status.model == "titanet-large"
    assert embed.seen == ["passage-1.wav", "passage-2.wav", "passage-3.wav"]
    (key, stored), = store.records.items()
    assert key == ("live-voice", "voiceprint", current_tenant().user_id)
    assert set(stored) == {"embedding", "model", "created_at", "samples", "agreement"}  # never audio
    assert abs(np.linalg.norm(stored["embedding"]) - 1.0) < 1e-4
    assert stored["agreement"] == pytest.approx(0.5, abs=1e-3)
    # The status the browser sees never carries the print.
    assert "embedding" not in status.model_dump()


def test_passages_in_different_voices_are_refused_and_nothing_is_stored(store) -> None:
    with pytest.raises(voiceprint.VoiceprintError) as refused:
        voiceprint.enrol_voiceprint([_wav(4), _wav(4)], embed=_embedder([_unit(0), _unit(1)]))
    assert refused.value.code == "voices_differ"
    assert store.records == {}


@pytest.mark.parametrize(("payload", "code"), [
    (_wav(2.0), "passage_length"),
    (_wav(21.0), "passage_length"),
    (_wav(4, amplitude=0.0), "passage_silent"),
    (_wav(4, rate=48_000), "invalid_audio"),
    (_wav(4, channels=2), "invalid_audio"),
    (b"not a wav", "invalid_audio"),
], ids=["short", "long", "silent", "48k", "stereo", "not-wav"])
def test_a_passage_must_be_a_few_seconds_of_16k_mono_speech(payload: bytes, code: str) -> None:
    with pytest.raises(voiceprint.VoiceprintError) as refused:
        voiceprint.passage_pcm(payload)
    assert refused.value.code == code


def test_one_passage_or_six_is_refused(store) -> None:
    for count in (1, 6):
        with pytest.raises(voiceprint.VoiceprintError) as refused:
            voiceprint.enrol_voiceprint([_wav(4)] * count, embed=_embedder([_unit(0)] * count))
        assert refused.value.code == "passage_count"


def test_a_guest_cannot_enrol_and_never_has_a_print(store, guest) -> None:
    store.records[("live-voice", "voiceprint", "guest-1")] = {"embedding": _unit(0)}
    with pytest.raises(voiceprint.VoiceprintError) as refused:
        voiceprint.enrol_voiceprint([_wav(4), _wav(4)], embed=_embedder([_unit(0), _unit(0)]))
    assert (refused.value.status, refused.value.code) == (403, "guest_cannot_enrol")
    assert voiceprint.read_voiceprint() is None
    assert not voiceprint.voiceprint_status().can_enrol


def test_the_stored_shape_is_checked() -> None:
    with pytest.raises(DocumentShapeError):
        validate_document("live-voice", "voiceprint", {"embedding": [float("nan")] * DIM, "model": "m",
                                                        "created_at": "2026-11-15T00:00:00+00:00", "samples": 2,
                                                        "agreement": 0.9})


def test_the_routes_enrol_report_and_delete(store, monkeypatch) -> None:
    vectors = iter([_unit(0), _unit(0, 1)])
    monkeypatch.setattr(voiceprint, "speaker_embedding", lambda payload, filename: next(vectors))
    router = APIRouter()
    voiceprint.register_voiceprint_routes(router)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    assert client.get("/api/stt/voiceprint").json()["enrolled"] is False
    enrolled = client.post("/api/stt/voiceprint", files=[("files", ("a.wav", _wav(4), "audio/wav")),
                                                         ("files", ("b.wav", _wav(4), "audio/wav"))])
    assert enrolled.status_code == 200, enrolled.text
    assert enrolled.json()["enrolled"] is True and "embedding" not in enrolled.json()
    refused = client.post("/api/stt/voiceprint", files=[("files", ("a.wav", _wav(1), "audio/wav"))] * 2)
    assert refused.status_code == 422 and refused.json()["detail"]["error"] == "passage_length"
    assert client.delete("/api/stt/voiceprint").json()["enrolled"] is False
    assert store.records == {}


# -- 2.2 the gateway sends the print, never the browser's ------------------------------------------------------


def test_the_gateway_sends_this_accounts_print_and_drops_one_from_the_browser(store) -> None:
    assert proxy._speaker_profile() is None
    voiceprint.enrol_voiceprint([_wav(4), _wav(4)], embed=_embedder([_unit(0), _unit(0)]))

    message = json.loads(proxy._speaker_profile())
    assert message["type"] == "speaker_profile" and len(message["embedding"]) == DIM
    names = proxy._CallNames(None, "scope")
    sent = json.dumps({"type": "speaker_profile", "embedding": _unit(1)})
    assert asyncio.run(proxy._from_browser(sent, names)) is None
    assert asyncio.run(proxy._from_browser(json.dumps({"type": "hello"}), names)) == json.dumps({"type": "hello"})
    assert asyncio.run(proxy._from_browser("not json", names)) == "not json"


def test_a_print_that_cannot_be_read_means_a_call_without_one(monkeypatch) -> None:
    def broken():
        raise RuntimeError("database down")

    monkeypatch.setattr(voiceprint, "_store", broken)
    assert proxy._speaker_profile() is None


# -- the speaker model is held for the call -------------------------------------------------------------------


def test_a_held_helper_is_not_unloaded_however_long_it_waits() -> None:
    helper = HelperModel("speaker", 0.0, lambda: object())
    helper.get()
    helper.hold()
    assert not helper.unload_if_idle(0.0)
    helper.release()
    helper.release()  # an extra release never goes negative
    assert helper.holds == 0
    helper.last_used -= 10
    assert helper.unload_if_idle(1.0)


def test_the_scorer_gives_a_rounded_cosine_or_nothing() -> None:
    helper = HelperModel("speaker", 0.0, lambda: "model")
    scorer = SpeakerScorer(helper, lambda model, samples: np.asarray(_unit(0, 1)) * 3)
    profile = np.asarray(_unit(0))
    assert scorer.warm()
    assert scorer.similarity(b"\x00\x01" * 16_000, profile) == pytest.approx(0.7071, abs=1e-4)
    assert scorer.similarity(b"\x00\x01" * 16_000, np.asarray(_unit(0)[:64])) is None  # another model's print

    def missing():
        raise HelperModel.unavailable("no weights")

    assert not SpeakerScorer(HelperModel("speaker", 0.0, missing), lambda model, samples: None).warm()


# -- the live socket scores each final ------------------------------------------------------------------------


class _Manager:
    feed_chunk_samples = 10**9  # never streams; the final decodes the whole segment

    def finalize(self, _segment_id: str, _pcm: bytes) -> tuple[str, dict]:
        return "hello there", {}

    def release(self, _segment_id: str) -> None:
        return None


class _Scorer:
    def __init__(self, similarity: float | None = 0.83, warms: bool = True) -> None:
        self.events: list[str] = []
        self.audio: list[int] = []
        self._similarity, self._warms = similarity, warms

    def hold(self) -> None:
        self.events.append("hold")

    def release(self) -> None:
        self.events.append("release")

    def warm(self) -> bool:
        self.events.append("warm")
        return self._warms

    def similarity(self, pcm16: bytes, profile: np.ndarray) -> float | None:
        assert abs(float(np.linalg.norm(profile)) - 1.0) < 1e-9
        self.audio.append(len(pcm16))
        return self._similarity


def _frame(header: dict, pcm: bytes) -> bytes:
    encoded = json.dumps(header).encode("utf-8")
    return len(encoded).to_bytes(4, "little") + encoded + pcm


def _segment(socket, session: str, segment_id: str, sequence: int, seconds: float) -> list[dict]:
    pcm = b"\x10\x00" * int(seconds * 16_000)
    socket.send_bytes(_frame({"segmentId": segment_id, "sequence": sequence, "sampleStart": 0,
                              "captureStartSample": 0, "primaryStartSample": 0, "sampleRate": 16_000,
                              "sessionId": session}, pcm))
    assert socket.receive_json()["type"] == "audio_buffered"
    socket.send_json({"type": "final", "segmentId": segment_id, "sequence": sequence, "sessionId": session})
    received = [socket.receive_json(), socket.receive_json()]  # finalize_queued, result_available
    assert [message["type"] for message in received] == ["finalize_queued", "result_available"]
    return received


def _connect(scorer: Any):
    app = FastAPI()
    install_nemotron_eou_websocket(app, _Manager(), speaker_scorer=scorer)
    return TestClient(app).websocket_connect("/ws/transcribe")


def test_each_final_long_enough_gets_its_score_after_the_final() -> None:
    scorer = _Scorer()
    session = f"s-{uuid.uuid4().hex}"
    with _connect(scorer) as socket:
        socket.receive_json()  # ready
        socket.send_json({"type": "speaker_profile", "model": "titanet-large", "embedding": [2.0] * DIM})
        socket.send_json({"type": "hello", "sessionId": session})
        ready = socket.receive_json()
        assert (ready["type"], ready["speakerScores"]) == ("session_ready", True)
        _segment(socket, session, "seg-1", 1, 1.2)
        score = socket.receive_json()
        assert score == {"type": "speaker_score", "segmentId": "seg-1", "sequence": 1, "similarity": 0.83,
                         "modelMs": score["modelMs"]}
        _segment(socket, session, "seg-2", 2, 0.5)  # too short to say whose voice it is
        _segment(socket, session, "seg-3", 3, 0.9)
        assert socket.receive_json()["segmentId"] == "seg-3"
    assert scorer.audio == [int(1.2 * 16_000) * 2, int(0.9 * 16_000) * 2]
    assert scorer.events[0] == "hold" and scorer.events[-1] == "release" and "warm" in scorer.events


def test_a_profile_after_the_first_message_is_ignored() -> None:
    scorer = _Scorer()
    session = f"s-{uuid.uuid4().hex}"
    with _connect(scorer) as socket:
        socket.receive_json()
        socket.send_json({"type": "hello", "sessionId": session})
        socket.receive_json()
        socket.send_json({"type": "speaker_profile", "embedding": [1.0] * DIM})
        _segment(socket, session, "seg-1", 1, 1.2)
    assert scorer.events == [] and scorer.audio == []


@pytest.mark.parametrize("profile", [[1.0] * 10, [0.0] * DIM, ["x"] * DIM, None],
                         ids=["too-short", "zero", "not-numbers", "missing"])
def test_a_profile_that_is_not_an_embedding_is_ignored(profile) -> None:
    scorer = _Scorer()
    with _connect(scorer) as socket:
        socket.receive_json()
        socket.send_json({"type": "speaker_profile", "embedding": profile})
        socket.send_json({"type": "hello", "sessionId": f"s-{uuid.uuid4().hex}"})
        ready = socket.receive_json()
        assert (ready["type"], ready["speakerScores"]) == ("session_ready", False)
    assert scorer.events == []


@pytest.mark.parametrize("scorer", [_Scorer(warms=False), _Scorer(similarity=None)], ids=["cold", "failed"])
def test_no_answer_is_a_null_score_so_nothing_waits_for_one(scorer: _Scorer) -> None:
    session = f"s-{uuid.uuid4().hex}"
    with _connect(scorer) as socket:
        socket.receive_json()
        socket.send_json({"type": "speaker_profile", "embedding": [1.0] * DIM})
        socket.send_json({"type": "hello", "sessionId": session})
        assert socket.receive_json()["speakerScores"] is True
        _segment(socket, session, "seg-1", 1, 1.2)
        score = socket.receive_json()
        assert (score["type"], score["segmentId"], score["similarity"]) == ("speaker_score", "seg-1", None)
    assert scorer.events[0] == "hold" and scorer.events[-1] == "release"


def test_no_scorer_means_finals_as_today() -> None:
    session = f"s-{uuid.uuid4().hex}"
    with _connect(None) as socket:
        socket.receive_json()
        socket.send_json({"type": "speaker_profile", "embedding": [1.0] * DIM})
        socket.send_json({"type": "hello", "sessionId": session})
        assert socket.receive_json()["speakerScores"] is False
        _segment(socket, session, "seg-1", 1, 1.2)
