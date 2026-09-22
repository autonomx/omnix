"""Story/dialogue interpretation over immutable source span IDs."""
from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid5

from .models import SourceSpan


_NAMESPACE = UUID("3479391a-d9f4-4ecb-bce0-210e03a3334f")
_ROLES = {"narration", "dialogue", "heading", "other"}
_RESPONSE_FIELDS = {"span_id", "speaker", "role", "delivery"}
_BATCH_RESPONSE_FIELDS = {"characters", "spans"}
_BATCH_SPAN_FIELDS = {"span_id", "speaker", "role", "delivery", "confidence"}
_CHARACTER_FIELDS = {"name", "aliases"}
_LOW_CONFIDENCE_REVIEW_THRESHOLD = 0.75
_ATTRIBUTION_VERBS = (
    "said", "asked", "replied", "answered", "shouted", "yelled", "whispered",
    "muttered", "murmured", "cried", "called", "snapped", "growled", "hissed",
    "sighed", "added", "continued", "insisted", "warned", "ordered", "demanded",
    "exclaimed", "remarked", "responded",
)
_ATTRIBUTION_VERB_RE = "|".join(re.escape(item) for item in _ATTRIBUTION_VERBS)


@dataclass(frozen=True, slots=True)
class Speaker:
    id: str
    canonical_name: str
    kind: str = "character"
    status: str = "active"


@dataclass(frozen=True, slots=True)
class SpeakerAlias:
    alias: str
    speaker_id: str
    status: str = "proposed"


@dataclass(frozen=True, slots=True)
class DiscoveredSpeaker:
    canonical_name: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SpanAnnotation:
    span_id: str
    role: str
    speaker_id: str
    speaker_candidate: str | None
    delivery: str
    review_reason: str | None
    evidence: dict[str, Any]
    confidence: float = 1.0


@dataclass(frozen=True, slots=True)
class BatchAnalysis:
    annotations: tuple[SpanAnnotation, ...]
    discovered_speakers: tuple[DiscoveredSpeaker, ...]


def narrator_id(project_id: str) -> str:
    return str(uuid5(_NAMESPACE, f"{project_id}:narrator"))


def normalize_speaker_name(label: str) -> str:
    """Return one Unicode/whitespace/case normalized identity form."""
    normalized = unicodedata.normalize("NFKC", label)
    return " ".join(normalized.strip().split()).casefold()


def display_speaker_name(label: str) -> str:
    """Collapse presentation whitespace without changing the user's spelling."""
    return " ".join(unicodedata.normalize("NFKC", label).strip().split())


def proposed_speaker_id(project_id: str, label: str) -> str:
    """Derive an idempotent UUID for an unconfirmed detected speaker."""
    normalized = normalize_speaker_name(label)
    if not normalized:
        raise ValueError("speaker candidate is required")
    return str(uuid5(_NAMESPACE, f"{project_id}:proposed-speaker:{normalized}"))


def resolve_speaker(
    label: str, speakers: Sequence[Speaker], aliases: Sequence[SpeakerAlias],
) -> str | None:
    """Resolve only active canonical identities or confirmed aliases.

    Proposed speakers are deliberately supplied to later classifier batches as
    context, but they remain uncastable and unresolved until a user confirms
    them. A classifier may also return a known speaker UUID directly.
    """
    normalized = normalize_speaker_name(label)
    if not normalized:
        return None
    direct = {
        speaker.id for speaker in speakers
        if speaker.status == "active" and normalize_speaker_name(speaker.id) == normalized
    }
    matched = {
        speaker.id for speaker in speakers
        if speaker.status == "active"
        and normalize_speaker_name(speaker.canonical_name) == normalized
    }
    matched.update(direct)
    matched.update(
        alias.speaker_id
        for alias in aliases
        if alias.status == "confirmed" and normalize_speaker_name(alias.alias) == normalized
    )
    return next(iter(matched)) if len(matched) == 1 else None


def _load_payload(value: str | dict[str, Any]) -> dict[str, Any]:
    payload = json.loads(value) if isinstance(value, str) else value
    if not isinstance(payload, dict):
        raise ValueError("classification response must be an object")
    return payload


def _parse_classification(value: str | dict[str, Any], span_id: str) -> dict[str, Any]:
    payload = _load_payload(value)
    fields = set(payload)
    if fields not in {_RESPONSE_FIELDS, _RESPONSE_FIELDS | {"confidence"}}:
        raise ValueError(
            "classification must contain span_id, speaker, role, delivery and optional confidence"
        )
    if payload.get("span_id") != span_id or payload.get("role") not in _ROLES:
        raise ValueError("classification span ID or role is invalid")
    if not all(isinstance(payload.get(key), str) for key in _RESPONSE_FIELDS):
        raise ValueError("classification fields must be strings")
    confidence = payload.get("confidence", 1.0)
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ValueError("classification confidence must be numeric")
    confidence = float(confidence)
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("classification confidence must be between zero and one")
    return {**payload, "confidence": confidence}


def _parse_batch_classification(
    value: str | dict[str, Any], expected_span_ids: Sequence[str],
) -> tuple[list[dict[str, Any]], list[DiscoveredSpeaker]]:
    payload = _load_payload(value)
    # Compatibility with test hooks and older custom classifiers. A one-span
    # batch may return the legacy single-span contract.
    if set(payload) in {_RESPONSE_FIELDS, _RESPONSE_FIELDS | {"confidence"}}:
        if len(expected_span_ids) != 1:
            raise ValueError("legacy classification cannot cover a multi-span batch")
        return [_parse_classification(payload, expected_span_ids[0])], []

    if set(payload) != _BATCH_RESPONSE_FIELDS:
        raise ValueError("batch classification must contain only characters and spans")
    raw_characters = payload["characters"]
    raw_spans = payload["spans"]
    if not isinstance(raw_characters, list) or not isinstance(raw_spans, list):
        raise ValueError("batch characters and spans must be arrays")

    discovered: list[DiscoveredSpeaker] = []
    seen_characters: set[str] = set()
    for item in raw_characters:
        if not isinstance(item, dict) or set(item) != _CHARACTER_FIELDS:
            raise ValueError("character discovery must contain only name and aliases")
        name = item.get("name")
        aliases = item.get("aliases")
        if not isinstance(name, str) or not isinstance(aliases, list) or not all(
            isinstance(alias, str) for alias in aliases
        ):
            raise ValueError("character discovery fields are invalid")
        display_name = display_speaker_name(name)
        normalized = normalize_speaker_name(display_name)
        if not normalized or normalized in seen_characters:
            continue
        seen_characters.add(normalized)
        clean_aliases: list[str] = []
        seen_aliases = {normalized}
        for alias in aliases:
            clean = display_speaker_name(alias)
            key = normalize_speaker_name(clean)
            if clean and key not in seen_aliases:
                seen_aliases.add(key)
                clean_aliases.append(clean)
        discovered.append(DiscoveredSpeaker(display_name, tuple(clean_aliases)))

    parsed_spans: list[dict[str, Any]] = []
    seen_span_ids: set[str] = set()
    expected = set(expected_span_ids)
    for item in raw_spans:
        if not isinstance(item, dict) or set(item) != _BATCH_SPAN_FIELDS:
            raise ValueError(
                "batch span must contain only span_id, speaker, role, delivery, confidence"
            )
        span_id = item.get("span_id")
        if not isinstance(span_id, str) or span_id not in expected or span_id in seen_span_ids:
            raise ValueError("batch span ID is missing, duplicated, or unexpected")
        if item.get("role") not in _ROLES:
            raise ValueError("batch span role is invalid")
        if not all(isinstance(item.get(key), str) for key in ("speaker", "role", "delivery")):
            raise ValueError("batch speaker, role, and delivery must be strings")
        confidence = item.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise ValueError("batch confidence must be numeric")
        confidence = float(confidence)
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("batch confidence must be between zero and one")
        seen_span_ids.add(span_id)
        parsed_spans.append({**item, "confidence": confidence})
    if seen_span_ids != expected:
        raise ValueError("batch classification must cover every requested span exactly once")
    return parsed_spans, discovered


def _attribution_evidence(source_text: str, known_names: Sequence[str]) -> list[str]:
    # Explicit nearby dialogue tags are review evidence, not authority to alter
    # immutable text or silently merge identities.
    found: list[str] = []
    for name in known_names:
        escaped = re.escape(name)
        patterns = (
            rf"\b(?:{_ATTRIBUTION_VERB_RE})\s+{escaped}\b",
            rf"\b{escaped}\s+(?:{_ATTRIBUTION_VERB_RE})\b",
        )
        if any(re.search(pattern, source_text, re.I) for pattern in patterns):
            found.append(name)
    return found


def _annotation_from_payload(
    *, project_id: str, span: SourceSpan, payload: dict[str, Any],
    speakers: Sequence[Speaker], aliases: Sequence[SpeakerAlias],
    evidence_text: str,
) -> SpanAnnotation:
    narrator = narrator_id(project_id)
    label = display_speaker_name(str(payload["speaker"]))
    role = str(payload["role"])
    delivery = str(payload["delivery"])
    confidence = float(payload.get("confidence", 1.0))
    if role == "dialogue" and span.structural_kind != "dialogue":
        return SpanAnnotation(
            span.id, span.structural_kind, narrator, label or None, delivery,
            "STRUCTURE_UNCERTAIN",
            {"classifier_role": role, "structural_kind": span.structural_kind,
             "confidence": confidence},
            confidence,
        )
    if span.structural_kind == "dialogue" and role != "dialogue":
        return SpanAnnotation(
            span.id, span.structural_kind, narrator, label or None, delivery,
            "STRUCTURE_UNCERTAIN",
            {"classifier_role": role, "structural_kind": span.structural_kind,
             "confidence": confidence},
            confidence,
        )

    speaker_id = narrator if role != "dialogue" or not label else resolve_speaker(
        label, speakers, aliases,
    )
    reason: str | None = None
    if role == "dialogue" and speaker_id is None:
        speaker_id = narrator
        reason = "UNSUPPORTED_SPEAKER"
    elif (
        role == "dialogue"
        and speaker_id != narrator
        and confidence < _LOW_CONFIDENCE_REVIEW_THRESHOLD
    ):
        reason = "LOW_CONFIDENCE_SPEAKER"

    roster = [speaker.canonical_name for speaker in speakers if speaker.status == "active"]
    attribution = _attribution_evidence(evidence_text, roster)
    if role == "dialogue" and attribution:
        expected = {
            resolve_speaker(name, speakers, aliases) for name in attribution
        }
        if speaker_id not in expected:
            reason = "ATTRIBUTION_CONTRADICTION"
    return SpanAnnotation(
        span.id, role, speaker_id, label or None, delivery, reason,
        {
            "attribution_names": attribution,
            "classifier_span_id": span.id,
            "confidence": confidence,
        },
        confidence,
    )


def annotate_spans(
    *, project_id: str, spans: Sequence[SourceSpan], speakers: Sequence[Speaker],
    aliases: Sequence[SpeakerAlias] = (),
    classifier: Callable[[dict[str, Any]], str | dict[str, Any]],
    context_window: int = 2,
) -> tuple[SpanAnnotation, ...]:
    """Legacy single-span classifier path retained for compatibility/tests."""
    narrator = narrator_id(project_id)
    result: list[SpanAnnotation] = []
    for index, span in enumerate(spans):
        context = {
            "span_id": span.id,
            "source_text": span.source_text,
            "before": [item.source_text for item in spans[max(0, index - context_window):index]],
            "after": [item.source_text for item in spans[index + 1:index + 1 + context_window]],
            "speaker_roster": [
                {"id": speaker.id, "name": speaker.canonical_name, "status": speaker.status}
                for speaker in speakers
            ],
            "task": "classify_only_no_source_text_in_response",
        }
        try:
            payload = _parse_classification(classifier(context), span.id)
        except Exception as exc:
            retry_context = {
                **context,
                "before": [item.source_text for item in spans[max(0, index - 2 * context_window):index]],
                "after": [item.source_text for item in spans[index + 1:index + 1 + 2 * context_window]],
                "task": "retry_classification_only_no_source_text_in_response",
                "previous_error": type(exc).__name__,
            }
            try:
                payload = _parse_classification(classifier(retry_context), span.id)
            except Exception as retry_exc:
                result.append(SpanAnnotation(
                    span.id, span.structural_kind, narrator, None, "",
                    "FALLBACK_NARRATOR",
                    {"classification_error": type(exc).__name__,
                     "retry_error": type(retry_exc).__name__, "confidence": 0.0},
                    0.0,
                ))
                continue
        evidence_text = " ".join(
            context["before"][-1:] + [span.source_text] + context["after"][:1]
        )
        result.append(_annotation_from_payload(
            project_id=project_id, span=span, payload=payload,
            speakers=speakers, aliases=aliases, evidence_text=evidence_text,
        ))
    return tuple(result)


def annotate_span_batches(
    *, project_id: str, spans: Sequence[SourceSpan], speakers: Sequence[Speaker],
    aliases: Sequence[SpeakerAlias] = (),
    classifier: Callable[[dict[str, Any]], str | dict[str, Any]],
    batch_size: int = 40, context_window: int = 3,
) -> BatchAnalysis:
    """Analyze story structure in bounded batches with a rolling character roster.

    Source prose is input-only. The model returns span IDs and interpretation
    metadata, while newly discovered characters are fed into later batches as
    provisional context. They are never automatically promoted to an active,
    castable identity.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    narrator = narrator_id(project_id)
    rolling_speakers = list(speakers)
    rolling_aliases = list(aliases)
    all_annotations: list[SpanAnnotation] = []
    discoveries: dict[str, DiscoveredSpeaker] = {
        normalize_speaker_name(speaker.canonical_name): DiscoveredSpeaker(
            speaker.canonical_name, (),
        )
        for speaker in rolling_speakers
        if speaker.status == "proposed"
    }

    for start in range(0, len(spans), batch_size):
        chunk = list(spans[start:start + batch_size])
        expected_ids = [span.id for span in chunk]
        before = spans[max(0, start - context_window):start]
        after = spans[start + len(chunk):start + len(chunk) + context_window]
        aliases_by_speaker: dict[str, list[str]] = {}
        for alias in rolling_aliases:
            aliases_by_speaker.setdefault(alias.speaker_id, []).append(alias.alias)
        context = {
            "task": "analyze_story_dialogue_batch_no_source_text_in_response",
            "span_ids": expected_ids,
            "spans": [
                {
                    "span_id": span.id,
                    "source_text": span.source_text,
                    "structural_kind": span.structural_kind,
                }
                for span in chunk
            ],
            "context_before": [item.source_text for item in before],
            "context_after": [item.source_text for item in after],
            "speaker_roster": [
                {
                    "id": speaker.id,
                    "name": speaker.canonical_name,
                    "status": speaker.status,
                    "aliases": aliases_by_speaker.get(speaker.id, []),
                }
                for speaker in rolling_speakers
            ],
        }
        try:
            raw = classifier(context)
            parsed, discovered = _parse_batch_classification(raw, expected_ids)
        except KeyError:
            # Older custom hooks may only understand the legacy per-span
            # payload. Keep them working without penalizing the normal v3 path.
            legacy = annotate_spans(
                project_id=project_id, spans=chunk, speakers=rolling_speakers,
                aliases=rolling_aliases, classifier=classifier,
                context_window=context_window,
            )
            all_annotations.extend(legacy)
            for annotation in legacy:
                if (
                    annotation.role == "dialogue"
                    and annotation.speaker_candidate
                    and annotation.speaker_id == narrator
                    and normalize_speaker_name(annotation.speaker_candidate) != "narrator"
                ):
                    key = normalize_speaker_name(annotation.speaker_candidate)
                    discoveries.setdefault(
                        key, DiscoveredSpeaker(
                            display_speaker_name(annotation.speaker_candidate), (),
                        ),
                    )
            continue
        except Exception as exc:
            retry_context = {
                **context,
                "task": "retry_story_dialogue_batch_no_source_text_in_response",
                "previous_error": type(exc).__name__,
                "context_before": [
                    item.source_text
                    for item in spans[max(0, start - 2 * context_window):start]
                ],
                "context_after": [
                    item.source_text
                    for item in spans[
                        start + len(chunk):
                        start + len(chunk) + 2 * context_window
                    ]
                ],
            }
            try:
                parsed, discovered = _parse_batch_classification(
                    classifier(retry_context), expected_ids,
                )
            except Exception as retry_exc:
                all_annotations.extend(
                    SpanAnnotation(
                        span.id, span.structural_kind, narrator, None, "",
                        "FALLBACK_NARRATOR",
                        {"classification_error": type(exc).__name__,
                         "retry_error": type(retry_exc).__name__,
                         "confidence": 0.0},
                        0.0,
                    )
                    for span in chunk
                )
                continue

        for discovered in discovered:
            key = normalize_speaker_name(discovered.canonical_name)
            if not key or key == "narrator":
                continue
            previous = discoveries.get(key)
            if previous is None:
                discoveries[key] = discovered
                provisional = Speaker(
                    proposed_speaker_id(project_id, discovered.canonical_name),
                    discovered.canonical_name,
                    "character",
                    "proposed",
                )
                rolling_speakers.append(provisional)
                rolling_aliases.extend(
                    SpeakerAlias(alias, provisional.id, "proposed")
                    for alias in discovered.aliases
                )
            elif discovered.aliases:
                merged = tuple(dict.fromkeys((*previous.aliases, *discovered.aliases)))
                discoveries[key] = DiscoveredSpeaker(previous.canonical_name, merged)

        payload_by_id = {str(item["span_id"]): item for item in parsed}
        for local_index, span in enumerate(chunk):
            global_index = start + local_index
            evidence_parts = [
                item.source_text
                for item in spans[max(0, global_index - 1):global_index]
            ]
            evidence_parts.append(span.source_text)
            evidence_parts.extend(
                item.source_text
                for item in spans[global_index + 1:global_index + 2]
            )
            annotation = _annotation_from_payload(
                project_id=project_id,
                span=span,
                payload=payload_by_id[span.id],
                speakers=rolling_speakers,
                aliases=rolling_aliases,
                evidence_text=" ".join(evidence_parts),
            )
            all_annotations.append(annotation)
            if (
                annotation.role == "dialogue"
                and annotation.speaker_candidate
                and annotation.speaker_id == narrator
                and normalize_speaker_name(annotation.speaker_candidate) != "narrator"
            ):
                key = normalize_speaker_name(annotation.speaker_candidate)
                if key not in discoveries:
                    discovered = DiscoveredSpeaker(
                        display_speaker_name(annotation.speaker_candidate), (),
                    )
                    discoveries[key] = discovered
                    rolling_speakers.append(Speaker(
                        proposed_speaker_id(project_id, discovered.canonical_name),
                        discovered.canonical_name,
                        "character",
                        "proposed",
                    ))

    existing_keys = {
        normalize_speaker_name(speaker.canonical_name)
        for speaker in speakers
        if speaker.status == "active"
    }
    return BatchAnalysis(
        tuple(all_annotations),
        tuple(
            discovery for key, discovery in discoveries.items()
            if key not in existing_keys
        ),
    )
