from __future__ import annotations

import base64
import io
import wave
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from app.audiobook.render_service import (
    RenderFailure,
    _pause_if_requested,
    _generation_progress_callback,
    _voice_for,
    decode_pcm_wav,
    higher_priority_tts_pending,
    run_render_once,
)
from app.audiobook.render_planner import RenderUnit
from app.audiobook.speech_plan import build_speech_plan
from app.audiobook.hashing import bytes_hash
from app.persistence.tenant import local_tenant_context


def _wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16000)
        writer.writeframes(b"\x00\x00" * 160)
    return buffer.getvalue()


def test_only_valid_lossless_provider_audio_is_accepted() -> None:
    content = _wav()
    audio, duration, rate = decode_pcm_wav({"success": True, "audio": base64.b64encode(content).decode()})
    assert audio == content
    assert duration == pytest.approx(0.01)
    assert rate == 16000
    with pytest.raises(RenderFailure):
        decode_pcm_wav({"success": False, "is_fallback": True, "audio": base64.b64encode(content).decode()})
    with pytest.raises(RenderFailure):
        decode_pcm_wav({"success": True, "audio": base64.b64encode(b"bad").decode()})


class _Connection:
    def __init__(self, pending: bool) -> None:
        self.pending = pending
        self.params = None

    def execute(self, _sql, params):
        self.sql = _sql
        self.params = params
        return self

    def fetchone(self):
        return (self.pending,)


def test_offline_priority_check_includes_realtime_and_preview() -> None:
    connection = _Connection(True)
    assert higher_priority_tts_pending(connection, local_tenant_context())
    assert "gpu:tts:realtime" in connection.params[1]
    assert "gpu:tts:preview" in connection.params[1]
    assert "available_at <= CURRENT_TIMESTAMP" in connection.sql
    assert "lease_expires_at > CURRENT_TIMESTAMP" in connection.sql


def test_generation_progress_persists_fractional_unit_progress(monkeypatch) -> None:
    class Jobs:
        def __init__(self) -> None:
            self.progress = None

        def update_progress(self, *_args, **kwargs):
            self.progress = kwargs["progress"]

    jobs = Jobs()

    @contextmanager
    def work(_database):
        yield SimpleNamespace(jobs=jobs, commit=lambda: None)

    monkeypatch.setattr("app.audiobook.render_service.unit_of_work", work)
    callback = _generation_progress_callback(
        None, local_tenant_context(), job_id="job", worker_id="worker",
        lease_token="lease", completed=0, total=1,
    )

    callback(760, 2048)

    assert jobs.progress["current"] == pytest.approx(760 / 2048)
    assert jobs.progress["total"] == 1
    assert jobs.progress["unit_current"] == 760
    assert jobs.progress["unit_total"] == 2048


def test_pause_request_releases_render_lease_at_a_unit_boundary() -> None:
    class Jobs:
        def get_job(self, *_args, **_kwargs):
            return {"status": "running", "metadata": {"pause_requested": True}}

    class Connection:
        def __init__(self) -> None:
            self.statements = []

        def execute(self, sql, params):
            self.statements.append((sql, params))
            return self

        def fetchone(self):
            return ("render-job",)

    connection = Connection()
    work = SimpleNamespace(connection=connection, jobs=Jobs())

    assert _pause_if_requested(
        work, local_tenant_context(), job_id="render-job", worker_id="worker", lease_token="lease",
    )
    assert "SET status = 'paused'" in connection.statements[0][0]
    assert "UPDATE omnix_job_attempts" in connection.statements[1][0]


def test_offline_does_not_claim_a_chapter_while_preview_is_pending(monkeypatch) -> None:
    class Jobs:
        def claim_next(self, *_args, **_kwargs):
            raise AssertionError("offline work was claimed before preview finished")

    @contextmanager
    def work(_database):
        yield SimpleNamespace(connection=_Connection(True), jobs=Jobs(), rollback=lambda: None)

    monkeypatch.setattr("app.audiobook.render_service.unit_of_work", work)
    assert run_render_once(None, None, local_tenant_context(), worker_id="offline") is False


def test_offline_does_not_claim_when_another_tts_process_is_realtime_busy(monkeypatch) -> None:
    class Jobs:
        def claim_next(self, *_args, **_kwargs):
            raise AssertionError("offline work was claimed while realtime TTS was active")

    @contextmanager
    def work(_database):
        yield SimpleNamespace(connection=_Connection(False), jobs=Jobs(), rollback=lambda: None)

    monkeypatch.setattr("app.audiobook.render_service.unit_of_work", work)
    monkeypatch.setattr("app.audiobook.render_service.other_process_priority_pending", lambda: True)
    assert run_render_once(None, None, local_tenant_context(), worker_id="offline") is False


def test_offline_render_uses_exact_cast_voice_profile(tmp_path) -> None:
    reference = tmp_path / "character.wav"
    reference.write_bytes(b"reference version one")
    unit = RenderUnit(
        span_id="span", ordinal=0, source_hash="a" * 64,
        annotation_id="annotation", annotation_revision=1,
        speaker_id="speaker", casting_id="casting", casting_revision=1,
        voice_profile_id="voice-cloning:character",
        voice_revision_hash=bytes_hash(reference.read_bytes()),
        delivery="", language="en", speech_plan=build_speech_plan("Hello."),
    )
    profiles = {unit.voice_profile_id: SimpleNamespace(
        storage_path=str(reference), metadata={"voice_clone_id": "character"})}
    assert _voice_for(unit, profiles, "faster-qwen3-tts") == unit.voice_profile_id
    reference.write_bytes(b"new reference")
    with pytest.raises(RenderFailure, match="changed since casting"):
        _voice_for(unit, profiles, "faster-qwen3-tts")


def test_canonical_voice_id_cannot_fall_back_to_another_reference(monkeypatch) -> None:
    from app.providers.faster_qwen3_tts_provider import FasterQwen3TTSProvider

    monkeypatch.setattr("app.assets.canonical_voice_clones.discover_canonical_voice_clone_assets",
                        lambda: [])
    provider = object.__new__(FasterQwen3TTSProvider)
    response = provider.generate_audio("Hello", speaker="voice-cloning:missing", language="en")
    assert response["success"] is False
    assert "unavailable" in response["error"]
