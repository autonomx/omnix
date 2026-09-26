from __future__ import annotations

import base64
import io
import json
import wave
from contextlib import contextmanager
from dataclasses import replace
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
    run_preview_once,
    concatenate_preview_audio,
    _complete_span_preview,
)
from app.assets.voice_clone_identity import voice_reference_revision
from app.persistence.blob_store import LocalBlobStore
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
    provider = FasterQwen3TTSProvider(config={"device": "cpu"})
    response = provider.generate_audio("Hello", speaker="voice-cloning:missing", language="en")
    assert response["success"] is False
    assert "No reference audio available" in response["error"]


def test_transcript_changes_invalidate_casting_and_render_identity(tmp_path):
    reference = tmp_path / "character.wav"
    reference.write_bytes(_wav())
    sidecar = tmp_path / "Character.json"
    sidecar.write_text(json.dumps({"ref_text": "Original words."}), encoding="utf-8")
    revision = voice_reference_revision(reference)
    unit = RenderUnit(
        span_id="span", ordinal=0, source_hash="a" * 64,
        annotation_id="annotation", annotation_revision=1,
        speaker_id="speaker", casting_id="casting", casting_revision=1,
        voice_profile_id="voice-cloning:character", voice_revision_hash=revision,
        delivery="", language="en", speech_plan=build_speech_plan("Hello."),
    )
    profiles = {unit.voice_profile_id: SimpleNamespace(storage_path=str(reference), metadata={})}
    _voice_for(unit, profiles, "faster-qwen3-tts")
    key = unit.identity(provider_id="provider", model_id="model", model_revision="revision",
                        generation_parameters={}, seed=None).key()
    sidecar.write_text(json.dumps({"ref_text": "Corrected words."}), encoding="utf-8")
    with pytest.raises(RenderFailure, match="changed since casting"):
        _voice_for(unit, profiles, "faster-qwen3-tts")
    revised = replace(unit, voice_revision_hash=voice_reference_revision(reference))
    assert revised.identity(provider_id="provider", model_id="model", model_revision="revision",
                            generation_parameters={}, seed=None).key() != key


def test_preview_processes_all_segments_and_combines_cached_and_generated_audio(tmp_path, monkeypatch):
    reference = tmp_path / "voice.wav"
    reference.write_bytes(_wav())
    first = RenderUnit(
        span_id="span", ordinal=0, source_hash="a" * 64,
        annotation_id="annotation", annotation_revision=1,
        speaker_id="speaker", casting_id="cast", casting_revision=1,
        voice_profile_id="voice-cloning:voice", voice_revision_hash=voice_reference_revision(reference),
        delivery="", language="en", speech_plan=build_speech_plan("First segment."),
        segment_index=0, segment_count=2,
    )
    second = replace(first, speech_plan=build_speech_plan("Second segment."), segment_index=1)
    payload = {"project_id": "book", "source_revision_id": "source", "chapter_id": "chapter",
               "span_id": "span", "provider_id": "test", "model_id": "model",
               "model_revision": "revision"}
    job = {"id": "preview", "lease_token": "lease", "input_payload": payload, "status": "running"}
    jobs = SimpleNamespace(
        claim_next=lambda *args, **kwargs: job, mark_running=lambda *args, **kwargs: job,
        get_job=lambda *args, **kwargs: job, renew_lease=lambda *args, **kwargs: None,
        fail=lambda *args, **kwargs: pytest.fail(str(kwargs)),
    )
    connection = SimpleNamespace(execute=lambda *args: SimpleNamespace(fetchone=lambda: ("source",)))

    @contextmanager
    def work(database):
        yield SimpleNamespace(jobs=jobs, connection=connection, commit=lambda: None, rollback=lambda: None)

    monkeypatch.setattr("app.audiobook.render_service.unit_of_work", work)
    monkeypatch.setattr("app.audiobook.render_service.assert_model_revision", lambda *args: None)
    monkeypatch.setattr("app.audiobook.render_service.load_chapter_units", lambda *args, **kwargs: [first, second])
    monkeypatch.setattr("app.audiobook.render_service.discover_canonical_voice_clone_assets", lambda: [
        SimpleNamespace(id=first.voice_profile_id, storage_path=str(reference), metadata={"voice_id": "voice"})])
    calls = []

    def generate(requests):
        calls.extend(requests)
        return [{"success": True, "audio": base64.b64encode(_wav()).decode()}]

    monkeypatch.setattr("app.audiobook.render_service.get_tts_provider", lambda *args: SimpleNamespace(generate_audio_batch=generate))
    cached_key = first.identity(provider_id="test", model_id="model", model_revision="revision",
                                generation_parameters={}, seed=None).key()
    monkeypatch.setattr("app.audiobook.render_service.find_valid_render", lambda *args: (
        {"id": "cached-first", "audio_asset_id": "audio-first"} if args[-1] == cached_key else None))
    saved = []

    def save(*args, **kwargs):
        assert kwargs["complete_preview"] is False
        saved.append(kwargs["unit"].segment_index)
        return {"render_id": "generated-second", "audio_asset_id": "audio-second"}

    monkeypatch.setattr("app.audiobook.render_service._save_render", save)
    completed = []
    monkeypatch.setattr("app.audiobook.render_service._complete_span_preview", lambda *args, **kwargs: completed.extend(kwargs["refs"]))
    assert run_preview_once(None, None, local_tenant_context(), worker_id="worker")
    assert [request["text"] for request in calls] == ["Second segment."]
    assert saved == [1]
    assert [ref["render_id"] for ref in completed] == ["cached-first", "generated-second"]


def test_combined_preview_preserves_every_frame_in_source_order(tmp_path):
    blobs = LocalBlobStore(tmp_path / "blobs")
    assets = []
    expected = b""
    for index, sample in enumerate((b"\x01\x00", b"\x02\x00")):
        buffer = io.BytesIO()
        frames = sample * 160
        expected += frames
        with wave.open(buffer, "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(16000)
            writer.writeframes(frames)
        record = blobs.put_bytes(f"{index}.wav", buffer.getvalue())
        assets.append((f"{index}.wav", record["checksum_sha256"]))
    output = tmp_path / "preview.wav"
    concatenate_preview_audio(blobs, assets, output)
    with wave.open(str(output), "rb") as reader:
        assert reader.getnframes() == 320
        assert reader.readframes(320) == expected


@pytest.mark.parametrize("canceled", [False, True])
def test_combined_preview_publication_honors_cancellation(tmp_path, monkeypatch, canceled):
    blobs = LocalBlobStore(tmp_path / "blobs")
    records = {}
    refs = []
    for index in range(2):
        key = f"segments/{index}.wav"
        blob = blobs.put_bytes(key, _wav())
        records[f"audio-{index}"] = (key, blob["checksum_sha256"])
        refs.append({"render_id": f"render-{index}", "audio_asset_id": f"audio-{index}"})
    created, completed, acknowledged = [], [], []

    class Connection:
        def execute(self, sql, params):
            return SimpleNamespace(fetchone=lambda: records[params[1]])

    @contextmanager
    def work(database):
        yield SimpleNamespace(
            connection=Connection(), assets=SimpleNamespace(create=lambda context, record: created.append(record)),
            jobs=SimpleNamespace(
                get_job=lambda *args: {"status": "cancel_requested" if canceled else "running"},
                acknowledge_cancel=lambda *args, **kwargs: acknowledged.append(kwargs["job_id"]),
                complete=lambda *args, **kwargs: completed.extend(kwargs["output_refs"]),
            ), commit=lambda: None, rollback=lambda: None,
        )

    monkeypatch.setattr("app.audiobook.render_service.unit_of_work", work)
    _complete_span_preview(None, blobs, local_tenant_context(), job_id="preview",
                           worker_id="worker", lease_token="lease", refs=refs)
    if canceled:
        assert acknowledged == ["preview"]
        assert created == completed == []
        assert list((blobs.root / "audiobook" / "preview").glob("*.wav")) == []
    else:
        assert len(created) == len(completed) == 1
        assert completed[0]["render_ids"] == ["render-0", "render-1"]
        assert completed[0]["audio_asset_id"] == created[0]["id"]
        assert created[0]["generation_job_id"] == "preview"
        audio = blobs.read_bytes(created[0]["storage_key"], expected_checksum=created[0]["checksum_sha256"])
        with wave.open(io.BytesIO(audio), "rb") as reader:
            assert reader.getnframes() == 320
