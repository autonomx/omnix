"""Picking the best section of a clone's sample: candidates on whole words, then the one whose test takes speak."""
from __future__ import annotations

import base64
import io
import wave
from typing import Any

import numpy as np

from app.platform.voice import clip_selection
from app.platform.voice.clip_selection import Word, candidate_sections, choose_section, section_text

RATE = 16_000


def _speech(words: list[tuple[float, float]], seconds: float) -> np.ndarray:
    """A tone in each word's time, silence between: enough for levels and cuts."""
    samples = np.zeros(int(seconds * RATE))
    time = np.arange(len(samples)) / RATE
    for start, end in words:
        span = (time >= start) & (time < end)
        samples[span] = 0.3 * np.sin(2 * np.pi * 180 * time[span])
    return samples


def _wav(samples: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(RATE)
        target.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())
    return buffer.getvalue()


def _sentence_words(seconds: float = 18.0) -> list[Word]:
    """Words 0.35 s long with 0.05 s between them, and a 0.3 s pause after every sixth (a sentence end)."""
    words, time, index = [], 0.2, 0
    while time + 0.35 < seconds - 0.2:
        text = f"word{index}" + ("." if index % 6 == 5 else "")
        words.append(Word(round(time, 3), round(time + 0.35, 3), text))
        time += 0.35 + (0.3 if index % 6 == 5 else 0.05)
        index += 1
    return words


def test_sections_start_and_end_on_whole_words_at_a_pause() -> None:
    words = _sentence_words()
    samples = _speech([(word.start, word.end) for word in words], 18.0)

    sections = candidate_sections(samples, RATE, words)

    assert 1 <= len(sections) <= clip_selection.CANDIDATES_TRIED
    for section in sections:
        assert clip_selection.MIN_SECTION_SECONDS <= section.seconds <= clip_selection.MAX_SECTION_SECONDS + 0.2
        # Only the pauses after a sentence are long enough to cut at (or the sample's own start and end).
        assert section.text.endswith(".") or section.last_word == len(words) - 1
        assert section.first_word == 0 or words[section.first_word - 1].text.endswith(".")
        # Never into a neighbouring word.
        assert section.start >= (words[section.first_word - 1].end if section.first_word else 0.0)
        assert section.end <= (words[section.last_word + 1].start if section.last_word + 1 < len(words) else 18.0)
    for index, left in enumerate(sections):
        for right in sections[index + 1:]:
            shared = max(0.0, min(left.end, right.end) - max(left.start, right.start))
            assert shared < 0.5 * min(left.seconds, right.seconds)


def test_a_typed_transcript_spells_the_section() -> None:
    words = [Word(0, 0.4, "hello"), Word(0.5, 0.9, "rudy"), Word(1.0, 1.4, "greyrat"), Word(1.5, 1.9, "here.")]
    section = clip_selection.Section(0.45, 1.95, 1, 3, "")

    assert section_text(words, section) == "rudy greyrat here."
    # The name was heard as "rudy": the typed spelling still fills its place.
    assert section_text(words, section, "Hello, Rudeus Greyrat here.") == "Rudeus Greyrat here."
    assert section_text(words, section, "Hello, Rudy Greyrat here!") == "Rudy Greyrat here!"
    assert section_text(words, section, "Something else entirely") == "rudy greyrat here."


def _takes(silent: int, total: int = 12, *, lead: float = 0.1) -> dict[str, Any]:
    takes = []
    for index in range(total):
        voiced = 0.0 if index < silent else 1.5
        takes.append({"line": index // 2, "take": index % 2, "text_chars": 30, "seconds": 2.0,
                      "voiced_seconds": voiced, "lead_seconds": lead,
                      "audio_16k": base64.b64encode(b"take").decode("ascii")})
    return {"ok": True, "engine": "faster-qwen3-tts", "takes": takes}


def test_the_section_whose_takes_go_silent_least_wins() -> None:
    words = _sentence_words()
    samples = _speech([(word.start, word.end) for word in words], 18.0)
    audio = _wav(samples)
    tried: list[str] = []
    silent_by_order = [4, 0, 2, 3]  # three sections, then the whole sample (18 s: short enough to try)

    def trial(clip: bytes, text: str, lines, takes: int) -> dict[str, Any]:
        tried.append(text)
        assert takes == clip_selection.TAKES_PER_LINE and list(lines) == list(clip_selection.TEST_LINES)
        return _takes(silent_by_order[len(tried) - 1])

    choice = choose_section(audio, timed_words=lambda _audio, _language: words, trial_takes=trial,
                            embed=lambda _audio: [1.0, 0.0])

    assert len(tried) == 4
    assert choice.audio is not None and choice.text == tried[1]
    assert choice.report["chosen"]["silent"] == 0
    assert [candidate["silent"] for candidate in choice.report["candidates"]] == [4, 0, 2, 3]
    assert [candidate["whole"] for candidate in choice.report["candidates"]] == [False, False, False, True]
    assert choice.report["chosen"]["likeness"] == 1.0
    with wave.open(io.BytesIO(choice.audio)) as clip:
        assert clip_selection.MIN_SECTION_SECONDS <= clip.getnframes() / clip.getframerate() <= 9.5


def test_when_the_whole_sample_tests_best_it_stays_as_it_is() -> None:
    words = _sentence_words()
    audio = _wav(_speech([(word.start, word.end) for word in words], 18.0))
    tried: list[str] = []

    def trial(clip: bytes, text: str, lines, takes: int) -> dict[str, Any]:
        tried.append(text)
        return _takes(0 if len(tried) == 4 else 3)

    choice = choose_section(audio, timed_words=lambda _audio, _language: words, trial_takes=trial,
                            embed=lambda _audio: None)

    assert choice.audio is None and choice.warning == ""
    assert choice.report["chosen"]["whole"] is True and choice.report["chosen"]["silent"] == 0
    assert tried[-1].startswith("word0 ") and tried[-1].endswith(words[-1].text)


def test_a_long_sample_is_not_tried_whole() -> None:
    words = _sentence_words(30.0)
    audio = _wav(_speech([(word.start, word.end) for word in words], 30.0))
    tried: list[str] = []

    choose_section(audio, timed_words=lambda _audio, _language: words,
                   trial_takes=lambda _clip, text, _lines, _count: tried.append(text) or _takes(1),
                   embed=lambda _audio: None)

    assert len(tried) == clip_selection.CANDIDATES_TRIED


def test_with_no_engine_to_test_on_the_whole_sample_stays_with_a_warning() -> None:
    words = _sentence_words()
    audio = _wav(_speech([(word.start, word.end) for word in words], 18.0))

    choice = choose_section(audio, timed_words=lambda _audio, _language: words,
                            trial_takes=lambda *_args: {"ok": False, "code": "trial_unsupported"},
                            embed=lambda _audio: None)

    assert choice.audio is None
    assert "loaded voice engine cannot test a clip" in choice.warning


def test_a_short_sample_is_used_whole_without_testing() -> None:
    called: list[bool] = []
    audio = _wav(_speech([(0.1, 4.0)], 5.0))

    choice = choose_section(audio, timed_words=lambda *_a: called.append(True) or [],
                            trial_takes=lambda *_a: called.append(True) or {}, embed=lambda _a: None)

    assert choice.audio is None and choice.report["skipped"] == "short" and called == []


def test_no_word_timings_leaves_the_whole_sample() -> None:
    audio = _wav(_speech([(0.1, 15.0)], 16.0))

    def fail(_audio: bytes, _language: str):
        raise RuntimeError("no timed engine")

    choice = choose_section(audio, timed_words=fail, trial_takes=lambda *_a: {}, embed=lambda _a: None)

    assert choice.audio is None and "no timed engine" in choice.warning
