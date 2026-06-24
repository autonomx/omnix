"""Narration quality API for grounded RPG presentation."""

from .evaluator import (
    build_safe_rewrite_contract,
    evaluate_narration_quality,
    narration_sentences,
    narration_words,
    normalize_narration_text,
)
from .types import DEFAULT_SLOP_PHRASES, NarrationQualityIssue, NarrationQualityPolicy, NarrationQualityReport

__all__ = [
    "DEFAULT_SLOP_PHRASES",
    "NarrationQualityIssue",
    "NarrationQualityPolicy",
    "NarrationQualityReport",
    "build_safe_rewrite_contract",
    "evaluate_narration_quality",
    "narration_sentences",
    "narration_words",
    "normalize_narration_text",
]
