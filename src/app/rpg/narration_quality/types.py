"""Contracts for RPG narration quality checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

DEFAULT_SLOP_PHRASES: tuple[str, ...] = (
    "you can't shake the feeling",
    "the air is thick with",
    "a sense of unease",
    "as if the world itself",
    "only time will tell",
    "little do you know",
    "the shadows seem to whisper",
    "a chill runs down your spine",
)


@dataclass(frozen=True)
class NarrationQualityIssue:
    """A single presentation-quality finding."""

    kind: str
    severity: str
    message: str
    evidence: tuple[str, ...] = ()
    count: int = 1


@dataclass(frozen=True)
class NarrationQualityPolicy:
    """Configurable thresholds for narration quality checks."""

    ngram_size: int = 4
    repeated_ngram_limit: int = 1
    sentence_opening_words: int = 4
    repeated_sentence_opening_limit: int = 1
    recent_overlap_ngram_size: int = 5
    recent_overlap_ratio_limit: float = 0.3
    slop_phrases: tuple[str, ...] = DEFAULT_SLOP_PHRASES
    rewrite_severities: tuple[str, ...] = ("warning", "error")


@dataclass(frozen=True)
class NarrationQualityReport:
    """Pure quality report for a narration candidate."""

    text_length: int
    word_count: int
    sentence_count: int
    issues: tuple[NarrationQualityIssue, ...] = ()
    repeated_ngram_hits: Mapping[str, int] = field(default_factory=dict)
    repeated_sentence_openings: Mapping[str, int] = field(default_factory=dict)
    slop_phrase_hits: tuple[str, ...] = ()
    recent_overlap_ratio: float = 0.0
    should_request_rewrite: bool = False
    rewrite_reasons: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        """Return a stable JSON-friendly report payload."""

        return {
            "text_length": self.text_length,
            "word_count": self.word_count,
            "sentence_count": self.sentence_count,
            "issues": [_issue_payload(issue) for issue in self.issues],
            "repeated_ngram_hits": dict(self.repeated_ngram_hits),
            "repeated_sentence_openings": dict(self.repeated_sentence_openings),
            "slop_phrase_hits": list(self.slop_phrase_hits),
            "recent_overlap_ratio": self.recent_overlap_ratio,
            "should_request_rewrite": self.should_request_rewrite,
            "rewrite_reasons": list(self.rewrite_reasons),
        }


def _issue_payload(issue: NarrationQualityIssue) -> dict[str, object]:
    return {
        "kind": issue.kind,
        "severity": issue.severity,
        "message": issue.message,
        "evidence": list(issue.evidence),
        "count": issue.count,
    }
