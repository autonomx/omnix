"""Dubbing's pipeline pieces without a database: fitting, translation, mixing and the step rules (Phase 6)."""
from __future__ import annotations

import base64
import io
import json
import wave
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from app.apps.dubbing import fit, steps, translate
from app.runtime.feature_catalog import load_feature


def test_the_module_declares_one_job_per_step() -> None:
    feature = load_feature("dubbing")
    assert feature.tier == "app" and "voice" in feature.uses
    assert [spec.type for spec in feature.job_handlers] == [f"dub.{step}" for step in steps.STEPS]
    classes = {spec.type: spec.resource_class.value for spec in feature.job_handlers}
    assert classes["dub.separate"] == "gpu:audio" and classes["dub.translate"] == "gpu:llm"
    assert classes["dub.synthesize"] == "gpu:tts" and classes["dub.transcribe"] == "gpu:stt"


# --- fitting ----------------------------------------------------------------------------------


@pytest.mark.parametrize(("take", "status", "tempo"), [
    (3.2, "fits", 1.0),         # within 10%
    (3.4, "stretched", 3.4 / 3.0),
    (4.0, "over", 1.15),        # past the stretch limit: shorten, then flag
    (2.6, "stretched", 2.6 / 3.0),
    (2.0, "short", 0.85),
    # Past the stretch limit but within tolerance once stretched to it: stretched, not flagged
    # (the English-to-Spanish real-model check had seven such lines labelled "short").
    (3.6, "stretched", 1.15),
    (2.4, "stretched", 0.85),
])
def test_a_take_is_fitted_by_stretching_at_most_15_percent(take: float, status: str, tempo: float) -> None:
    planned = fit.plan_fit(take, 3.0)
    assert planned.status == status and planned.tempo == pytest.approx(tempo)
    if status in {"fits", "stretched"}:
        assert fit.within_tolerance(take / planned.tempo, 3.0)


# --- translation --------------------------------------------------------------------------------


def test_a_batch_names_each_line_its_budget_and_its_context() -> None:
    lines = [translate.LineToTranslate("l1", "Ana", "Good morning.", 1.5)]
    messages = translate.batch_messages(lines, before=["Hello."], after=["Bye."], source="en", target="es")
    request = json.loads(messages[1]["content"])
    assert request["target_language"] == "Spanish" and request["context_before"] == ["Hello."]
    assert request["lines"][0] == {"id": "l1", "speaker": "Ana", "text": "Good morning.", "seconds": 1.5,
                                   "max_characters": 21}


def test_an_answer_must_cover_every_line_and_may_come_fenced() -> None:
    lines = [translate.LineToTranslate("l1", "Ana", "Hi.", 1.0), translate.LineToTranslate("l2", "Ben", "Yes.", 1.0)]
    answer = '```json\n{"lines": [{"id": "l1", "translation": "Hola."}, {"id": "l2", "translation": " Sí. "}]}\n```'
    assert translate.parse_batch(answer, lines) == {"l1": "Hola.", "l2": "Sí."}
    with pytest.raises(translate.TranslationError, match="left out 1"):
        translate.parse_batch('{"lines": [{"id": "l1", "translation": "Hola."}]}', lines)
    with pytest.raises(translate.TranslationError):
        translate.parse_batch("Sorry, I can't.", lines)
    assert translate.parse_shortened('{"translation": "Corto."}') == "Corto."


def test_a_bad_answer_is_asked_again_once() -> None:
    answers = iter(["not json", '{"lines": [{"id": "l1", "translation": "Hola."}]}'])
    translator = translate.Translator()
    translator.chat = lambda messages: next(answers)  # type: ignore[method-assign]
    lines = [translate.LineToTranslate("l1", "Ana", "Hi.", 1.0)]
    assert translator.translate(lines, before=[], after=[], source="en", target="es") == {"l1": "Hola."}


# --- mixing -----------------------------------------------------------------------------------


def test_takes_land_at_their_start_and_duck_the_background(monkeypatch) -> None:
    from app.apps.dubbing import mix

    monkeypatch.setattr("app.platform.voice.contracts.normalize_loudness", lambda samples, rate, target: (samples, 0, 0))
    rate = 1000
    background = np.full(rate * 4, 0.1, dtype=np.float32)
    take = mix.PlacedTake(1.0, np.full(rate, 0.5, dtype=np.float32))
    mixed = mix.mix_dub([take], background, rate)
    assert len(mixed) == len(background)
    assert mixed[200] == pytest.approx(0.1)                       # before the line: background alone
    ducked = 10 ** (mix.DUCK_DB / 20) * 0.1
    assert mixed[1600] == pytest.approx(0.5 + ducked, abs=1e-3)   # during it: the voice over the ducked bed
    assert mixed[3900] == pytest.approx(0.1, abs=1e-3)            # released after it


# --- synthesis and mux rules ---------------------------------------------------------------------


def _wav(seconds: float, rate: int = 24_000) -> str:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(rate)
        time = np.arange(int(rate * seconds)) / rate
        target.writeframes((0.3 * np.sin(2 * np.pi * 200 * time) * 32767).astype("<i2").tobytes())
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _segment(**values: Any) -> dict[str, Any]:
    base = {"id": "line:1", "position": 0, "speaker": "Speaker 1", "start_seconds": 1.0, "end_seconds": 4.0,
            "source_text": "Good morning, everyone.", "translation": "Buenos días a todos.", "translation_revision": 1,
            "translation_origin": "llm", "voice_override": "", "take_asset_id": "", "take_revision": 0,
            "approved_revision": None, "approved_take_asset_id": None}
    return {**base, **values}


class _Run(steps.StepRun):
    def __init__(self, segments: list[dict[str, Any]], *, engine_casting: dict[str, str] | None = None,
                 line_ids: list[str] | None = None) -> None:
        job = SimpleNamespace(id="job:1", input_payload={"project_id": "dub:1", "line_ids": line_ids or []})
        project = {"id": "dub:1", "title": "Call", "source_asset_id": "src", "target_language": "es",
                   "source_language": "en", "assets": {"vocals": "a:vocals"}, "casting": engine_casting or {}}
        super().__init__(job, None, project, segments)
        self.stored: list[dict[str, Any]] = []

    def store(self, **values: Any) -> str:
        self.stored.append(values)
        return f"asset:{len(self.stored)}"


class _Engine:
    def __init__(self, *lengths: float) -> None:
        self.lengths = list(lengths)
        self.calls: list[dict[str, Any]] = []

    def generate_audio(self, text: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"text": text, **kwargs})
        return {"success": True, "audio_base64": _wav(self.lengths.pop(0))}


def _synthesize(run: _Run, engine: _Engine, *, engine_id: str = "faster-qwen3-tts", translator: Any = None,
                edited_meanwhile: bool = False):
    saved: dict[str, Any] = {}
    translations: list[str] = []

    def save_translation(segment_id: str, text: str, expected_revision: int) -> int | None:
        if edited_meanwhile:
            return None  # a person changed the line since this run read it
        if text == run.segments[0]["translation"]:
            return expected_revision  # the same words: nothing to store
        assert expected_revision == len(translations) + 1
        translations.append(text)
        return 1 + len(translations)

    result = steps.synthesize(run, provider=engine, engine=engine_id, translator=translator,
                              save_translation=save_translation,
                              save_take=lambda segment_id, **take: saved.update({segment_id: take}))
    return result, saved, translations


def test_a_line_slightly_long_is_stretched_to_its_budget(monkeypatch) -> None:
    monkeypatch.setattr("app.platform.voice.contracts.watermark_render", lambda wav: (wav, None))
    run = _Run([_segment()], engine_casting={"Speaker 1": "voice-cloning:ana"})
    engine = _Engine(3.4)
    result, saved, _ = _synthesize(run, engine)
    assert engine.calls[0]["speaker"] == "voice-cloning:ana" and engine.calls[0]["language"] == "es"
    assert result == {"fit": {"stretched": 1}}
    assert saved["line:1"]["seconds"] == pytest.approx(3.0, abs=0.05) and saved["line:1"]["revision"] == 1


def test_a_line_far_too_long_is_shortened_then_flagged(monkeypatch) -> None:
    monkeypatch.setattr("app.platform.voice.contracts.watermark_render", lambda wav: (wav, None))

    class _Translator:
        def shorten(self, line: Any, current: str, **kwargs: Any) -> str:
            return current[: len(current) // 2]

    run = _Run([_segment()])
    result, saved, translations = _synthesize(run, _Engine(5.0, 4.4, 3.2), translator=_Translator())
    assert len(translations) == 2 and saved["line:1"]["revision"] == 3   # shortened twice, the last words kept
    assert saved["line:1"]["fit_status"] == "shortened" and result == {"fit": {"shortened": 1}}
    run = _Run([_segment()])
    result, saved, translations = _synthesize(run, _Engine(5.0, 5.0, 5.0), translator=_Translator())
    assert result == {"fit": {"over": 1}} and saved["line:1"]["shortenings"] == 2


def test_a_persons_words_are_never_shortened(monkeypatch) -> None:
    monkeypatch.setattr("app.platform.voice.contracts.watermark_render", lambda wav: (wav, None))

    class _Translator:
        def shorten(self, line: Any, current: str, **kwargs: Any) -> str:
            raise AssertionError("a person's translation was sent to be shortened")

    result, saved, translations = _synthesize(_Run([_segment(translation_origin="person")]), _Engine(5.0),
                                              translator=_Translator())
    assert translations == [] and result == {"fit": {"over": 1}}   # flagged for the person, words kept
    assert saved["line:1"]["shortenings"] == 0


def test_a_shortening_that_returns_the_same_words_keeps_the_take(monkeypatch) -> None:
    monkeypatch.setattr("app.platform.voice.contracts.watermark_render", lambda wav: (wav, None))

    class _Translator:
        def shorten(self, line: Any, current: str, **kwargs: Any) -> str:
            return current

    result, saved, translations = _synthesize(_Run([_segment()]), _Engine(5.0), translator=_Translator())
    assert translations == [] and result == {"fit": {"over": 1}} and saved["line:1"]["revision"] == 1


def test_a_line_edited_during_synthesis_is_left_for_its_editor(monkeypatch) -> None:
    monkeypatch.setattr("app.platform.voice.contracts.watermark_render", lambda wav: (wav, None))

    class _Translator:
        def shorten(self, line: Any, current: str, **kwargs: Any) -> str:
            return current[: len(current) // 2]

    result, saved, _ = _synthesize(_Run([_segment()]), _Engine(5.0), translator=_Translator(), edited_meanwhile=True)
    assert result == {"fit": {"edited_meanwhile": 1}} and saved == {}   # no take for words nobody wrote


def test_an_engine_with_duration_control_renders_to_the_budget(monkeypatch) -> None:
    monkeypatch.setattr("app.platform.voice.contracts.watermark_render", lambda wav: (wav, None))
    engine = _Engine(3.0)
    _synthesize(_Run([_segment()]), engine, engine_id="omnivoice")
    assert engine.calls[0]["duration"] == 3.0


def test_approved_and_current_lines_are_not_rendered_again(monkeypatch) -> None:
    monkeypatch.setattr("app.platform.voice.contracts.watermark_render", lambda wav: (wav, None))
    approved = _segment(id="line:a", take_asset_id="t:1", take_revision=1, approved_revision=1,
                        approved_take_asset_id="t:1")
    current = _segment(id="line:b", take_asset_id="t:2", take_revision=1)
    stale = _segment(id="line:c", take_asset_id="t:3", take_revision=1, translation_revision=2)
    engine = _Engine(3.0)
    _, saved, _ = _synthesize(_Run([approved, current, stale]), engine)
    assert list(saved) == ["line:c"]
    # Asking for a line by id renders it whatever its state.
    _, saved, _ = _synthesize(_Run([approved, current, stale], line_ids=["line:a"]), _Engine(3.0))
    assert list(saved) == ["line:a"]


def test_the_final_mix_waits_for_every_line_to_be_approved() -> None:
    run = _Run([_segment(take_asset_id="t:1", take_revision=1, approved_revision=1, approved_take_asset_id="t:1"),
                _segment(id="line:2", take_asset_id="t:2", take_revision=1)])
    with pytest.raises(steps.DubRequestError, match="1 line"):
        steps.mux(run)
    # An approval of older words does not count.
    assert not steps.approved(_segment(take_asset_id="t:1", take_revision=2, translation_revision=2,
                                       approved_revision=1, approved_take_asset_id="t:1"))


def test_each_speaker_is_cloned_from_their_own_speech(monkeypatch) -> None:
    rate = 16_000
    vocals = np.concatenate([np.full(rate * 12, 0.2), np.full(rate * 12, -0.2)]).astype(np.float32)
    segments = [_segment(id="a", speaker="Speaker 1", start_seconds=0.0, end_seconds=6.0, source_text="One."),
                _segment(id="b", speaker="Speaker 1", start_seconds=6.0, end_seconds=12.0, source_text="Two."),
                _segment(id="c", speaker="Speaker 2", start_seconds=12.0, end_seconds=14.0, source_text="Hi.")]
    run = _Run(segments, engine_casting={"Speaker 3": "voice-cloning:kept"})
    monkeypatch.setattr(run, "asset_bytes", lambda key: base64.b64decode(_raw_wav(vocals, rate)))
    cloned: list[dict[str, Any]] = []

    def clone(**values: Any) -> str:
        cloned.append(values)
        return f"voice-cloning:{len(cloned)}"

    result = steps.cast(run, clone)
    assert result["casting"] == {"Speaker 3": "voice-cloning:kept", "Speaker 1": "voice-cloning:1"}
    assert result["uncast"] == ["Speaker 2"]  # two seconds is too little to clone
    assert cloned[0]["text"] == "One. Two." and cloned[0]["language"] == "en"
    # The project is in the name, so another project with the same title cannot overwrite this voice.
    assert cloned[0]["name"].endswith(f"({steps._safe(run.project['id'])[-8:]})")


def _raw_wav(samples: np.ndarray, rate: int) -> str:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(rate)
        target.writeframes((samples * 32767).astype("<i2").tobytes())
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def test_every_stored_output_is_a_new_asset(monkeypatch, tmp_path) -> None:
    """Re-runs never reuse an id (stored content never changes under one), and SRT and VTT stay apart."""
    from types import SimpleNamespace

    from app.apps.dubbing.steps import StepRun

    stored: dict[str, object] = {}
    store = SimpleNamespace(upsert_asset=lambda record: stored.setdefault(record.id, record) and record)
    monkeypatch.setattr("app.assets.default_asset_store", lambda: store)
    monkeypatch.setattr("app.runtime.paths.resources_data_root", lambda: tmp_path)
    monkeypatch.setattr("app.jobs.inline_execution.require_execution_authority", lambda *_args, **_kwargs: None)
    run = StepRun(SimpleNamespace(id="job:1", input_payload={}), None, {"id": "dub:1"}, [])
    srt = run.store(name="subtitles.es.srt", data=b"1", kind="subtitles_srt", mime="application/x-subrip",
                    title="SRT", parents=[])
    vtt = run.store(name="subtitles.es.vtt", data=b"WEBVTT", kind="subtitles_vtt", mime="text/vtt", title="VTT",
                    parents=[])
    again = run.store(name="subtitles.es.srt", data=b"2", kind="subtitles_srt", mime="application/x-subrip",
                      title="SRT", parents=[])
    assert len({srt, vtt, again}) == 3
    assert len({record.storage_path for record in stored.values()}) == 3
