"""The best section of a clone's sample: the one whose test takes speak best on the real voice engine.

The engine continues from the end of the reference clip and copies its pauses, so a whole sample can render a live
phrase as near-silence. On 2026-11-05 Jinx's clip, cut by hand to end on a whole word, went from 26 silent takes in
240 to 3 in 180; an 8 s section of Abhishek's recording stopped his voice drifting (2026-11-03). This makes that
choice for every new voice, when the clone form's "Pick the best section" is on:

1. word timings of the cleaned sample (the timed speech-to-text engine);
2. a few candidate sections of 5 to 9 s that start and end on whole words at a pause, steady and mostly voiced;
3. test takes of each on the voice engine (``/api/tts/trial_takes``, behind live speech), and how close each take
   sounds to the sample (the speech service's speaker embedding);
4. the section with the fewest silent takes, then the likest voice, then the quickest start.

Anything that cannot run (no timed engine, another voice engine loaded, a busy engine) leaves the whole sample in
place, with a warning, rather than failing the clone.
"""
from __future__ import annotations

import base64
import difflib
import io
import json
import logging
import re
import statistics
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

from .effects import write_mono

logger = logging.getLogger(__name__)

MIN_SECTION_SECONDS = 5.0
MAX_SECTION_SECONDS = 9.0
TARGET_SECTION_SECONDS = 7.0
# A gap between words at least this long is a place to start or end a section (not inside a word or a run of speech).
# Cleaned samples have their pauses shortened, so 0.12 s left one candidate on a 16 s sample; 0.08 s gave three on
# 19 s and six on 40 s (2026-11-07, three real samples).
BOUNDARY_GAP_SECONDS = 0.08
# Up to this long, the whole sample is tried too: a choice that can only make a voice better than not choosing.
WHOLE_SAMPLE_MAX_SECONDS = 20.0
EDGE_SECONDS = 0.06
CANDIDATES_TRIED = 3
TAKES_PER_LINE = 2
# A take with less voiced time than this per character of its line lost words: the live speech check's line
# (phrase_speech_check, 29 characters per voiced second, calibrated on real takes 2026-11-04).
FASTEST_VOICED_CHARS_PER_SECOND = 29.0
# Short and medium lines like a live reply's, including the openers that fail most.
TEST_LINES = (
    "Yeah, well,",
    "Look, I get it.",
    "That's where you're wrong.",
    "So here's what's happening:",
    "Nobody thought it through, and now we're stuck with it.",
    "The bridge was empty when I got there, and the lights were out.",
)


@dataclass(frozen=True)
class Word:
    start: float
    end: float
    text: str


@dataclass
class Section:
    start: float
    end: float
    first_word: int
    last_word: int
    text: str
    prescore: float = 0.0
    whole: bool = False

    @property
    def seconds(self) -> float:
        return round(self.end - self.start, 3)


@dataclass
class SectionTrial:
    start: float
    end: float
    text: str
    takes: int = 0
    silent: int = 0
    likeness: float | None = None
    lead_seconds: float = 0.0
    whole: bool = False

    def rank(self) -> tuple[int, float, float]:
        return (self.silent, -(self.likeness if self.likeness is not None else 0.0), self.lead_seconds)


@dataclass
class SectionChoice:
    audio: bytes | None = None
    text: str = ""
    report: dict[str, Any] = field(default_factory=dict)
    warning: str = ""


def words_of(document: Any) -> list[Word]:
    """Every word of a timed transcript, in order."""
    words: list[Word] = []
    for segment in getattr(document, "segments", []) or []:
        for word in getattr(segment, "words", []) or []:
            text = str(getattr(word, "word", "") or "").strip()
            if text:
                words.append(Word(float(word.start), float(word.end), text))
    return sorted(words, key=lambda item: item.start)


def _levels_db(samples: np.ndarray, rate: int) -> np.ndarray:
    frame = max(1, int(rate * 0.02))
    count = max(1, len(samples) // frame)
    frames = samples[: count * frame].reshape(count, frame)
    return 20 * np.log10(np.sqrt(np.mean(frames ** 2, axis=1) + 1e-12))


def _prescore(samples: np.ndarray, rate: int, start: float, end: float, text: str) -> float:
    """Steady, mostly voiced, near the target length, and ending a sentence or clause: higher is better."""
    levels = _levels_db(samples[int(start * rate): int(end * rate)], rate)
    voiced = levels[levels > levels.max() - 30.0] if len(levels) else levels
    voiced_share = len(voiced) / max(1, len(levels))
    steadiness = -float(np.std(voiced)) / 6.0 if len(voiced) > 1 else -1.0
    length = -abs((end - start) - TARGET_SECTION_SECONDS) / 2.0
    ending = 0.3 if re.search(r"[.!?,;:]$", text) else 0.0
    return voiced_share + steadiness + length + ending


def candidate_sections(
    samples: np.ndarray, rate: int, words: Sequence[Word], *, limit: int = CANDIDATES_TRIED,
) -> list[Section]:
    """Sections that start and end on whole words at a pause, best first and overlapping each other little."""
    if not words:
        return []
    duration = len(samples) / rate
    starts = [i for i, word in enumerate(words) if i == 0 or word.start - words[i - 1].end >= BOUNDARY_GAP_SECONDS]
    ends = [j for j, word in enumerate(words)
            if j == len(words) - 1 or words[j + 1].start - word.end >= BOUNDARY_GAP_SECONDS]
    found: list[Section] = []
    for i in starts:
        for j in ends:
            span = words[j].end - words[i].start
            if j < i or not MIN_SECTION_SECONDS <= span <= MAX_SECTION_SECONDS:
                continue
            # A little air at each edge, never reaching into the next word.
            start = max(0.0, words[i].start - EDGE_SECONDS, words[i - 1].end if i else 0.0)
            end = min(duration, words[j].end + EDGE_SECONDS, words[j + 1].start if j + 1 < len(words) else duration)
            text = " ".join(word.text for word in words[i: j + 1])
            found.append(Section(round(start, 3), round(end, 3), i, j, text, _prescore(samples, rate, start, end, text)))
    found.sort(key=lambda section: -section.prescore)
    chosen: list[Section] = []
    for section in found:
        if all(_overlap(section, other) < 0.5 for other in chosen):
            chosen.append(section)
        if len(chosen) == limit:
            break
    return chosen


def _overlap(left: Section, right: Section) -> float:
    shared = max(0.0, min(left.end, right.end) - max(left.start, right.start))
    return shared / max(1e-9, min(left.end - left.start, right.end - right.start))


def section_text(words: Sequence[Word], section: Section, manual_text: str = "") -> str:
    """The section's words; spelled as the person typed them when they gave a transcript (names, punctuation)."""
    heard = " ".join(word.text for word in words[section.first_word: section.last_word + 1])
    typed = manual_text.split()
    if not typed:
        return heard
    simple = [re.sub(r"[^\w']", "", word).casefold() for word in typed]
    spoken = [re.sub(r"[^\w']", "", word.text).casefold() for word in words]
    mapping: dict[int, int] = {}
    for block in difflib.SequenceMatcher(a=spoken, b=simple, autojunk=False).get_matching_blocks():
        for offset in range(block.size):
            mapping[block.a + offset] = block.b + offset
    # An edge word heard differently ("rudy" for "Rudeus") takes its place from the matched words beside it.
    first = mapping.get(section.first_word)
    if first is None:
        before = [index for index in mapping if index < section.first_word]
        first = mapping[max(before)] + 1 if before else 0
    last = mapping.get(section.last_word)
    if last is None:
        after = [index for index in mapping if index > section.last_word]
        last = mapping[min(after)] - 1 if after else len(typed) - 1
    if not mapping or last < first:
        return heard
    return " ".join(typed[first: last + 1])


def _cosine(left: list[float] | None, right: list[float] | None) -> float | None:
    if left is None or right is None:
        return None
    a, b = np.asarray(left, dtype=np.float64), np.asarray(right, dtype=np.float64)
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(a @ b / denominator) if denominator else None


def score_section(
    section: Section, takes: list[dict[str, Any]], *, reference: list[float] | None,
    embed: Callable[[bytes], list[float] | None],
) -> SectionTrial:
    """How a section's test takes went: silent ones, likeness to the sample, and the quiet before the voice."""
    trial = SectionTrial(section.start, section.end, section.text, takes=len(takes))
    likeness: list[float] = []
    leads: list[float] = []
    for take in takes:
        chars = int(take.get("text_chars") or 0)
        voiced = float(take.get("voiced_seconds") or 0.0)
        if voiced < chars / FASTEST_VOICED_CHARS_PER_SECOND:
            trial.silent += 1
            continue
        leads.append(float(take.get("lead_seconds") or 0.0))
        if reference is not None and take.get("audio_16k"):
            score = _cosine(embed(base64.b64decode(take["audio_16k"])), reference)
            if score is not None:
                likeness.append(score)
    trial.likeness = round(statistics.median(likeness), 3) if likeness else None
    trial.lead_seconds = round(statistics.median(leads), 3) if leads else 0.0
    return trial


def choose_section(
    audio: bytes,
    *,
    manual_text: str = "",
    language: str = "",
    timed_words: Callable[[bytes, str], Sequence[Word]],
    trial_takes: Callable[[bytes, str, Sequence[str], int], dict[str, Any]],
    embed: Callable[[bytes], list[float] | None],
) -> SectionChoice:
    """The best section of a cleaned sample (a mono WAV), or the reason the whole sample stays."""
    import soundfile as sf

    samples, rate = sf.read(io.BytesIO(audio), dtype="float64", always_2d=True)
    samples = samples.mean(axis=1)
    duration = len(samples) / rate
    if duration < MIN_SECTION_SECONDS + 1.0:
        return SectionChoice(report={"skipped": "short", "sample_seconds": round(duration, 3)})
    try:
        words = list(timed_words(audio, language))
    except Exception as exc:  # noqa: BLE001 - the whole sample still clones
        logger.warning("Clone section choice: no word timings", exc_info=True)
        return SectionChoice(warning=f"The best section could not be picked ({exc}); the whole sample is used.")
    sections = candidate_sections(samples, rate, words)
    if not sections:
        return SectionChoice(report={"skipped": "no_section", "sample_seconds": round(duration, 3)})
    if duration <= WHOLE_SAMPLE_MAX_SECONDS:
        sections.append(Section(0.0, round(duration, 3), 0, len(words) - 1, "", whole=True))
    reference = embed(audio)
    trials: list[SectionTrial] = []
    clips: list[tuple[bytes, str]] = []
    for section in sections:
        clip = write_mono(samples[int(section.start * rate): int(section.end * rate)], rate)
        text = section_text(words, section, manual_text)
        result = trial_takes(clip, text, TEST_LINES, TAKES_PER_LINE)
        if not result.get("ok"):
            code = str(result.get("code") or "error")
            reason = {"trial_unsupported": "the loaded voice engine cannot test a clip",
                      "busy": "the voice engine stayed busy"}.get(code, code)
            return SectionChoice(warning=f"The best section could not be picked ({reason}); the whole sample is used.")
        section.text = text
        trial = score_section(section, list(result.get("takes") or []), reference=reference, embed=embed)
        trial.whole = section.whole
        trials.append(trial)
        clips.append((clip, text))
    best = min(range(len(trials)), key=lambda index: trials[index].rank())
    report = {
        "sample_seconds": round(duration, 3),
        "chosen": asdict(trials[best]),
        "candidates": [asdict(trial) for trial in trials],
        "test_lines": len(TEST_LINES),
        "takes_per_line": TAKES_PER_LINE,
    }
    if trials[best].whole:
        # The whole sample tested best: it stays as it is, with its own transcript.
        return SectionChoice(report=report)
    return SectionChoice(audio=clips[best][0], text=clips[best][1], report=report)


def service_timed_words(audio: bytes, language: str) -> list[Word]:
    """Word timings from the speech service's timed engine (the one subtitles use)."""
    from .transcription import transcribe_timed_audio

    return words_of(transcribe_timed_audio(audio, "sample.wav", language=language, diarize=False))


def service_trial_takes(clip: bytes, ref_text: str, lines: Sequence[str], takes: int) -> dict[str, Any]:
    """Test takes of ``lines`` in the voice of ``clip``, from the voice service."""
    from app.runtime.config import get_runtime_config
    from app.runtime.http_client import shared_http_client
    from app.security.service_token import service_headers

    endpoint = get_runtime_config().tts
    if endpoint is None:
        return {"ok": False, "code": "no_voice_service"}
    response = shared_http_client("tts-service").post(
        endpoint.url.rstrip("/") + "/api/tts/trial_takes",
        files={"file": ("section.wav", clip, "audio/wav")},
        data={"phrases": json.dumps(list(lines)), "ref_text": ref_text, "takes": str(takes)},
        headers=service_headers(),
        # Each take waits behind live speech; a whole section's takes take well under a minute on an idle engine.
        timeout=600,
        retry=False,
    )
    if response.status_code != 200:
        return {"ok": False, "code": f"http_{response.status_code}"}
    return response.json()


def service_embedding(audio: bytes) -> list[float] | None:
    """A recording's speaker embedding from the speech service, or None."""
    from app.runtime.config import get_runtime_config
    from app.runtime.http_client import shared_http_client
    from app.security.service_token import service_headers

    endpoint = get_runtime_config().stt
    if endpoint is None:
        return None
    try:
        response = shared_http_client("stt-service").post(
            endpoint.url.removesuffix("/transcribe") + "/speaker/embedding",
            files={"file": ("take.wav", audio, "audio/wav")}, headers=service_headers(), timeout=30, retry=False,
        )
    except Exception:  # noqa: BLE001 - likeness is a tie-breaker; silent takes still decide
        logger.info("Clone section choice: no speaker embedding", exc_info=True)
        return None
    if response.status_code != 200:
        return None
    data = response.json()
    embedding = data.get("embedding") if data.get("ok") else None
    return embedding if isinstance(embedding, list) else None


def choose_section_with_services(audio: bytes, *, manual_text: str = "", language: str = "") -> SectionChoice:
    return choose_section(
        audio, manual_text=manual_text, language=language,
        timed_words=service_timed_words, trial_takes=service_trial_takes, embed=service_embedding,
    )


__all__ = [
    "SectionChoice", "Word", "candidate_sections", "choose_section", "choose_section_with_services", "section_text",
    "words_of",
]
