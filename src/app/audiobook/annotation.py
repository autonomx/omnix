"""Classifier-only interpretation over immutable span IDs."""
from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid5

from .models import SourceSpan


_NAMESPACE = UUID("3479391a-d9f4-4ecb-bce0-210e03a3334f")
_ROLES = {"narration", "dialogue", "heading", "other"}
_RESPONSE_FIELDS = {"span_id", "speaker", "role", "delivery"}


@dataclass(frozen=True, slots=True)
class Speaker:
    id: str
    canonical_name: str
    kind: str = "character"


@dataclass(frozen=True, slots=True)
class SpeakerAlias:
    alias: str
    speaker_id: str
    status: str = "proposed"


@dataclass(frozen=True, slots=True)
class SpanAnnotation:
    span_id: str
    role: str
    speaker_id: str
    speaker_candidate: str | None
    delivery: str
    review_reason: str | None
    evidence: dict[str, Any]


def narrator_id(project_id: str) -> str:
    return str(uuid5(_NAMESPACE, f"{project_id}:narrator"))


def resolve_speaker(label: str, speakers: Sequence[Speaker], aliases: Sequence[SpeakerAlias]) -> str | None:
    """Only exact canonical names and confirmed aliases resolve automatically."""
    normalized = label.strip().casefold()
    matched = {speaker.id for speaker in speakers if speaker.canonical_name.casefold() == normalized}
    matched.update(alias.speaker_id for alias in aliases
                   if alias.status == "confirmed" and alias.alias.strip().casefold() == normalized)
    return next(iter(matched)) if len(matched) == 1 else None


def _parse_classification(value: str | dict[str, Any], span_id: str) -> dict[str, str]:
    payload = json.loads(value) if isinstance(value, str) else value
    if not isinstance(payload, dict) or set(payload) != _RESPONSE_FIELDS:
        raise ValueError("classification must contain only span_id, speaker, role, delivery")
    if payload["span_id"] != span_id or payload["role"] not in _ROLES:
        raise ValueError("classification span ID or role is invalid")
    if not all(isinstance(payload[key], str) for key in _RESPONSE_FIELDS):
        raise ValueError("classification fields must be strings")
    return payload


def _attribution_evidence(source_text: str, known_names: Sequence[str]) -> list[str]:
    # A narrow evidence detector: a nearby explicit attribution is a review hint,
    # never authority to rewrite source text or silently merge two speakers.
    found: list[str] = []
    for name in known_names:
        escaped = re.escape(name)
        if re.search(rf"\b(?:said|asked|replied)\s+{escaped}\b|\b{escaped}\s+(?:said|asked|replied)\b", source_text, re.I):
            found.append(name)
    return found


def annotate_spans(
    *, project_id: str, spans: Sequence[SourceSpan], speakers: Sequence[Speaker],
    aliases: Sequence[SpeakerAlias] = (), classifier: Callable[[dict[str, Any]], str | dict[str, Any]],
    context_window: int = 2,
) -> tuple[SpanAnnotation, ...]:
    narrator = narrator_id(project_id)
    roster = [speaker.canonical_name for speaker in speakers]
    result: list[SpanAnnotation] = []
    for index, span in enumerate(spans):
        context = {
            "span_id": span.id,
            "source_text": span.source_text,
            "before": [item.source_text for item in spans[max(0, index - context_window):index]],
            "after": [item.source_text for item in spans[index + 1:index + 1 + context_window]],
            "speaker_roster": [{"id": speaker.id, "name": speaker.canonical_name} for speaker in speakers],
            "task": "classify_only_no_source_text_in_response",
        }
        try:
            payload = _parse_classification(classifier(context), span.id)
        except Exception as exc:
            result.append(SpanAnnotation(
                span.id, span.structural_kind, narrator, None, "", "FALLBACK_NARRATOR",
                {"classification_error": type(exc).__name__},
            ))
            continue
        label = payload["speaker"].strip()
        role = payload["role"]
        if role == "dialogue" and span.structural_kind != "dialogue":
            result.append(SpanAnnotation(
                span.id, span.structural_kind, narrator, label or None, payload["delivery"],
                "STRUCTURE_UNCERTAIN", {"classifier_role": role, "structural_kind": span.structural_kind},
            ))
            continue
        speaker_id = narrator if role != "dialogue" or not label else resolve_speaker(label, speakers, aliases)
        reason = None
        if role == "dialogue" and speaker_id is None:
            speaker_id = narrator
            reason = "UNSUPPORTED_SPEAKER"
        evidence_text = " ".join(context["before"][-1:] + [span.source_text] + context["after"][:1])
        attribution = _attribution_evidence(evidence_text, roster)
        if role == "dialogue" and attribution:
            expected = {resolve_speaker(name, speakers, aliases) for name in attribution}
            if speaker_id not in expected:
                reason = "ATTRIBUTION_CONTRADICTION"
        result.append(SpanAnnotation(
            span.id, role, speaker_id, label or None, payload["delivery"], reason,
            {"attribution_names": attribution, "classifier_span_id": span.id},
        ))
    return tuple(result)
