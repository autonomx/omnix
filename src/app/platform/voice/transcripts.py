"""Transcripts: the versioned ``TranscriptDocument`` and its exports (Voice Studio Phase 2).

A transcript is a ``transcript`` asset holding this document as JSON, with the
source audio as its parent. People edit it in the Transcribe tool (rename
speakers, fix words, split and merge segments); exports are built from the
stored document, so an edit shows up in every format.

Subtitles follow common broadcast limits: at most two lines of 42 characters
and 7 seconds per cue, never shorter than 0.8 s, cut at word boundaries.
"""
from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

TRANSCRIPT_SCHEMA = "omnix-transcript-v1"
MAX_LINE_CHARS = 42
MAX_LINES = 2
MAX_CUE_SECONDS = 7.0
MIN_CUE_SECONDS = 0.8
ExportFormat = Literal["srt", "vtt", "txt", "json"]


class TranscriptWord(BaseModel):
    start: float
    end: float
    word: str
    confidence: float | None = None


class TranscriptSegment(BaseModel):
    start: float
    end: float
    speaker: str
    text: str
    words: list[TranscriptWord] = Field(default_factory=list)


class TranscriptDocument(BaseModel):
    schema_: str = Field(default=TRANSCRIPT_SCHEMA, alias="schema")
    language: str = "auto"
    duration: float = 0.0
    engine: str = ""
    diarized: bool = False
    speakers: list[str] = Field(default_factory=list)
    segments: list[TranscriptSegment] = Field(default_factory=list)
    text: str = ""
    source_asset_id: str = ""

    model_config = {"populate_by_name": True}

    def normalized(self) -> TranscriptDocument:
        """Segments in time order, each segment's text from its words, speakers and text recomputed."""
        segments = sorted(self.segments, key=lambda segment: (segment.start, segment.end))
        for segment in segments:
            if segment.words:
                segment.text = " ".join(word.word for word in segment.words).strip()
                segment.start = min(segment.start, segment.words[0].start)
                segment.end = max(segment.end, segment.words[-1].end)
        speakers: list[str] = []
        for segment in segments:
            if segment.speaker not in speakers:
                speakers.append(segment.speaker)
        return self.model_copy(update={
            "segments": segments,
            "speakers": speakers,
            "text": " ".join(segment.text for segment in segments).strip(),
        })


def document_from_stored(raw: dict[str, Any], *, source_asset_id: str = "") -> TranscriptDocument:
    """A ``TranscriptDocument`` from a stored transcript, including the untimed v1 shape.

    Untimed transcripts (``schema_version: 1``) carry one segment for the whole
    file and no words; they open as a single-speaker document.
    """
    if raw.get("schema") == TRANSCRIPT_SCHEMA:
        document = TranscriptDocument.model_validate(raw)
    else:
        segments = []
        for entry in raw.get("segments") or []:
            if isinstance(entry, dict) and str(entry.get("text") or "").strip():
                segments.append(TranscriptSegment(start=float(entry.get("start") or 0.0),
                                                  end=float(entry.get("end") or 0.0),
                                                  speaker="Speaker 1", text=str(entry["text"]).strip()))
        if not segments and str(raw.get("text") or "").strip():
            duration = float(raw.get("duration") or 0.0)
            segments.append(TranscriptSegment(start=0.0, end=duration, speaker="Speaker 1",
                                              text=str(raw["text"]).strip()))
        document = TranscriptDocument(duration=float(raw.get("duration") or 0.0),
                                      engine=str(raw.get("provider") or ""), segments=segments)
    if source_asset_id and not document.source_asset_id:
        document = document.model_copy(update={"source_asset_id": source_asset_id})
    return document.normalized()


def _timestamp(seconds: float, separator: str) -> str:
    milliseconds = max(0, int(round(seconds * 1000)))
    hours, rest = divmod(milliseconds, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{millis:03d}"


def _wrap(words: list[str]) -> list[str]:
    lines: list[str] = []
    for word in words:
        if lines and len(lines[-1]) + 1 + len(word) <= MAX_LINE_CHARS:
            lines[-1] += " " + word
        else:
            lines.append(word)
    return lines


def subtitle_cues(document: TranscriptDocument, *, label_speakers: bool = True) -> list[tuple[float, float, str]]:
    """Cues of at most two 42-character lines and 7 seconds, cut at word boundaries."""
    cues: list[tuple[float, float, str]] = []
    multiple = len({segment.speaker for segment in document.segments}) > 1
    for segment in document.segments:
        words = segment.words or [TranscriptWord(start=segment.start, end=segment.end, word=token)
                                  for token in segment.text.split()]
        if not segment.words and words:
            # No word timing: spread the segment's span evenly over its words.
            step = (segment.end - segment.start) / len(words)
            for index, word in enumerate(words):
                word.start = segment.start + index * step
                word.end = word.start + step
        # The speaker label goes on the segment's first cue only.
        prefix = f"{segment.speaker}: " if label_speakers and multiple else ""
        current: list[TranscriptWord] = []
        for word in words:
            candidate = current + [word]
            text = prefix + " ".join(item.word for item in candidate)
            too_long = len(_wrap(text.split())) > MAX_LINES
            too_slow = bool(current) and word.end - current[0].start > MAX_CUE_SECONDS
            if current and (too_long or too_slow):
                cues.append(_cue(current, prefix))
                prefix = ""
                current = [word]
            else:
                current = candidate
        if current:
            cues.append(_cue(current, prefix))
    # Never shorter than the minimum, never overlapping the next cue.
    adjusted: list[tuple[float, float, str]] = []
    for index, (start, end, text) in enumerate(cues):
        end = max(end, start + MIN_CUE_SECONDS)
        if index + 1 < len(cues):
            end = min(end, cues[index + 1][0])
        adjusted.append((start, max(end, start + 0.01), text))
    return adjusted


def _cue(words: list[TranscriptWord], prefix: str) -> tuple[float, float, str]:
    text = (prefix + " ".join(word.word for word in words)).strip()
    return words[0].start, words[-1].end, "\n".join(_wrap(text.split()))


def export_transcript(document: TranscriptDocument, fmt: ExportFormat) -> tuple[str, str]:
    """The exported text and its media type."""
    document = document.normalized()
    if fmt == "json":
        return json.dumps(document.model_dump(by_alias=True), indent=2, ensure_ascii=False) + "\n", "application/json"
    if fmt == "txt":
        lines = []
        multiple = len(document.speakers) > 1
        for segment in document.segments:
            lines.append(f"{segment.speaker}: {segment.text}" if multiple else segment.text)
        return "\n".join(lines) + "\n", "text/plain"
    cues = subtitle_cues(document)
    if fmt == "srt":
        blocks = [f"{index}\n{_timestamp(start, ',')} --> {_timestamp(end, ',')}\n{text}"
                  for index, (start, end, text) in enumerate(cues, start=1)]
        return "\n\n".join(blocks) + "\n", "application/x-subrip"
    blocks = [f"{_timestamp(start, '.')} --> {_timestamp(end, '.')}\n{text}" for start, end, text in cues]
    return "WEBVTT\n\n" + "\n\n".join(blocks) + "\n", "text/vtt"


def lint_subtitles(cues: list[tuple[float, float, str]]) -> list[str]:
    """Problems a subtitle linter would report: long lines, too many lines, long or overlapping cues."""
    problems = []
    for index, (start, end, text) in enumerate(cues, start=1):
        lines = text.split("\n")
        if len(lines) > MAX_LINES:
            problems.append(f"cue {index}: {len(lines)} lines")
        if any(len(line) > MAX_LINE_CHARS for line in lines):
            problems.append(f"cue {index}: a line is over {MAX_LINE_CHARS} characters")
        if end - start > MAX_CUE_SECONDS + 1e-6 and len(text.split()) > 1:
            problems.append(f"cue {index}: {end - start:.1f} s long")
        if end <= start:
            problems.append(f"cue {index}: ends before it starts")
        if index < len(cues) and end > cues[index][0] + 1e-6:
            problems.append(f"cue {index}: overlaps the next cue")
    return problems


def _comparable_words(text: str) -> list[str]:
    """Lower-case words without punctuation, so a check compares what was said, not how it was written."""
    import re

    return re.findall(r"[\w']+", text.casefold().replace("’", "'"))


def word_error_rate(reference: str, hypothesis: str) -> float:
    """(substitutions + deletions + insertions) / reference words, by word-level edit distance."""
    expected, heard = _comparable_words(reference), _comparable_words(hypothesis)
    if not expected:
        return 0.0 if not heard else 1.0
    previous = list(range(len(heard) + 1))
    for row, word in enumerate(expected, start=1):
        current = [row] + [0] * len(heard)
        for column, candidate in enumerate(heard, start=1):
            current[column] = min(previous[column] + 1, current[column - 1] + 1,
                                  previous[column - 1] + (word != candidate))
        previous = current
    return previous[-1] / len(expected)


def render_check(document: TranscriptDocument, lines: list[dict[str, Any]],
                 timeline: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Word error of a render against its script, overall and per line when the render's timeline is known.

    ``lines`` are the render's script segments (``speaker``, ``text``); ``timeline``
    gives each line's ``start``/``end`` in the render, and every heard word goes to
    the line whose span holds its middle.
    """
    reference = " ".join(str(line.get("text") or "") for line in lines)
    words = [word for segment in document.segments for word in segment.words]
    result: dict[str, Any] = {"word_error_rate": round(word_error_rate(reference, document.text), 4),
                                 "reference_words": len(_comparable_words(reference)), "lines": []}
    if not timeline or len(timeline) != len(lines) or not words:
        return result
    heard: list[list[str]] = [[] for _ in lines]
    spans = [(float(entry.get("start") or 0.0), float(entry.get("end") or 0.0)) for entry in timeline]
    for word in words:
        middle = (word.start + word.end) / 2
        index = min(range(len(spans)), key=lambda item: 0.0 if spans[item][0] <= middle <= spans[item][1]
                    else min(abs(spans[item][0] - middle), abs(spans[item][1] - middle)))
        heard[index].append(word.word)
    result["lines"] = [{
        "index": index, "speaker": str(line.get("speaker") or ""), "text": str(line.get("text") or ""),
        "heard": " ".join(heard[index]), "start": spans[index][0], "end": spans[index][1],
        "word_error_rate": round(word_error_rate(str(line.get("text") or ""), " ".join(heard[index])), 4),
    } for index, line in enumerate(lines)]
    return result


def speaker_sample_spans(document: TranscriptDocument, speaker: str, *, min_seconds: float = 10.0,
                         max_seconds: float = 30.0) -> list[TranscriptSegment]:
    """A speaker's cleanest stretches for a clone sample: 10-30 s of their most confident, unoverlapped speech.

    Segments shorter than a second or overlapping another speaker are skipped;
    the rest are taken best-first (mean word confidence, then length) until at
    least 20 s, never over ``max_seconds``, and returned in time order. Fewer than
    ``min_seconds`` in total returns nothing.
    """
    own = [segment for segment in document.segments if segment.speaker == speaker]
    others = [segment for segment in document.segments if segment.speaker != speaker]

    def overlaps(segment: TranscriptSegment) -> bool:
        return any(other.start < segment.end and segment.start < other.end for other in others)

    def confidence(segment: TranscriptSegment) -> float:
        known = [word.confidence for word in segment.words if word.confidence is not None]
        return sum(known) / len(known) if known else 0.5

    candidates = [segment for segment in own if segment.end - segment.start >= 1.0 and not overlaps(segment)]
    candidates.sort(key=lambda segment: (confidence(segment), segment.end - segment.start), reverse=True)
    chosen: list[TranscriptSegment] = []
    total = 0.0
    for segment in candidates:
        length = segment.end - segment.start
        if total + length > max_seconds:
            continue
        chosen.append(segment)
        total += length
        if total >= 20.0:
            break
    if total < min_seconds:
        return []
    return sorted(chosen, key=lambda segment: segment.start)


def diarization_error_rate(reference: list[tuple[float, float, str]], hypothesis: list[tuple[float, float, str]],
                           *, step: float = 0.01) -> float:
    """Frame-based DER with the best one-to-one speaker mapping (missed + false alarm + confusion)."""
    import itertools

    end = max([item[1] for item in reference + hypothesis] or [0.0])
    frames = int(end / step) + 1
    reference_labels = sorted({item[2] for item in reference})
    hypothesis_labels = sorted({item[2] for item in hypothesis})

    def label_track(items: list[tuple[float, float, str]], labels: list[str]) -> list[set[int]]:
        track: list[set[int]] = [set() for _ in range(frames)]
        for start, stop, label in items:
            for frame in range(int(start / step), min(frames, int(stop / step))):
                track[frame].add(labels.index(label))
        return track

    ref = label_track(reference, reference_labels)
    hyp = label_track(hypothesis, hypothesis_labels)
    total = sum(len(frame) for frame in ref) or 1
    best = None
    sizes = max(len(reference_labels), len(hypothesis_labels))
    for permutation in itertools.permutations(range(sizes), len(hypothesis_labels)):
        errors = 0
        for reference_frame, hypothesis_frame in zip(ref, hyp):
            mapped = {permutation[label] for label in hypothesis_frame}
            correct = len(reference_frame & mapped)
            errors += max(len(reference_frame), len(mapped)) - correct
        best = errors if best is None else min(best, errors)
    return (best or 0) / total


__all__ = [
    "TRANSCRIPT_SCHEMA",
    "TranscriptDocument",
    "TranscriptSegment",
    "TranscriptWord",
    "diarization_error_rate",
    "document_from_stored",
    "export_transcript",
    "lint_subtitles",
    "render_check",
    "speaker_sample_spans",
    "subtitle_cues",
    "word_error_rate",
]
