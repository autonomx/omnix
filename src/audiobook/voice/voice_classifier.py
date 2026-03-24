"""LLM-based character voice classification with keyword fallback."""

import json
import logging
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)

FEMALE_NAMES = {
    'sofia', 'emma', 'olivia', 'ava', 'mia', 'charlotte', 'amelia',
    'harper', 'evelyn', 'sarah', 'laura', 'kate', 'jessica', 'ciri',
    'her', 'anaka',
}

MALE_NAMES = {
    'morgan', 'james', 'john', 'robert', 'michael', 'david', 'richard',
    'joseph', 'thomas', 'charles', 'nate', 'inigo', 'jinx',
}

_voice_cache: Dict[str, Dict] = {}

_DEFAULT_RESULT: Dict[str, object] = {
    "gender": "neutral",
    "age": "adult",
    "tone": "calm",
    "confidence": 0.0,
}

_VALID_GENDERS = {"male", "female", "neutral"}
_VALID_AGES = {"child", "young_adult", "adult", "elder"}
_VALID_TONES = {"soft", "deep", "energetic", "calm"}

_LLM_PROMPT_TEMPLATE = (
    "Classify the following character for audiobook voice assignment.\n"
    "Character name: {name}\n"
    "{context_line}"
    "Return ONLY a JSON object with these fields:\n"
    '  "gender": "male" | "female" | "neutral"\n'
    '  "age": "child" | "young_adult" | "adult" | "elder"\n'
    '  "tone": "soft" | "deep" | "energetic" | "calm"\n'
    '  "confidence": a float between 0.0 and 1.0\n'
    "Do not guess aggressively. If uncertain, return neutral.\n"
)


def is_system_character(name: str) -> bool:
    """Return True if *name* looks like a bot, system, or automated speaker."""
    nl = name.lower()
    return any(keyword in nl for keyword in [
        "bot", "system", "notification", "assistant",
    ])


def _keyword_classify(name: str) -> Dict:
    """Fallback classification based on name keywords."""
    if not name:
        return dict(_DEFAULT_RESULT)

    nl = name.lower().strip()

    # System/bot characters get a neutral, robotic classification
    if is_system_character(name):
        return {
            "gender": "neutral",
            "age": "adult",
            "tone": "calm",
            "confidence": 0.9,
        }

    gender = "neutral"
    if any(w in nl for w in ["ms.", "mrs.", "she", "her", "woman"]):
        gender = "female"
    elif any(w in nl for w in ["mr.", "he", "him", "man"]):
        gender = "male"
    elif any(f in nl for f in FEMALE_NAMES):
        gender = "female"
    elif any(m in nl for m in MALE_NAMES):
        gender = "male"

    confidence = 0.6 if gender != "neutral" else 0.0
    return {
        "gender": gender,
        "age": "adult",
        "tone": "calm",
        "confidence": confidence,
    }


def _validate_result(raw: Dict) -> Dict:
    """Sanitise an LLM response into a valid result dict."""
    gender = raw.get("gender", "neutral")
    age = raw.get("age", "adult")
    tone = raw.get("tone", "calm")
    confidence = raw.get("confidence", 0.0)

    if gender not in _VALID_GENDERS:
        gender = "neutral"
    if age not in _VALID_AGES:
        age = "adult"
    if tone not in _VALID_TONES:
        tone = "calm"
    try:
        confidence = float(confidence)
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = 0.0

    return {
        "gender": gender,
        "age": age,
        "tone": tone,
        "confidence": confidence,
    }


def classify_character_voice(
    name: str,
    context: str = "",
    llm_fn: Optional[Callable] = None,
) -> Dict:
    """Classify a character's voice profile using an LLM with keyword fallback.

    Args:
        name: Character name to classify.
        context: Optional narrative context about the character.
        llm_fn: Optional callable that accepts a prompt string and returns a
                 response string.  When *None* or on failure the function falls
                 back to keyword-based detection.

    Returns:
        A dict with keys ``gender``, ``age``, ``tone``, and ``confidence``.
    """
    if not name or not name.strip():
        return dict(_DEFAULT_RESULT)

    cache_key = f"{name}-{context[:50]}"
    if cache_key in _voice_cache:
        return dict(_voice_cache[cache_key])

    if llm_fn is not None:
        context_line = f"Context: {context}\n" if context else ""
        prompt = _LLM_PROMPT_TEMPLATE.format(name=name, context_line=context_line)

        max_attempts = 2
        for attempt in range(max_attempts):
            try:
                response = llm_fn(prompt)
                # Strip markdown fences if present
                text = response.strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[-1]
                    text = text.rsplit("```", 1)[0]
                result = _validate_result(json.loads(text))
                _voice_cache[cache_key] = result
                return dict(result)
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                logger.debug(
                    "LLM parse attempt %d/%d failed for '%s': %s",
                    attempt + 1,
                    max_attempts,
                    name,
                    exc,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("LLM call failed for '%s': %s", name, exc)
                break

    result = _keyword_classify(name)
    _voice_cache[cache_key] = result
    return dict(result)


def clear_voice_cache() -> None:
    """Reset the module-level voice classification cache."""
    _voice_cache.clear()
