"""Pure narration quality evaluation and safe rewrite contract helpers."""

from __future__ import annotations

from collections import Counter
import re
from typing import Iterable, Mapping, Sequence

from .types import NarrationQualityIssue, NarrationQualityPolicy, NarrationQualityReport

_WORD_RE = re.compile(r"[A-Za-z0-9']+")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_narration_text(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text or "").strip()


def narration_words(text: str) -> tuple[str, ...]:
    return tuple(match.group(0).lower() for match in _WORD_RE.finditer(text or ""))


def narration_sentences(text: str) -> tuple[str, ...]:
    normalized = normalize_narration_text(text)
    if not normalized:
        return ()
    return tuple(sentence.strip() for sentence in _SENTENCE_RE.split(normalized) if sentence.strip())


def _ngrams(words: Sequence[str], size: int) -> tuple[str, ...]:
    if size <= 0 or len(words) < size:
        return ()
    return tuple(" ".join(words[index : index + size]) for index in range(len(words) - size + 1))


def _repeated_counts(values: Iterable[str], limit: int) -> dict[str, int]:
    counts = Counter(value for value in values if value)
    return {value: count for value, count in counts.items() if count > limit}


def _sentence_openings(sentences: Sequence[str], opening_words: int) -> tuple[str, ...]:
    openings: list[str] = []
    for sentence in sentences:
        words = narration_words(sentence)
        if words:
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


def _quality_issue(kind: str, message: str, hits: Mapping[str, int]) -> NarrationQualityIssue:
    return NarrationQualityIssue(kind, "warning", message, tuple(sorted(hits)), sum(hits.values()))


def _quality_issues(
    repeated_ngram_hits: Mapping[str, int],
    repeated_sentence_openings: Mapping[str, int],
    slop_phrase_hits: Sequence[str],
    overlap_ratio: float,
    policy: NarrationQualityPolicy,
) -> tuple[NarrationQualityIssue, ...]:
    issues: list[NarrationQualityIssue] = []
    if repeated_ngram_hits:
        issues.append(_quality_issue("repeated_ngram", "Narration repeats the same phrase.", repeated_ngram_hits))
    if repeated_sentence_openings:
        issues.append(_quality_issue("repeated_sentence_opening", "Multiple sentences share opening words.", repeated_sentence_openings))
    if slop_phrase_hits:
        issues.append(
            NarrationQualityIssue(
                "slop_phrase",
                "warning",
                "Narration contains low-value or overused prose phrases.",
                tuple(sorted(slop_phrase_hits)),
                len(slop_phrase_hits),
            )
        )
    if overlap_ratio > policy.recent_overlap_ratio_limit:
        issues.append(
            NarrationQualityIssue(
                "recent_overlap",
                "warning",
                "Narration overlaps too heavily with recent transcript text.",
                (f"{overlap_ratio:.3f}",),
            )
        )
    return tuple(issues)


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
        _sentence_openings(sentences, active_policy.sentence_opening_words),
        active_policy.repeated_sentence_opening_limit,
    )
    slop_phrase_hits = _slop_hits(normalized, active_policy.slop_phrases)
    overlap_ratio = _recent_overlap_ratio(words, recent_texts, active_policy)
    issues = _quality_issues(repeated_ngram_hits, repeated_sentence_openings, slop_phrase_hits, overlap_ratio, active_policy)
    rewrite_reasons = tuple(issue.kind for issue in issues if issue.severity in active_policy.rewrite_severities)
    return NarrationQualityReport(
        text_length=len(normalized),
        word_count=len(words),
        sentence_count=len(sentences),
        issues=issues,
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
    """Build a presentation-only downstream rewrite request."""

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
