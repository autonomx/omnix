"""LLM-based dialogue parsing with regex fallback.

Sends raw book text to an LLM to produce structured dialogue/narration
segments.  Falls back to the regex ``parse_dialogue`` in
``app.audiobook`` when no LLM callable is provided.
"""

import json
import logging
import re
from typing import Callable, Dict, List, Optional, Tuple

from audiobook.ai.speaker_tracker import SpeakerTracker
from audiobook.constants import NARRATOR

logger = logging.getLogger(__name__)

MAX_RETRIES = 3

VALID_TYPES = {"dialogue", "narration"}

DIALOGUE_PROMPT = """\
You are a precise dialogue parser for audiobook production.

Analyze the following text and split it into sequential segments.
Each segment is either **dialogue** (words spoken by a character) or
**narration** (everything else, including attribution tags such as
"said Tom").

Rules:
- Preserve ALL original text exactly — never summarize, rephrase, or omit words.
- Every word in the input must appear in exactly one output segment.
- Maintain strict chronological order.
- Assign dialogue to the character who speaks it.
- Use "Narrator" as the speaker for all narration segments.
- If the speaker of a quoted line cannot be determined, use "Narrator".
- Do NOT invent or hallucinate character names that are not present in the text.
- Each segment must have a "type" field: "dialogue" for spoken words, "narration" for everything else.
{context_line}
Return ONLY valid JSON — no markdown fences, no commentary.
Use this exact schema:

[
  {{"speaker": "Narrator", "text": "...", "type": "narration"}},
  {{"speaker": "CharacterName", "text": "...", "type": "dialogue"}}
]

Text:
{input_text}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_json_load(response: str) -> Optional[List[Dict]]:
    """Try to parse *response* as a JSON list of segments.

    Handles direct JSON, JSON wrapped in markdown fences, and JSON
    embedded inside a larger response.
    """
    if not response or not response.strip():
        return None

    text = response.strip()

    # 1. Direct parse
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "segments" in data:
            return data["segments"]
        if isinstance(data, dict) and "script" in data:
            return data["script"]
    except json.JSONDecodeError:
        pass

    # 2. Strip markdown code fences (```json ... ``` or ``` ... ```)
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence_match:
        try:
            data = json.loads(fence_match.group(1).strip())
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "segments" in data:
                return data["segments"]
            if isinstance(data, dict) and "script" in data:
                return data["script"]
        except json.JSONDecodeError:
            pass

    # 3. Extract first JSON array
    arr_match = re.search(r"\[.*\]", text, re.DOTALL)
    if arr_match:
        try:
            data = json.loads(arr_match.group())
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

    return None


def _validate_segments(data: List) -> List[Dict]:
    """Validate and normalise a list of raw segment dicts.

    Each valid segment must contain ``speaker`` (str) and ``text`` (str).
    A ``type`` field is added/corrected to be one of ``"dialogue"`` or
    ``"narration"``.  Invalid entries are silently dropped.

    Speakers that are empty, ``None``, or ``"unknown"`` are resolved to
    :data:`NARRATOR` so that downstream code never sees an unresolved
    speaker.
    """
    tracker = SpeakerTracker()
    validated: List[Dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        speaker = item.get("speaker")
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            continue

        # Resolve missing / unknown speakers via the tracker
        if not isinstance(speaker, str) or not speaker.strip() or speaker.strip().lower() == "unknown":
            speaker = tracker.resolve(None)
        else:
            speaker = speaker.strip()
            tracker.update(speaker)

        seg_type = item.get("type", "")
        if seg_type not in VALID_TYPES:
            seg_type = "narration" if speaker == NARRATOR else "dialogue"
        validated.append({
            "speaker": speaker,
            "text": text.strip(),
            "type": seg_type,
        })
    return validated


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_dialogue_llm(
    text: str,
    llm_fn: Optional[Callable[[str], str]] = None,
) -> List[Dict]:
    """Parse *text* into dialogue/narration segments using an LLM.

    Args:
        text: Raw book text to parse.
        llm_fn: Callable that accepts a prompt string and returns the
                 LLM response string.  If ``None``, falls back to the
                 regex-based ``parse_dialogue`` from ``app.audiobook``.

    Returns:
        A list of segment dicts, each with ``speaker``, ``text``, and
        ``type`` (``"dialogue"`` or ``"narration"``).
    """
    if not text or not text.strip():
        return []

    if llm_fn is None:
        return _regex_fallback(text)

    prompt = DIALOGUE_PROMPT.format(
        context_line="",
        input_text=text,
    )

    last_error: Optional[Exception] = None
    for attempt in range(MAX_RETRIES):
        try:
            raw_response = llm_fn(prompt)
            parsed = _safe_json_load(raw_response)
            if parsed is not None:
                segments = _validate_segments(parsed)
                if segments:
                    return segments
            logger.warning(
                "Attempt %d/%d: LLM returned unparseable or empty response",
                attempt + 1,
                MAX_RETRIES,
            )
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning(
                "Attempt %d/%d failed: %s", attempt + 1, MAX_RETRIES, exc
            )

    logger.warning(
        "All %d LLM attempts failed (last error: %s); falling back to regex",
        MAX_RETRIES,
        last_error,
    )
    return _regex_fallback(text)


def parse_with_context(
    text: str,
    llm_fn: Optional[Callable[[str], str]] = None,
    last_speaker: Optional[str] = None,
) -> Tuple[List[Dict], Optional[str]]:
    """Parse *text* with speaker-continuity context.

    Passes the previous speaker into the LLM prompt so the model can
    better attribute ambiguous dialogue.  Uses :class:`SpeakerTracker`
    to resolve and track speakers across calls.

    Args:
        text: Raw book text to parse.
        llm_fn: Optional LLM callable (same contract as
                 :func:`parse_dialogue_llm`).
        last_speaker: The last known speaker from a preceding chunk,
                      used for continuity.

    Returns:
        A tuple of ``(segments, last_speaker_detected)`` where
        *segments* is the list of segment dicts and
        *last_speaker_detected* is the last non-Narrator speaker
        found (or ``None``).
    """
    if not text or not text.strip():
        return [], last_speaker

    tracker = SpeakerTracker()
    if last_speaker:
        tracker.update(last_speaker)

    if llm_fn is None:
        segments = _regex_fallback(text)
        for seg in segments:
            tracker.update(seg["speaker"])
        return segments, tracker.last_speaker

    context_line = ""
    if last_speaker:
        context_line = (
            f"- The most recent speaker before this passage was "
            f'"{last_speaker}". Use this for continuity when attribution '
            f"is ambiguous.\n"
        )

    prompt = DIALOGUE_PROMPT.format(
        context_line=context_line,
        input_text=text,
    )

    last_error: Optional[Exception] = None
    for attempt in range(MAX_RETRIES):
        try:
            raw_response = llm_fn(prompt)
            parsed = _safe_json_load(raw_response)
            if parsed is not None:
                segments = _validate_segments(parsed)
                if segments:
                    for seg in segments:
                        tracker.update(seg["speaker"])
                    return segments, tracker.last_speaker
            logger.warning(
                "Attempt %d/%d: LLM returned unparseable or empty response",
                attempt + 1,
                MAX_RETRIES,
            )
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning(
                "Attempt %d/%d failed: %s", attempt + 1, MAX_RETRIES, exc
            )

    logger.warning(
        "All %d LLM attempts failed (last error: %s); falling back to regex",
        MAX_RETRIES,
        last_error,
    )
    segments = _regex_fallback(text)
    for seg in segments:
        tracker.update(seg["speaker"])
    return segments, tracker.last_speaker


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _regex_fallback(text: str) -> List[Dict]:
    """Fall back to the regex-based parser and add ``type`` fields."""
    from app.audiobook import parse_dialogue  # type: ignore[import]

    segments = parse_dialogue(text)
    return _validate_segments(segments)
