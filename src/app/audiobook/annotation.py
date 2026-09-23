"""Story/dialogue interpretation over immutable source span IDs."""
from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid5

from .models import SourceSpan
from .classification_logging import classification_log


_NAMESPACE = UUID("3479391a-d9f4-4ecb-bce0-210e03a3334f")
_ROLES = {"narration", "dialogue", "heading", "other"}
_RESPONSE_FIELDS = {"span_id", "speaker", "role", "delivery"}
_BATCH_RESPONSE_FIELDS = {"characters", "spans"}
_BATCH_SPAN_FIELDS = {"span_id", "speaker", "role", "delivery", "confidence"}
_CHARACTER_REQUIRED_FIELDS = {"name", "aliases"}
_CHARACTER_OPTIONAL_FIELDS = {
    "role", "traits", "estimated_age", "gender_presentation",
}
_LOW_CONFIDENCE_REVIEW_THRESHOLD = 0.75
_ATTRIBUTION_VERBS = (
    "said", "asked", "replied", "answered", "shouted", "yelled", "whispered",
    "muttered", "murmured", "cried", "called", "snapped", "growled", "hissed",
    "sighed", "added", "continued", "insisted", "warned", "ordered", "demanded",
    "exclaimed", "remarked", "responded",
)
_ATTRIBUTION_VERB_RE = "|".join(re.escape(item) for item in _ATTRIBUTION_VERBS)


def _log_classification_event(
    event: str, log_context: Mapping[str, Any] | None = None, **details: Any,
) -> None:
    fields = dict(log_context or {})
    fields.update(details)
    classification_log(event, **fields)


class _LegacyBatchContract(ValueError):
    """Signal that a classifier only supports the pre-v3 single-span contract."""


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
    role: str = ""
    traits: tuple[str, ...] = ()
    estimated_age: str = ""
    gender_presentation: str = ""


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
    if fields != _RESPONSE_FIELDS and fields != (_RESPONSE_FIELDS | {"confidence"}):
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
    payload_fields = set(payload)
    if payload_fields == _RESPONSE_FIELDS or payload_fields == (_RESPONSE_FIELDS | {"confidence"}):
        if len(expected_span_ids) != 1:
            raise _LegacyBatchContract(
                "legacy classification cannot cover a multi-span batch"
            )
        return [_parse_classification(payload, expected_span_ids[0])], []

    if payload_fields != _BATCH_RESPONSE_FIELDS:
        raise ValueError("batch classification must contain only characters and spans")
    raw_characters = payload["characters"]
    raw_spans = payload["spans"]
    if not isinstance(raw_characters, list) or not isinstance(raw_spans, list):
        raise ValueError("batch characters and spans must be arrays")

    discovered: list[DiscoveredSpeaker] = []
    seen_characters: set[str] = set()
    for item in raw_characters:
        if not isinstance(item, dict):
            raise ValueError("character discovery must be an object")
        fields = set(item)
        if (
            not _CHARACTER_REQUIRED_FIELDS.issubset(fields)
            or not fields.issubset(_CHARACTER_REQUIRED_FIELDS | _CHARACTER_OPTIONAL_FIELDS)
        ):
            raise ValueError("character discovery fields are invalid")
        name = item.get("name")
        aliases = item.get("aliases")
        traits = item.get("traits", [])
        if (
            not isinstance(name, str)
            or not isinstance(aliases, list)
            or not all(isinstance(alias, str) for alias in aliases)
            or not isinstance(traits, list)
            or not all(isinstance(trait, str) for trait in traits)
        ):
            raise ValueError("character discovery fields are invalid")
        for optional in ("role", "estimated_age", "gender_presentation"):
            if optional in item and not isinstance(item[optional], str):
                raise ValueError("character discovery metadata must be strings")
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
        clean_traits = tuple(
            dict.fromkeys(
                display_speaker_name(trait)
                for trait in traits
                if display_speaker_name(trait)
            )
        )
        discovered.append(DiscoveredSpeaker(
            display_name,
            tuple(clean_aliases),
            display_speaker_name(str(item.get("role", ""))),
            clean_traits,
            display_speaker_name(str(item.get("estimated_age", ""))),
            display_speaker_name(str(item.get("gender_presentation", ""))),
        ))

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
    raw_label = display_speaker_name(str(payload["speaker"]))
    id_match = next(
        (
            speaker for speaker in speakers
            if normalize_speaker_name(speaker.id) == normalize_speaker_name(raw_label)
        ),
        None,
    )
    label = id_match.canonical_name if id_match is not None else raw_label
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
        raw_label, speakers, aliases,
    )
    reason: str | None = None
    if role == "dialogue" and speaker_id is None:
        speaker_id = narrator
        reason = "UNSUPPORTED_SPEAKER"
    elif role == "dialogue" and speaker_id == narrator:
        reason = "NARRATOR_DIALOGUE_UNCERTAIN"
    elif (
        role == "dialogue"
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
    log_context: Mapping[str, Any] | None = None,
) -> tuple[SpanAnnotation, ...]:
    """Legacy single-span classifier path retained for compatibility/tests."""
    narrator = narrator_id(project_id)
    result: list[SpanAnnotation] = []
    _log_classification_event(
        "classification_legacy_started",
        log_context,
        project_id=project_id,
        span_count=len(spans),
        context_window=context_window,
        speaker_roster=[
            {"id": speaker.id, "name": speaker.canonical_name, "status": speaker.status}
            for speaker in speakers
        ],
    )
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
        raw_result: object = None
        _log_classification_event(
            "classification_request",
            log_context,
            project_id=project_id,
            mode="single",
            attempt="initial",
            span_id=span.id,
            chapter_id=span.chapter_id,
            structural_kind=span.structural_kind,
            request=context,
        )
        try:
            raw_result = classifier(context)
            _log_classification_event(
                "classification_response",
                log_context,
                project_id=project_id,
                mode="single",
                attempt="initial",
                span_id=span.id,
                raw_response=raw_result,
            )
            payload = _parse_classification(raw_result, span.id)
            _log_classification_event(
                "classification_parsed",
                log_context,
                project_id=project_id,
                mode="single",
                attempt="initial",
                span_id=span.id,
                parsed=payload,
            )
        except Exception as exc:
            _log_classification_event(
                "classification_parse_failed",
                log_context,
                project_id=project_id,
                mode="single",
                attempt="initial",
                span_id=span.id,
                error_type=type(exc).__name__,
                error=str(exc),
                failure_stage="parser" if raw_result is not None else "classifier_call",
                raw_response=raw_result,
            )
            retry_context = {
                **context,
                "before": [item.source_text for item in spans[max(0, index - 2 * context_window):index]],
                "after": [item.source_text for item in spans[index + 1:index + 1 + 2 * context_window]],
                "task": "retry_classification_only_no_source_text_in_response",
                "previous_error": type(exc).__name__,
            }
            retry_result: object = None
            _log_classification_event(
                "classification_request",
                log_context,
                project_id=project_id,
                mode="single",
                attempt="retry",
                span_id=span.id,
                chapter_id=span.chapter_id,
                structural_kind=span.structural_kind,
                request=retry_context,
            )
            try:
                retry_result = classifier(retry_context)
                _log_classification_event(
                    "classification_response",
                    log_context,
                    project_id=project_id,
                    mode="single",
                    attempt="retry",
                    span_id=span.id,
                    raw_response=retry_result,
                )
                payload = _parse_classification(retry_result, span.id)
                _log_classification_event(
                    "classification_parsed",
                    log_context,
                    project_id=project_id,
                    mode="single",
                    attempt="retry",
                    span_id=span.id,
                    parsed=payload,
                )
            except Exception as retry_exc:
                _log_classification_event(
                    "classification_fallback",
                    log_context,
                    project_id=project_id,
                    mode="single",
                    span_id=span.id,
                    reason="retry_failed",
                    initial_error_type=type(exc).__name__,
                    initial_error=str(exc),
                    retry_error_type=type(retry_exc).__name__,
                    retry_error=str(retry_exc),
                    retry_response=retry_result,
                    fallback_speaker_id=narrator,
                    fallback_review_reason="FALLBACK_NARRATOR",
                )
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
        annotation = result[-1]
        _log_classification_event(
            "classification_annotation",
            log_context,
            project_id=project_id,
            mode="single",
            span_id=span.id,
            annotation=annotation,
        )
    _log_classification_event(
        "classification_legacy_completed",
        log_context,
        project_id=project_id,
        span_count=len(result),
        review_count=sum(item.review_reason is not None for item in result),
    )
    return tuple(result)


def annotate_span_batches(
    *, project_id: str, spans: Sequence[SourceSpan], speakers: Sequence[Speaker],
    aliases: Sequence[SpeakerAlias] = (),
    classifier: Callable[[dict[str, Any]], str | dict[str, Any]],
    batch_size: int = 40, context_window: int = 3,
    log_context: Mapping[str, Any] | None = None,
) -> BatchAnalysis:
    """Analyze dialogue in bounded batches with a rolling character roster.

    Narration is structurally authoritative and assigned to the narrator without
    an LLM call. Dialogue spans are batched, with nearby immutable narration
    supplied as context for attribution. Newly discovered people immediately
    become provisional context for later batches, but never become castable
    until the user confirms them.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    narrator = narrator_id(project_id)
    rolling_speakers = list(speakers)
    rolling_aliases = list(aliases)
    annotations_by_id: dict[str, SpanAnnotation] = {}
    discoveries: dict[str, DiscoveredSpeaker] = {
        normalize_speaker_name(speaker.canonical_name): DiscoveredSpeaker(
            speaker.canonical_name, (),
        )
        for speaker in rolling_speakers
        if speaker.status == "proposed"
    }

    # Structural narration does not need model inference. Keeping it out of the
    # request is the main full-book performance win; it still appears around
    # dialogue as attribution context below.
    for span in spans:
        if span.structural_kind != "dialogue":
            annotations_by_id[span.id] = SpanAnnotation(
                span.id,
                span.structural_kind,
                narrator,
                None,
                "",
                None,
                {
                    "deterministic_structural_role": span.structural_kind,
                    "confidence": 1.0,
                },
                1.0,
            )

    def merge_discovery(discovered: DiscoveredSpeaker) -> None:
        key = normalize_speaker_name(discovered.canonical_name)
        if not key or key == "narrator":
            return
        existing_speaker = next(
            (
                speaker for speaker in rolling_speakers
                if normalize_speaker_name(speaker.canonical_name) == key
            ),
            None,
        )
        previous = discoveries.get(key)
        if existing_speaker is not None:
            previous = previous or DiscoveredSpeaker(
                existing_speaker.canonical_name, (),
            )
            merged = tuple(dict.fromkeys((*previous.aliases, *discovered.aliases)))
            merged_discovery = DiscoveredSpeaker(
                previous.canonical_name,
                merged,
                discovered.role or previous.role,
                tuple(dict.fromkeys((*previous.traits, *discovered.traits))),
                discovered.estimated_age or previous.estimated_age,
                discovered.gender_presentation or previous.gender_presentation,
            )
            if (
                existing_speaker.status == "proposed"
                or merged_discovery.aliases
                or merged_discovery.role
                or merged_discovery.traits
                or merged_discovery.estimated_age
                or merged_discovery.gender_presentation
            ):
                discoveries[key] = merged_discovery
            if discovered.aliases:
                known_aliases = {
                    normalize_speaker_name(alias.alias)
                    for alias in rolling_aliases
                    if alias.speaker_id == existing_speaker.id
                }
                rolling_aliases.extend(
                    SpeakerAlias(alias, existing_speaker.id, "proposed")
                    for alias in discovered.aliases
                    if normalize_speaker_name(alias) not in known_aliases
                )
            return

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
            return

        merged = tuple(dict.fromkeys((*previous.aliases, *discovered.aliases)))
        discoveries[key] = DiscoveredSpeaker(
            previous.canonical_name,
            merged,
            discovered.role or previous.role,
            tuple(dict.fromkeys((*previous.traits, *discovered.traits))),
            discovered.estimated_age or previous.estimated_age,
            discovered.gender_presentation or previous.gender_presentation,
        )

    def record_unknown_candidate(annotation: SpanAnnotation) -> None:
        if (
            annotation.role == "dialogue"
            and annotation.speaker_candidate
            and annotation.speaker_id == narrator
            and normalize_speaker_name(annotation.speaker_candidate) != "narrator"
        ):
            merge_discovery(DiscoveredSpeaker(
                display_speaker_name(annotation.speaker_candidate), (),
            ))

    dialogue_entries = [
        (index, span)
        for index, span in enumerate(spans)
        if span.structural_kind == "dialogue"
    ]
    _log_classification_event(
        "classification_batches_started",
        log_context,
        project_id=project_id,
        chapter_id=spans[0].chapter_id if spans else None,
        span_count=len(spans),
        dialogue_span_count=len(dialogue_entries),
        batch_size=batch_size,
        context_window=context_window,
        speaker_roster=[
            {"id": speaker.id, "name": speaker.canonical_name, "status": speaker.status}
            for speaker in rolling_speakers
        ],
    )
    for batch_start in range(0, len(dialogue_entries), batch_size):
        batch_number = batch_start // batch_size + 1
        entries = dialogue_entries[batch_start:batch_start + batch_size]
        chunk = [span for _index, span in entries]
        expected_ids = [span.id for span in chunk]
        aliases_by_speaker: dict[str, list[str]] = {}
        for alias in rolling_aliases:
            aliases_by_speaker.setdefault(alias.speaker_id, []).append(alias.alias)

        request_spans: list[dict[str, Any]] = []
        for global_index, span in entries:
            before = spans[max(0, global_index - context_window):global_index]
            after = spans[
                global_index + 1:
                min(len(spans), global_index + 1 + context_window)
            ]
            request_spans.append({
                "span_id": span.id,
                "source_text": span.source_text,
                "structural_kind": span.structural_kind,
                "before": [item.source_text for item in before],
                "after": [item.source_text for item in after],
            })
        context = {
            "task": "analyze_story_dialogue_batch_no_source_text_in_response",
            "span_ids": expected_ids,
            "spans": request_spans,
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

        _log_classification_event(
            "classification_batch_request",
            log_context,
            project_id=project_id,
            chapter_id=chunk[0].chapter_id if chunk else None,
            mode="batch",
            batch_number=batch_number,
            attempt="initial",
            expected_span_ids=expected_ids,
            request=context,
        )
        raw_result: object = None
        try:
            raw_result = classifier(context)
            _log_classification_event(
                "classification_batch_response",
                log_context,
                project_id=project_id,
                chapter_id=chunk[0].chapter_id if chunk else None,
                mode="batch",
                batch_number=batch_number,
                attempt="initial",
                raw_response=raw_result,
            )
            parsed, discovered = _parse_batch_classification(
                raw_result, expected_ids,
            )
            _log_classification_event(
                "classification_batch_parsed",
                log_context,
                project_id=project_id,
                chapter_id=chunk[0].chapter_id if chunk else None,
                mode="batch",
                batch_number=batch_number,
                attempt="initial",
                parsed_spans=parsed,
                discovered_speakers=discovered,
            )
        except (KeyError, _LegacyBatchContract):
            # Compatibility for older custom hooks that expect source_text at
            # the top level. Normal v3 classifiers never take this path.
            _log_classification_event(
                "classification_batch_legacy_contract",
                log_context,
                project_id=project_id,
                chapter_id=chunk[0].chapter_id if chunk else None,
                batch_number=batch_number,
                error_type="legacy_batch_contract",
                error="classifier did not return the v3 batch shape",
                raw_response=raw_result,
            )
            legacy = annotate_spans(
                project_id=project_id,
                spans=chunk,
                speakers=rolling_speakers,
                aliases=rolling_aliases,
                classifier=classifier,
                context_window=1,
                log_context={
                    **dict(log_context or {}),
                    "chapter_id": chunk[0].chapter_id if chunk else None,
                    "batch_number": batch_number,
                    "parent_mode": "legacy_batch_fallback",
                },
            )
            for annotation in legacy:
                annotations_by_id[annotation.span_id] = annotation
                record_unknown_candidate(annotation)
            _log_classification_event(
                "classification_batch_completed",
                log_context,
                project_id=project_id,
                chapter_id=chunk[0].chapter_id if chunk else None,
                mode="legacy_single_span",
                batch_number=batch_number,
                annotation_count=len(legacy),
                annotations=legacy,
            )
            continue
        except Exception as exc:
            _log_classification_event(
                "classification_batch_parse_failed",
                log_context,
                project_id=project_id,
                chapter_id=chunk[0].chapter_id if chunk else None,
                mode="batch",
                batch_number=batch_number,
                attempt="initial",
                error_type=type(exc).__name__,
                error=str(exc),
                failure_stage="parser" if raw_result is not None else "classifier_call",
                raw_response=raw_result,
            )
            retry_context = {
                **context,
                "task": "retry_story_dialogue_batch_no_source_text_in_response",
                "previous_error": type(exc).__name__,
            }
            retry_result: object = None
            _log_classification_event(
                "classification_batch_request",
                log_context,
                project_id=project_id,
                chapter_id=chunk[0].chapter_id if chunk else None,
                mode="batch",
                batch_number=batch_number,
                attempt="retry",
                expected_span_ids=expected_ids,
                request=retry_context,
            )
            try:
                retry_result = classifier(retry_context)
                _log_classification_event(
                    "classification_batch_response",
                    log_context,
                    project_id=project_id,
                    chapter_id=chunk[0].chapter_id if chunk else None,
                    mode="batch",
                    batch_number=batch_number,
                    attempt="retry",
                    raw_response=retry_result,
                )
                parsed, discovered = _parse_batch_classification(
                    retry_result, expected_ids,
                )
                _log_classification_event(
                    "classification_batch_parsed",
                    log_context,
                    project_id=project_id,
                    chapter_id=chunk[0].chapter_id if chunk else None,
                    mode="batch",
                    batch_number=batch_number,
                    attempt="retry",
                    parsed_spans=parsed,
                    discovered_speakers=discovered,
                )
            except Exception as retry_exc:
                _log_classification_event(
                    "classification_batch_fallback",
                    log_context,
                    project_id=project_id,
                    chapter_id=chunk[0].chapter_id if chunk else None,
                    mode="batch",
                    batch_number=batch_number,
                    reason="retry_failed",
                    initial_error_type=type(exc).__name__,
                    initial_error=str(exc),
                    initial_response=raw_result,
                    retry_error_type=type(retry_exc).__name__,
                    retry_error=str(retry_exc),
                    retry_response=retry_result,
                    expected_span_ids=expected_ids,
                )
                for span in chunk:
                    annotations_by_id[span.id] = SpanAnnotation(
                        span.id,
                        span.structural_kind,
                        narrator,
                        None,
                        "",
                        "FALLBACK_NARRATOR",
                        {
                            "classification_error": type(exc).__name__,
                            "retry_error": type(retry_exc).__name__,
                            "confidence": 0.0,
                        },
                        0.0,
                    )
                _log_classification_event(
                    "classification_batch_completed",
                    log_context,
                    project_id=project_id,
                    chapter_id=chunk[0].chapter_id if chunk else None,
                    mode="batch",
                    batch_number=batch_number,
                    annotation_count=len(chunk),
                    annotations=[annotations_by_id[span.id] for span in chunk],
                )
                continue

        for discovered_speaker in discovered:
            merge_discovery(discovered_speaker)

        payload_by_id = {str(item["span_id"]): item for item in parsed}
        for global_index, span in entries:
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
            annotations_by_id[span.id] = annotation
            record_unknown_candidate(annotation)
        _log_classification_event(
            "classification_batch_completed",
            log_context,
            project_id=project_id,
            chapter_id=chunk[0].chapter_id if chunk else None,
            mode="batch",
            batch_number=batch_number,
            annotation_count=len(chunk),
            annotations=[annotations_by_id[span.id] for span in chunk],
            discovered_speakers=discovered,
        )

    existing_keys = {
        normalize_speaker_name(speaker.canonical_name)
        for speaker in speakers
        if speaker.status == "active"
    }
    analysis = BatchAnalysis(
        tuple(annotations_by_id[span.id] for span in spans),
        tuple(
            discovery for key, discovery in discoveries.items()
            if (
                key not in existing_keys
                or discovery.aliases
                or discovery.role
                or discovery.traits
                or discovery.estimated_age
                or discovery.gender_presentation
            )
        ),
    )
    _log_classification_event(
        "classification_batches_completed",
        log_context,
        project_id=project_id,
        chapter_id=spans[0].chapter_id if spans else None,
        annotation_count=len(analysis.annotations),
        review_count=sum(item.review_reason is not None for item in analysis.annotations),
        discovered_speakers=analysis.discovered_speakers,
        annotations=analysis.annotations,
    )
    return analysis
