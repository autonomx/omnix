"""Voice Studio Phase 2: timed, speaker-labelled transcripts and their exports.

The engine's pure parts (chunking, speech windows, clustering, segments) run
here on synthetic audio and embeddings; the NeMo models are exercised by the
real-model check recorded in the roadmap.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from app.assets.models import AssetRecord, AssetType
from app.jobs.models import JobRecord
from app.platform.voice import jobs as voice_jobs
from app.platform.voice.transcripts import (
    MAX_CUE_SECONDS,
    MAX_LINE_CHARS,
    TranscriptDocument,
    diarization_error_rate,
    document_from_stored,
    export_transcript,
    lint_subtitles,
    subtitle_cues,
)
from services.stt import timed_transcription as timed

RATE = 16_000


# --- Chunking and speech windows ----------------------------------------------------------


def test_long_audio_is_cut_in_chunks_of_at_most_30_seconds_at_quiet_points() -> None:
    rng = np.random.default_rng(3)
    speech = 0.3 * rng.standard_normal(RATE * 75).astype(np.float32)
    # A quiet gap just before each nominal cut, where the cut should land.
    for gap in (29.0, 58.5):
        speech[int(gap * RATE): int((gap + 0.3) * RATE)] *= 0.001
    bounds = timed.chunk_bounds(speech)
    assert bounds[0][0] == 0 and bounds[-1][1] == len(speech)
    assert all(end - start <= 30 * RATE for start, end in bounds)
    assert all(bounds[index][1] == bounds[index + 1][0] for index in range(len(bounds) - 1))
    for (_start, cut), gap in zip(bounds[:-1], (29.0, 58.5)):
        assert gap <= cut / RATE <= gap + 0.3


def test_short_audio_is_one_chunk() -> None:
    assert timed.chunk_bounds(np.zeros(RATE * 5, dtype=np.float32)) == [(0, RATE * 5)]


def test_speech_units_split_at_pauses_and_cover_spoken_stretches_only() -> None:
    words = [{"start": 0.0, "end": 0.4}, {"start": 0.5, "end": 1.0}, {"start": 1.1, "end": 1.6},
             {"start": 1.7, "end": 2.2}, {"start": 2.3, "end": 2.8}, {"start": 2.9, "end": 3.4},
             {"start": 4.0, "end": 4.3}, {"start": 10.0, "end": 10.2}]
    units = timed.speech_units(words, 12.0)
    # 0.0-3.4 is one stretch, cut at a word boundary at 3 s; pauses start new units.
    spans = [(unit.start, unit.end) for unit in units]
    assert spans[0] == (0.0, 2.8) and units[0].spoken == pytest.approx(2.8)
    assert spans[1] == pytest.approx((2.65, 3.65))  # 2.9-3.4, widened to a second
    assert units[1].spoken == pytest.approx(0.5)
    assert spans[2] == pytest.approx((3.65, 4.65))  # after a 0.6 s pause
    assert not any(5.0 < start < 9.0 for start, _end in spans)  # silence gets no unit
    assert spans[-1] == pytest.approx((9.6, 10.6))  # a short unit is widened to a second


def test_units_also_end_at_sentence_ends() -> None:
    words = [{"start": 0.0, "end": 0.5, "word": "Thanks."}, {"start": 0.6, "end": 1.0, "word": "Great,"},
             {"start": 1.1, "end": 1.5, "word": "really"}, {"start": 1.6, "end": 2.0, "word": "great!"},
             {"start": 2.1, "end": 2.6, "word": "Next"}]
    units = timed.speech_units(words, 5.0, shortest=0.0)
    assert [(unit.start, unit.end) for unit in units] == [(0.0, 0.5), (0.6, 2.0), (2.1, 2.6)]


def test_word_edges_at_pauses_snap_to_the_speech_energy() -> None:
    samples = np.zeros(RATE * 3, dtype=np.float32)
    tone = 0.3 * np.sin(2 * np.pi * 200 * np.arange(RATE) / RATE).astype(np.float32)
    samples[int(0.50 * RATE): int(1.20 * RATE)] = tone[: int(0.70 * RATE)]
    samples[int(1.80 * RATE): int(2.40 * RATE)] = tone[: int(0.60 * RATE)]
    words = [{"start": 0.64, "end": 0.90, "word": "one"}, {"start": 0.92, "end": 1.04, "word": "two"},
             {"start": 1.68, "end": 2.56, "word": "three"}]
    timed.refine_edges(samples, words)
    assert words[0]["start"] == pytest.approx(0.50, abs=0.011)  # after the file start: snapped earlier
    assert words[0]["end"] == 0.90  # no pause after it: untouched
    assert words[1]["end"] == pytest.approx(1.20, abs=0.011)  # before a pause: snapped later
    assert words[2]["start"] == pytest.approx(1.80, abs=0.011)
    assert words[2]["end"] == pytest.approx(2.40, abs=0.011)


# --- Speaker clustering and diarization ---------------------------------------------------


def _voices(count: int, rng: np.random.Generator, dims: int = 192) -> np.ndarray:
    return rng.standard_normal((count, dims))


def _embed(voice: np.ndarray, rng: np.random.Generator, noise: float = 0.35) -> np.ndarray:
    return voice + noise * np.linalg.norm(voice) / np.sqrt(len(voice)) * rng.standard_normal(len(voice))


def test_clustering_finds_the_speakers_and_numbers_them_by_first_appearance() -> None:
    rng = np.random.default_rng(7)
    voices = _voices(3, rng)
    order = [2, 2, 0, 0, 1, 2, 1, 0, 0, 2]
    labels = timed.cluster_speakers(np.vstack([_embed(voices[speaker], rng) for speaker in order]))
    assert labels.tolist() == [0, 0, 1, 1, 2, 0, 2, 1, 1, 0]


def test_a_speaker_count_fixes_the_number_of_clusters() -> None:
    rng = np.random.default_rng(8)
    voices = _voices(3, rng)
    embeddings = np.vstack([_embed(voices[index % 3], rng) for index in range(12)])
    assert len(set(timed.cluster_speakers(embeddings, speakers=2).tolist())) == 2
    assert len(set(timed.cluster_speakers(embeddings, speakers=3).tolist())) == 3


def test_long_files_cluster_a_sample_and_label_every_window() -> None:
    rng = np.random.default_rng(9)
    voices = _voices(2, rng)
    truth = [(index // 40) % 2 for index in range(1500)]
    labels = timed.cluster_speakers(np.vstack([_embed(voices[speaker], rng) for speaker in truth]))
    assert len(labels) == 1500
    assert labels.tolist() == truth


def test_one_voice_stays_one_speaker() -> None:
    rng = np.random.default_rng(10)
    voice = _voices(1, rng)[0]
    labels = timed.cluster_speakers(np.vstack([_embed(voice, rng) for _ in range(30)]))
    assert set(labels.tolist()) == {0}


def test_a_lone_outlier_or_a_near_identical_voice_is_not_a_new_speaker() -> None:
    rng = np.random.default_rng(12)
    voice = _voices(1, rng)[0]
    outlier = _voices(1, rng)[0]
    embeddings = np.vstack([_embed(voice, rng) for _ in range(20)] + [outlier])
    assert set(timed.cluster_speakers(embeddings).tolist()) == {0}
    twin = voice + 0.25 * np.linalg.norm(voice) / np.sqrt(len(voice)) * rng.standard_normal(len(voice))
    mixed = np.vstack([_embed(voice if index % 2 else twin, rng) for index in range(20)])
    assert set(timed.cluster_speakers(mixed).tolist()) == {0}


def test_short_units_take_the_nearest_speaker_without_shaping_the_clusters() -> None:
    rng = np.random.default_rng(13)
    voices = _voices(2, rng)
    embeddings = np.vstack([_embed(voices[index % 2], rng) for index in range(10)] + [_embed(voices[1], rng, 0.6)])
    reliable = np.array([True] * 10 + [False])
    labels = timed.cluster_speakers(embeddings, reliable=reliable)
    assert labels.tolist() == [0, 1] * 5 + [1]


def test_one_window_is_one_speaker() -> None:
    assert timed.cluster_speakers(np.ones((1, 4))).tolist() == [0]
    assert timed.cluster_speakers(np.zeros((0, 4))).tolist() == []


def _conversation(rng: np.random.Generator) -> tuple[list[dict[str, Any]], list[tuple[float, float, str]]]:
    """Three speakers taking turns: words with timing and the reference speaker turns."""
    turns = [("A", 0.0, 6.0), ("B", 6.4, 11.0), ("A", 11.5, 14.0), ("C", 14.6, 22.0), ("B", 22.5, 27.0)]
    words, reference = [], []
    for speaker, start, end in turns:
        reference.append((start, end, speaker))
        position = start
        while position + 0.3 <= end:
            words.append({"start": round(position, 2), "end": round(position + 0.3, 2), "word": "word",
                          "confidence": 0.9, "true": speaker})
            position += 0.4
    return words, reference


def test_a_three_speaker_conversation_diarizes_with_a_low_error_rate() -> None:
    rng = np.random.default_rng(11)
    voices = dict(zip("ABC", _voices(3, rng)))
    words, reference = _conversation(rng)
    windows = timed.speech_units(words, 27.0)

    def speaker_at(time: float) -> str:
        return next(speaker for start, end, speaker in reference if start - 0.5 <= time <= end + 0.5)

    embeddings = []
    for start, end, _spoken in windows:
        # A window spanning a turn change sounds like whoever speaks most of it.
        middle = (start + end) / 2
        embeddings.append(_embed(voices[speaker_at(middle)], rng))
    reliable = np.array([unit.spoken >= 1.0 for unit in windows])
    labels = timed.cluster_speakers(np.vstack(embeddings), reliable=reliable)
    timed.assign_speakers(words, windows, labels)
    segments = timed.build_segments(words)
    hypothesis = [(segment["start"], segment["end"], segment["speaker"]) for segment in segments]
    assert len({segment["speaker"] for segment in segments}) == 3
    assert diarization_error_rate(reference, hypothesis) < 0.12


def test_segments_break_at_speaker_changes_and_pauses() -> None:
    words = [
        {"start": 0.0, "end": 0.5, "word": "Hello", "confidence": 0.9, "speaker": "Speaker 1"},
        {"start": 0.6, "end": 1.0, "word": "there.", "confidence": 0.8, "speaker": "Speaker 1"},
        {"start": 1.2, "end": 1.6, "word": "Hi!", "confidence": None, "speaker": "Speaker 2"},
        {"start": 4.0, "end": 4.5, "word": "Later.", "confidence": 0.7, "speaker": "Speaker 2"},
    ]
    segments = timed.build_segments(words)
    assert [segment["text"] for segment in segments] == ["Hello there.", "Hi!", "Later."]
    assert [segment["speaker"] for segment in segments] == ["Speaker 1", "Speaker 2", "Speaker 2"]
    assert segments[0]["words"][1] == {"start": 0.6, "end": 1.0, "word": "there.", "confidence": 0.8}


def test_a_long_segment_breaks_after_its_last_sentence_end() -> None:
    texts = ["One", "two.", "Three", "four", "five.", "Six", "seven"]
    words = [{"start": 2.5 * index, "end": 2.5 * index + 2.0, "word": text, "confidence": None,
              "speaker": "Speaker 1"} for index, text in enumerate(texts)]
    segments = timed.build_segments(words)
    assert [segment["text"] for segment in segments] == ["One two. Three four five.", "Six seven"]
    assert segments[1]["start"] == 12.5
    texts[5] = "Six."
    words = [{"start": 2.5 * index, "end": 2.5 * index + 2.0, "word": text, "confidence": None,
              "speaker": "Speaker 1"} for index, text in enumerate(texts)]
    assert [segment["text"] for segment in timed.build_segments(words)] == ["One two. Three four five. Six.", "seven"]


def test_the_diarization_error_rate_counts_misses_and_confusion() -> None:
    reference = [(0.0, 10.0, "A"), (10.0, 20.0, "B")]
    assert diarization_error_rate(reference, [(0.0, 10.0, "x"), (10.0, 20.0, "y")]) == pytest.approx(0.0, abs=0.01)
    assert diarization_error_rate(reference, [(0.0, 20.0, "x")]) == pytest.approx(0.5, abs=0.01)
    assert diarization_error_rate(reference, [(0.0, 10.0, "x")]) == pytest.approx(0.5, abs=0.01)


def test_the_pipeline_shifts_chunk_word_times_onto_the_file_timeline(monkeypatch, tmp_path: Path) -> None:
    class _Hypothesis:
        def __init__(self, words: list[dict[str, Any]]) -> None:
            self.timestamp = {"word": words}
            self.word_confidence = [0.5] * len(words)

    class _Asr:
        def transcribe(self, paths: list[str], **_kwargs: Any) -> list[Any]:
            return [_Hypothesis([{"word": "chunk", "start": 1.0, "end": 1.4}])]

    monkeypatch.setattr(timed.ASR, "get", lambda: _Asr())
    monkeypatch.setattr(timed, "refine_edges", lambda samples, words: None)  # noise has no speech edges
    samples = 0.2 * np.random.default_rng(1).standard_normal(RATE * 45).astype(np.float32)
    document = timed.transcribe_timed(samples, language="de", diarize=False, workdir=tmp_path)
    starts = [word["start"] for segment in document["segments"] for word in segment["words"]]
    bounds = timed.chunk_bounds(samples)
    assert starts == [round(start / RATE + 1.0, 3) for start, _end in bounds]
    assert document["schema"] == "omnix-transcript-v1"
    assert document["language"] == "de" and document["diarized"] is False
    assert document["speakers"] == ["Speaker 1"]


def test_batch_transcription_waits_for_live_audio_between_chunks(monkeypatch, tmp_path: Path) -> None:
    calls: list[str] = []
    live = iter([True, True, False, False])

    class _Asr:
        def transcribe(self, paths: list[str], **_kwargs: Any) -> list[Any]:
            calls.append("chunk")
            return [SimpleNamespace(timestamp={"word": []}, word_confidence=[])]

    monkeypatch.setattr(timed.ASR, "get", lambda: _Asr())
    monkeypatch.setattr(timed.time, "sleep", lambda _seconds: calls.append("wait"))
    samples = np.zeros(RATE * 40, dtype=np.float32)
    timed.transcribe_timed(samples, diarize=False, workdir=tmp_path, live_active=lambda: next(live, False))
    assert calls == ["wait", "wait", "chunk", "chunk"]


def test_a_missing_model_says_how_to_install_it(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(timed, "models_root", lambda: tmp_path)
    monkeypatch.setattr("services.helper_models.free_vram_gb", lambda: 0.5)  # even short of VRAM, install comes first
    helper = timed._NemoHelper("Parakeet-TDT", ("parakeet-tdt-0.6b-v3",), 2.5, lambda path: object())
    with pytest.raises(timed.TimedTranscriptionUnavailable, match="Models tool"):
        helper.get()


def test_a_helper_that_does_not_fit_fails_fast_and_an_idle_one_unloads(monkeypatch, tmp_path: Path) -> None:
    folder = tmp_path / "parakeet-tdt-0.6b-v3"
    folder.mkdir()
    (folder / "model.nemo").write_bytes(b"x")
    monkeypatch.setattr(timed, "models_root", lambda: tmp_path)
    helper = timed._NemoHelper("Parakeet-TDT", ("parakeet-tdt-0.6b-v3",), 2.5, lambda path: "model")
    monkeypatch.setattr("services.helper_models.free_vram_gb", lambda: 1.0)
    with pytest.raises(timed.TimedTranscriptionUnavailable, match="VRAM"):
        helper.get()
    monkeypatch.setattr("services.helper_models.free_vram_gb", lambda: 10.0)
    assert helper.get() == "model" and helper.loaded
    assert helper.unload_if_idle(60.0) is False
    helper.last_used -= 120.0
    assert helper.unload_if_idle(60.0) is True and not helper.loaded


# --- The service route --------------------------------------------------------------------


def _service(monkeypatch, result: Any) -> Any:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    seen: dict[str, Any] = {}

    def fake_transcribe(samples: np.ndarray, **kwargs: Any) -> Any:
        seen.update(kwargs, samples=len(samples))
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(timed, "transcribe_timed", fake_transcribe)
    app = FastAPI()
    timed.install_timed_transcription_routes(app, decode=lambda payload, name: (payload, len(payload) / 32000),
                                             live_active=lambda: False)
    return TestClient(app), seen


def test_the_service_route_returns_a_document_and_passes_the_options(monkeypatch) -> None:
    client, seen = _service(monkeypatch, {"schema": "omnix-transcript-v1", "segments": []})
    response = client.post("/transcribe/timed", files={"file": ("a.wav", b"\x00\x00" * 1600)},
                           data={"language": "fr", "diarize": "false", "speakers": "2"})
    assert response.status_code == 200, response.text
    assert response.json()["schema"] == "omnix-transcript-v1"
    assert seen["language"] == "fr" and seen["diarize"] is False and seen["speakers"] == 2
    assert seen["samples"] == 1600


def test_the_service_route_reports_a_missing_model_in_an_envelope(monkeypatch) -> None:
    # The model-service middleware replaces error bodies, so actionable outcomes arrive as 200 envelopes.
    client, _seen = _service(monkeypatch, timed.TimedTranscriptionUnavailable("Parakeet-TDT is not installed"))
    response = client.post("/transcribe/timed", files={"file": ("a.wav", b"\x00\x00" * 10)})
    assert response.status_code == 200
    assert response.json() == {"ok": False, "code": "model_unavailable", "message": "Parakeet-TDT is not installed"}
    assert client.post("/transcribe/timed", files={"file": ("a.wav", b"\x00\x00")},
                       data={"speakers": "12"}).status_code == 400


# --- Transcript documents and exports -----------------------------------------------------


def _document() -> TranscriptDocument:
    words_one = [{"start": round(0.3 * index, 2), "end": round(0.3 * index + 0.25, 2), "word": f"word{index}"}
                 for index in range(40)]
    return TranscriptDocument.model_validate({
        "schema": "omnix-transcript-v1", "language": "en", "duration": 20.0, "engine": "Parakeet-TDT",
        "diarized": True,
        "segments": [
            {"start": 0.0, "end": 12.0, "speaker": "Ana", "text": "", "words": words_one},
            {"start": 12.5, "end": 14.0, "speaker": "Ben", "text": "",
             "words": [{"start": 12.5, "end": 12.9, "word": "Short."}]},
        ],
    }).normalized()


def test_subtitles_keep_to_two_42_character_lines_and_7_seconds() -> None:
    cues = subtitle_cues(_document())
    assert lint_subtitles(cues) == []
    assert all(len(line) <= MAX_LINE_CHARS for _s, _e, text in cues for line in text.split("\n"))
    assert all(end - start <= MAX_CUE_SECONDS for start, end, _t in cues)
    assert cues[0][2].startswith("Ana: ")
    assert not cues[1][2].startswith("Ana: ")  # the label goes on a segment's first cue only
    assert cues[-1][2] == "Ben: Short."
    assert cues[-1][1] - cues[-1][0] >= 0.8  # short cues are held for the minimum


def test_srt_and_vtt_have_their_timestamp_formats() -> None:
    srt, srt_type = export_transcript(_document(), "srt")
    vtt, vtt_type = export_transcript(_document(), "vtt")
    assert srt_type == "application/x-subrip" and vtt_type == "text/vtt"
    assert srt.startswith("1\n00:00:00,000 --> ")
    assert re.search(r"^\d\d:\d\d:\d\d,\d{3} --> \d\d:\d\d:\d\d,\d{3}$", srt, re.MULTILINE)
    assert vtt.startswith("WEBVTT\n\n00:00:00.000 --> ")
    assert "," not in vtt.split("\n")[2]


def test_text_and_json_exports_round_trip() -> None:
    text, _ = export_transcript(_document(), "txt")
    assert text.splitlines()[1] == "Ben: Short."
    exported, _ = export_transcript(_document(), "json")
    again = TranscriptDocument.model_validate(json.loads(exported))
    assert again.speakers == ["Ana", "Ben"] and again.text.endswith("Short.")


def test_an_untimed_transcript_opens_as_one_speaker() -> None:
    document = document_from_stored({"schema_version": 1, "text": "hello there", "segments": [],
                                     "duration": 2.0, "provider": "parakeet"}, source_asset_id="audio:1")
    assert document.speakers == ["Speaker 1"] and document.text == "hello there"
    assert document.source_asset_id == "audio:1"
    assert subtitle_cues(document)[0] == (0.0, 2.0, "hello there")


# --- The stt.transcribe job (timed) -------------------------------------------------------


class _AssetStore:
    def __init__(self) -> None:
        self.assets: dict[str, AssetRecord] = {}

    def get_asset(self, asset_id: str) -> AssetRecord | None:
        return self.assets.get(asset_id)

    def upsert_asset(self, asset: AssetRecord) -> AssetRecord:
        self.assets[asset.id] = asset
        return asset


class _JobStore:
    def __init__(self) -> None:
        self.completed: dict[str, Any] = {}
        self.failed: dict[str, Any] = {}

    def mark_running(self, job_id: str) -> None:
        pass

    def complete_job(self, job_id: str, request: Any) -> None:
        self.completed[job_id] = request

    def fail_job(self, job_id: str, request: Any) -> None:
        self.failed[job_id] = request


def _stereo_wav(seconds: float, rate: int) -> bytes:
    import io
    import wave

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as target:
        target.setnchannels(2)
        target.setsampwidth(2)
        target.setframerate(rate)
        tone = (0.2 * np.sin(2 * np.pi * 220 * np.arange(int(rate * seconds)) / rate) * 32767).astype("<i2")
        target.writeframes(np.repeat(tone, 2).tobytes())
    return buffer.getvalue()


@pytest.fixture
def stores(tmp_path: Path, monkeypatch) -> _AssetStore:
    import app.assets as assets_module

    store = _AssetStore()
    monkeypatch.setattr(assets_module, "default_asset_store", lambda: store)
    monkeypatch.setattr("app.runtime.paths.resources_data_root", lambda: tmp_path)
    audio = tmp_path / "talk.wav"
    audio.write_bytes(_stereo_wav(1.0, 44_100))
    store.upsert_asset(AssetRecord(id="audio:talk", module="voice", type=AssetType.AUDIO, mime_type="audio/wav",
                                   storage_path=str(audio), metadata={"title": "Talk"},
                                   created_at="2026-10-19T00:00:00+00:00"))
    return store


def _transcribe_job(payload: dict[str, Any]) -> JobRecord:
    return JobRecord.model_validate({
        "id": "job-timed", "module": "stt", "type": "stt.transcribe", "status": "running", "resource_class": "gpu:stt",
        "input_payload": payload, "input_ref": {"asset_id": "audio:talk"},
        "created_at": "2026-10-19T00:00:00+00:00", "updated_at": "2026-10-19T00:00:00+00:00",
    })


def _stt(result: dict[str, Any], seen: dict[str, Any], uploads: list[tuple[int, int]] | None = None) -> Any:
    class _Stt:
        provider_name = "parakeet"

        def transcribe_timed(self, path: str, **kwargs: Any) -> dict[str, Any]:
            import wave

            seen.update(kwargs)
            if uploads is not None:
                with wave.open(path, "rb") as clip:
                    uploads.append((clip.getframerate(), clip.getnchannels()))
            return result

    return _Stt()


def test_a_timed_job_saves_a_versioned_transcript_with_speakers(monkeypatch, stores) -> None:
    seen: dict[str, Any] = {}
    document = _document().model_dump(by_alias=True)
    monkeypatch.setattr("app.providers.service.get_stt_provider",
                        lambda name=None: _stt({"success": True, "document": document}, seen))
    store = _JobStore()
    job = _transcribe_job({"timed": True, "diarize": True, "speakers": 2, "language": "en"})
    voice_jobs.execute_voice_studio_job(store, job)
    assert job.id in store.completed, store.failed.get(job.id)
    assert seen == {"language": "en", "diarize": True, "speakers": 2}
    transcript = next(asset for asset in stores.assets.values() if asset.type == AssetType.TRANSCRIPT)
    assert transcript.parent_asset_ids == ["audio:talk"]
    assert transcript.compat == {"contract": "omnix-transcript-v1"}
    assert transcript.metadata["speakers"] == ["Ana", "Ben"]
    saved = json.loads(Path(transcript.storage_path).read_text(encoding="utf-8"))
    assert saved["source_asset_id"] == "audio:talk" and saved["schema"] == "omnix-transcript-v1"


@pytest.mark.parametrize(("code", "retryable"), [("model_unavailable", False), ("model_service_error", True)])
def test_a_missing_timed_model_fails_without_retry(monkeypatch, stores, code: str, retryable: bool) -> None:
    monkeypatch.setattr("app.providers.service.get_stt_provider",
                        lambda name=None: _stt({"success": False, "code": code, "error": "nope"}, {}))
    store = _JobStore()
    job = _transcribe_job({"timed": True})
    voice_jobs.execute_voice_studio_job(store, job)
    assert store.failed[job.id].retryable is retryable


def test_a_speaker_count_out_of_range_is_refused(monkeypatch, stores) -> None:
    monkeypatch.setattr("app.providers.service.get_stt_provider", lambda name=None: _stt({}, {}))
    store = _JobStore()
    job = _transcribe_job({"timed": True, "speakers": 12})
    voice_jobs.execute_voice_studio_job(store, job)
    assert store.failed[job.id].code == "invalid_request"


# --- Transcript routes --------------------------------------------------------------------


@pytest.fixture
def transcript_client(stores, tmp_path: Path) -> Any:
    from fastapi import APIRouter, FastAPI
    from fastapi.testclient import TestClient

    from app.platform.voice.voice_studio_routes import register_voice_studio_routes

    path = tmp_path / "t.json"
    path.write_text(json.dumps(_document().model_dump(by_alias=True)), encoding="utf-8")
    stores.upsert_asset(AssetRecord(id="transcript:1", module="stt", type=AssetType.TRANSCRIPT,
                                    mime_type="application/json", storage_path=str(path),
                                    metadata={"title": "Transcript of Talk"}, parent_asset_ids=["audio:talk"],
                                    created_at="2026-10-19T00:00:00+00:00"))
    router = APIRouter()
    register_voice_studio_routes(router, SimpleNamespace())
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_a_transcript_is_read_edited_as_a_new_revision_and_exported(transcript_client, stores) -> None:
    loaded = transcript_client.get("/api/voice/transcripts/transcript:1").json()
    assert loaded["revision"] == 1 and loaded["document"]["speakers"] == ["Ana", "Ben"]
    document = loaded["document"]
    for segment in document["segments"]:
        segment["speaker"] = "Host" if segment["speaker"] == "Ana" else segment["speaker"]
    document["segments"][1]["words"][0]["word"] = "Brief."
    document["engine"] = "forged"
    saved = transcript_client.put("/api/voice/transcripts/transcript:1",
                                  json={"document": document, "expected_revision": 1})
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["revision"] == 2
    assert body["document"]["speakers"] == ["Host", "Ben"]
    assert body["document"]["engine"] == "Parakeet-TDT"  # facts about the recording are not editable
    assert body["document"]["segments"][1]["text"] == "Brief."
    assert stores.assets["transcript:1"].storage_path.endswith("-r2.json")
    stale = transcript_client.put("/api/voice/transcripts/transcript:1",
                                  json={"document": document, "expected_revision": 1})
    assert stale.status_code == 409

    srt = transcript_client.get("/api/voice/transcripts/transcript:1/export", params={"format": "srt"})
    assert srt.status_code == 200
    assert 'filename="Transcript-of-Talk.srt"' in srt.headers["content-disposition"]
    assert "Host: word0" in srt.text and "Ben: Brief." in srt.text
    assert transcript_client.get("/api/voice/transcripts/transcript:1/export",
                                 params={"format": "docx"}).status_code == 422


def test_only_transcript_assets_open_as_transcripts(transcript_client) -> None:
    assert transcript_client.get("/api/voice/transcripts/audio:talk").status_code == 404
    assert transcript_client.get("/api/voice/transcripts/missing").status_code == 404


# --- Hooks: check a render, make a voice from a speaker -----------------------------------


def test_word_error_rate_ignores_case_and_punctuation() -> None:
    from app.platform.voice.transcripts import word_error_rate

    assert word_error_rate("Hello, world!", "hello world") == 0.0
    assert word_error_rate("one two three four", "one too three") == pytest.approx(0.5)
    assert word_error_rate("", "") == 0.0


def test_a_render_check_scores_each_line_by_its_place_in_the_render(monkeypatch, stores, tmp_path: Path) -> None:
    render = tmp_path / "render.wav"
    render.write_bytes(_stereo_wav(2.5, 24_000))
    stores.upsert_asset(AssetRecord(
        id="audio:render", module="voice", type=AssetType.AUDIO, mime_type="audio/wav", storage_path=str(render),
        metadata={"title": "Render", "script_segments": [{"speaker": "Ana", "text": "Hello there."},
                                                         {"speaker": "Ben", "text": "General Kenobi."}],
                  "timeline": [{"segment": 0, "start": 0.0, "end": 1.0}, {"segment": 1, "start": 1.3, "end": 2.5}]},
        created_at="2026-10-19T00:00:00+00:00"))
    heard = TranscriptDocument.model_validate({"schema": "omnix-transcript-v1", "segments": [{
        "start": 0.0, "end": 2.4, "speaker": "Speaker 1", "text": "",
        "words": [{"start": 0.1, "end": 0.4, "word": "Hello"}, {"start": 0.5, "end": 0.9, "word": "there."},
                  {"start": 1.4, "end": 1.8, "word": "General"}, {"start": 1.9, "end": 2.4, "word": "Canobi."}],
    }]}).model_dump(by_alias=True)
    seen: dict[str, Any] = {}
    monkeypatch.setattr("app.providers.service.get_stt_provider",
                        lambda name=None: _stt({"success": True, "document": heard}, seen))
    store = _JobStore()
    job = _transcribe_job({"check_render": True})
    job = job.model_copy(update={"input_ref": {"asset_id": "audio:render"}})
    voice_jobs.execute_voice_studio_job(store, job)
    assert job.id in store.completed, store.failed.get(job.id)
    assert seen["diarize"] is False
    output = store.completed[job.id].output_refs[0]
    report = output["render_check"]
    assert report["word_error_rate"] == pytest.approx(0.25)
    assert [line["word_error_rate"] for line in report["lines"]] == [0.0, 0.5]
    assert report["lines"][1]["heard"] == "General Canobi."
    assert "Word error rate 25.0%" in store.completed[job.id].logs[0]["message"]
    assert not [asset for asset in stores.assets.values() if asset.type == AssetType.TRANSCRIPT]


def test_a_render_check_needs_a_render_with_a_script(monkeypatch, stores) -> None:
    monkeypatch.setattr("app.providers.service.get_stt_provider", lambda name=None: _stt({}, {}))
    store = _JobStore()
    job = _transcribe_job({"check_render": True})
    voice_jobs.execute_voice_studio_job(store, job)
    assert store.failed[job.id].code == "invalid_request"


def _two_speaker_document() -> TranscriptDocument:
    def segment(start: float, end: float, speaker: str, confidence: float) -> dict[str, Any]:
        return {"start": start, "end": end, "speaker": speaker, "text": "",
                "words": [{"start": start, "end": end, "word": f"{speaker}@{start:g}", "confidence": confidence}]}

    return TranscriptDocument.model_validate({"schema": "omnix-transcript-v1", "source_asset_id": "audio:talk",
                                              "segments": [
        segment(0.0, 6.0, "Ana", 0.9), segment(6.5, 12.0, "Ben", 0.95), segment(12.5, 20.0, "Ana", 0.6),
        segment(20.5, 28.0, "Ana", 0.95), segment(27.5, 29.0, "Ben", 0.9), segment(30.0, 30.5, "Ana", 0.99),
    ]}).normalized()


def test_a_speaker_sample_takes_their_cleanest_unoverlapped_speech() -> None:
    from app.platform.voice.transcripts import speaker_sample_spans

    spans = speaker_sample_spans(_two_speaker_document(), "Ana")
    # 20.5-28.0 overlaps Ben and 30.0-30.5 is too short; the rest are taken best-first, in time order.
    assert [(segment.start, segment.end) for segment in spans] == [(0.0, 6.0), (12.5, 20.0)]
    assert speaker_sample_spans(_two_speaker_document(), "Ben") == []  # under 10 s of clean speech


def test_the_speaker_sample_route_cuts_the_source_recording(transcript_client, stores, tmp_path: Path) -> None:
    import base64
    import io
    import wave

    from app.platform.voice.effects import write_mono

    rate = 16_000
    source = tmp_path / "talk.wav"
    source.write_bytes(write_mono(0.1 * np.ones(rate * 31), rate))
    transcript = tmp_path / "two.json"
    transcript.write_text(json.dumps(_two_speaker_document().model_dump(by_alias=True)), encoding="utf-8")
    stores.upsert_asset(AssetRecord(id="transcript:2", module="stt", type=AssetType.TRANSCRIPT,
                                    mime_type="application/json", storage_path=str(transcript),
                                    parent_asset_ids=["audio:talk"], created_at="2026-10-19T00:00:00+00:00"))
    response = transcript_client.post("/api/voice/transcripts/transcript:2/speaker-sample", json={"speaker": "Ana"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["text"] == "Ana@0 Ana@12.5"
    with wave.open(io.BytesIO(base64.b64decode(body["audio_base64"]))) as clip:
        seconds = clip.getnframes() / clip.getframerate()
    # 6.0 s + 7.5 s of speech, 50 ms of padding at each edge (none before 0 s), and one 250 ms gap.
    assert seconds == pytest.approx(13.5 + 0.05 + 0.1 + 0.25, abs=0.01)
    assert body["duration"] == pytest.approx(seconds, abs=0.01)
    assert transcript_client.post("/api/voice/transcripts/transcript:2/speaker-sample",
                                  json={"speaker": "Ben"}).status_code == 422
    assert transcript_client.post("/api/voice/transcripts/transcript:2/speaker-sample",
                                  json={"speaker": "Cy"}).status_code == 404


def test_the_stt_service_gets_16_khz_mono_whatever_the_recording(monkeypatch, stores) -> None:
    # Model services cap uploads (50 MB by default): 16 kHz mono keeps about 26 minutes under it.
    uploads: list[tuple[int, int]] = []
    document = _document().model_dump(by_alias=True)
    monkeypatch.setattr("app.providers.service.get_stt_provider",
                        lambda name=None: _stt({"success": True, "document": document}, {}, uploads))
    store = _JobStore()
    job = _transcribe_job({"timed": True})
    voice_jobs.execute_voice_studio_job(store, job)
    assert job.id in store.completed, store.failed.get(job.id)
    assert uploads == [(16_000, 1)]
