"""Pure narration quality helpers for grounded RPG presentation.

The simulation remains the authoritative source of RPG truth. This module only
scores already-produced presentation text and builds a safe rewrite request
contract for presentation-layer polish. It does not mutate state, infer state, or
approve new game facts.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import re
from typing import Iterable, Mapping, Sequence

_WORD_RE = re.compile(r"[A-Za-z0-9']+")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
_WHITESPACE_RE = re.compile(r"\s+")

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
            "issues": [
                {
                    "kind": issue.kind,
                    "severity": issue.severity,
                    "message": issue.message,
                    "evidence": list(issue.evidence),
                    "count": issue.count,
                }
                for issue in self.issues
            ],
            "repeated_ngram_hits": dict(self.repeated_ngram_hits),
            "repeated_sentence_openings": dict(self.repeated_sentence_openings),
            "slop_phrase_hits": list(self.slop_phrase_hits),
            "recent_overlap_ratio": self.recent_overlap_ratio,
            "should_request_rewrite": self.should_request_rewrite,
            "rewrite_reasons": list(self.rewrite_reasons),
        }


def normalize_narration_text(text: str) -> str:
    """Normalize whitespace while preserving words and punctuation."""

    return _WHITESPACE_RE.sub(" ", text or "").strip()


def narration_words(text: str) -> tuple[str, ...]:
    """Tokenize narration into lowercase word-like tokens."""

    return tuple(match.group(0).lower() for match in _WORD_RE.finditer(text or ""))


def narration_sentences(text: str) -> tuple[str, ...]:
    """Split narration into stable sentence-like chunks."""

    normalized = normalize_narration_text(text)
    if not normalized:
        return ()
    return tuple(sentence.strip() for sentence in _SENTENCE_RE.split(normalized) if sentence.strip())


def _ngrams(words: Sequence[str], size: int) -> tuple[str, ...]:
    if size <= 0 or len(words) < size:
        return ()
    return tuple(" ".join(words[index : index + size]) for index in range(0, len(words) - size + 1))


def _repeated_counts(values: Iterable[str], limit: int) -> dict[str, int]:
    counts = Counter(value for value in values if value)
    return {value: count for value, count in counts.items() if count > limit}


def _sentence_openings(sentences: Sequence[str], opening_words: int) -> tuple[str, ...]:
    openings: list[str] = []
    for sentence in sentences:
        words = narration_words(sentence)
        if not words:
            continue
        openings.append(" ".join(words[:opening_words]))
    return tuple(openings)


def _recent_overlap_ratio(words: Sequence[str], recent_texts: Sequence[str], policy: NarrationQualityPolicy) -> float:
    current_ngrams = set(_ngrams(words, policy.recent_overlap_ngram_size))
    if not current_ngrams or not recent_texts:
        return 0.0

    recent_words = narration_words("\n".join(recent_texts))
    recent_ngrams = set(_ngrams(recent_words, policy.recent_overlap_ngram_size))
    if not recent_ngrams:
        return 0.0
    return len(current_ngrams.intersection(recent_ngrams)) / len(current_ngrams)


def _slop_hits(normalized_text: str, slop_phrases: Sequence[str]) -> tuple[str, ...]:
    lowered = normalized_text.lower()
    return tuple(phrase for phrase in slop_phrases if phrase.lower() in lowered)


def evaluate_narration_quality(
    text: str,
    *,
    recent_texts: Sequence[str] = (),
    policy: NarrationQualityPolicy | None = None,
) -> NarrationQualityReport:
    """Evaluate narration presentation quality without changing game state."""

    active_policy = policy or NarrationQualityPolicy()
    normalized = normalize_narration_text(text)
    words = narration_words(normalized)
    sentences = narration_sentences(normalized)

    repeated_ngram_hits = _repeated_counts(_ngrams(words, active_policy.ngram_size), active_policy.repeated_ngram_limit)
    repeated_sentence_openings = _repeated_counts(
        _sentence_openings(sentences, active_policy.sentence_opening_words), active_policy.repeated_sentence_opening_limit
    )
    slop_phrase_hits = _slop_hits(normalized, active_policy.slop_phrases)
    overlap_ratio = _recent_overlap_ratio(words, recent_texts, active_policy)

    issues: list[NarrationQualityIssue] = []
    if repeated_ngram_hits:
        issues.append(
            NarrationQualityIssue(
                kind="repeated_ngram",
                severity="warning",
                message="Narration repeats the same phrase more than the configured limit.",
                evidence=tuple(sorted(repeated_ngram_hits)),
                count=sum(repeated_ngram_hits.values()),
            )
        )
    if repeated_sentence_openings:
        issues.append(
            NarrationQualityIssue(
                kind="repeated_sentence_opening",
                severity="warning",
                message="Multiple sentences begin with the same opening words.",
                evidence=tuple(sorted(repeated_sentence_openings)),
                count=sum(repeated_sentence_openings.values()),
            )
        )
    if slop_phrase_hits:
        issues.append(
            NarrationQualityIssue(
                kind="slop_phrase",
                severity="warning",
                message="Narration contains low-value or overused prose phrases.",
                evidence=tuple(sorted(slop_phrase_hits)),
                count=len(slop_phrase_hits),
            )
        )
    if overlap_ratio > active_policy.recent_overlap_ratio_limit:
        issues.append(
            NarrationQualityIssue(
                kind="recent_overlap",
                severity="warning",
                message="Narration overlaps too heavily with recent transcript text.",
                evidence=(f"{overlap_ratio:.3f}",),
                count=1,
            )
        )

    rewrite_reasons = tuple(issue.kind for issue in issues if issue.severity in active_policy.rewrite_severities)
    return NarrationQualityReport(
        text_length=len(normalized),
        word_count=len(words),
        sentence_count=len(sentences),
        issues=tuple(issues),
        repeated_ngram_hits=repeated_ngram_hits,
        repeated_sentence_openings=repeated_sentence_openings,
        slop_phrase_hits=slop_phrase_hits,
        recent_overlap_ratio=overlap_ratio,
        should_request_rewrite=bool(rewrite_reasons),
        rewrite_reasons=rewrite_reasons,
    )


def build_safe_rewrite_contract(
    narration: str,
    *,
    state_facts: Mapping[str, object] | None = None,
    quality_report: NarrationQualityReport | None = None,
) -> dict[str, object]:
    """Build a presentation-only rewrite contract for a downstream LLM call.

    The returned payload is intentionally explicit: a rewrite may improve style,
    pacing, and specificity, but it may not add facts, outcomes, inventory,
    currency, location, combat, quest, or relationship changes not already present
    in the supplied state facts.
    """

    report = quality_report or evaluate_narration_quality(narration)
    return {
        "task": "presentation_rewrite_only",
        "source_narration": normalize_narration_text(narration),
        "state_facts": dict(state_facts or {}),
        "quality_report": report.as_dict(),
        "rewrite_requested": report.should_request_rewrite,
        "rewrite_reasons": list(report.rewrite_reasons),
        "rules": [
            "Preserve every supplied state fact exactly.",
            "Do not add inventory, currency, XP, location, quest, combat, party, or relationship changes.",
            "Do not imply hidden events became known to the player.",
            "Do not change speaker identity, NPC names, item names, or resolved outcomes.",
            "Improve only wording, specificity, pacing, and repetition.",
            "Return only the rewritten narration text.",
        ],
    }
