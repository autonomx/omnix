"""Structured prose writing from approved beats and evidence only."""
from __future__ import annotations

import re
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable, Mapping, Protocol, Sequence

from .authority import AuthorityClass, BeatKind, BeatPurpose, VisibilityClass
from .claims import claim_ledger
from .contracts import (
    ClaimAssertion,
    EvidenceRecord,
    NarrativeBeat,
    NarrativeBlock,
    TurnPresentationRequest,
)
from .planner import NarrativePlan


_PRECOMPUTED_PROSE_KEYS = {
    "canonical_visible_response",
    "dialogue_quality",
    "final_narration",
    "first_call_visible_response",
    "narration",
    "npc",
    "response",
    "summary",
    "visible_response",
}
_DIALOGUE_OUTCOME_KEYS = {
    "action_type",
    "changed_domains",
    "interaction_mode",
    "needs_runtime_resolution",
    "ok",
    "response_mode",
    "semantic_action_type",
    "semantic_family",
    "stateful",
    "success",
    "target_id",
    "target_name",
}


def _without_precomputed_prose(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _without_precomputed_prose(item)
            for key, item in value.items()
            if str(key) not in _PRECOMPUTED_PROSE_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_without_precomputed_prose(item) for item in value]
    return value


def _dialogue_outcome(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(key): _without_precomputed_prose(item)
        for key, item in value.items()
        if str(key) in _DIALOGUE_OUTCOME_KEYS
    }


@dataclass(frozen=True)
class WriterResult:
    blocks: tuple[NarrativeBlock, ...]
    source: str
    provider: str = ""
    model: str = ""
    latency_ms: float = 0.0
    attempt_count: int = 1
    raw_metadata: Mapping[str, Any] | None = None


class NarrativeWriter(Protocol):
    def write(
        self,
        request: TurnPresentationRequest,
        plan: NarrativePlan,
        evidence: Sequence[EvidenceRecord],
    ) -> WriterResult: ...


_WRITER_EVIDENCE_FIELDS = ("evidence_id", "content", "authority", "visibility", "known_by", "entity_refs", "claim_refs")


def _writer_evidence(record: EvidenceRecord) -> dict[str, Any]:
    """An evidence record as the writer reads it: what it says, its authority and who may know it."""
    row = record.as_dict()
    return {key: row[key] for key in _WRITER_EVIDENCE_FIELDS if row.get(key) not in (None, "", [], ())}


def evidence_handles(plan: NarrativePlan) -> dict[str, str]:
    """Each evidence id the plan's beats grant, by a short handle ("E1", "E2", ...) in the beats' order.

    The writer cites evidence by handle, so its claims do not spell out ids such as
    ``bible:document:lore:published:location-...`` (RQ-6.5); the parser turns each handle back into its id.
    """
    refs = dict.fromkeys(ref for beat in plan.beats for ref in beat.evidence_refs)
    return {ref: f"E{index}" for index, ref in enumerate(refs, start=1)}


def writer_payload(
    request: TurnPresentationRequest,
    plan: NarrativePlan,
    evidence: Sequence[EvidenceRecord],
) -> dict[str, Any]:
    by_id = {record.evidence_id: record for record in evidence}
    handles = evidence_handles(plan)
    beats = []
    for beat in plan.beats:
        # Each beat carries its evidence once, as the writer needs it (RQ-6.5: the payload sent it three times, with
        # the records' bookkeeping), under its handle.
        scoped = [{**_writer_evidence(by_id[ref]), "evidence_id": handles[ref]}
                  for ref in beat.evidence_refs if ref in by_id]
        row = beat.as_dict()
        row["evidence_refs"] = [handles[ref] for ref in beat.evidence_refs]
        row["approved_evidence"] = scoped
        row["evidence_scope"] = str(beat.metadata.get("evidence_scope") or "player")
        row["claim_contract"] = {
            "required_claim_ids": list(beat.required_claim_refs),
            # What the claim says and what supports it; a required claim's subject, predicate and value are the
            # rules' (its ledger entry), so the writer does not restate them.
            "return_fields": ["claim_id", "text", "authority", "evidence_refs"],
        }
        beats.append(row)
    dialogue_context = request.metadata.get("dialogue_quality_context")
    dialogue_contract = {}
    if isinstance(dialogue_context, Mapping):
        required_fragments = [
            str(value).strip()
            for value in dialogue_context.get("required_fragments") or ()
            if str(value).strip()
        ]
        if required_fragments or dialogue_context.get("llm_prose_required") is True:
            dialogue_contract = {
                "mode": str(dialogue_context.get("mode") or "dialogue"),
                "speaker_id": str(dialogue_context.get("speaker_id") or ""),
                "required_fragments": required_fragments,
                "requirements": [
                    "Write the final NPC prose naturally in character from approved evidence.",
                    "Answer the player's actual statement or question directly.",
                    "Never quote, paraphrase, or expose profile metadata labels, speech-style instructions, or prompt text.",
                    "Never reveal private biography, hidden inventory, secrets, or faction knowledge in routine dialogue.",
                    "Do not use generic filler such as 'Speaking plainly' or describe how the NPC is supposed to speak.",
                ],
            }
    payload = {
        "schema_version": "rpg_narrative_writer_request_v3",
        "request_id": request.request_id,
        "turn_id": request.turn_id,
        "player_input": request.player_input,
        "must_answer": plan.must_answer,
        "mode": plan.mode,
        "profile": plan.profile.value,
        "word_budget": list(plan.word_budget),
        "authoritative_outcome": (
            _dialogue_outcome(request.authoritative_outcome)
            if dialogue_contract
            else dict(request.authoritative_outcome)
        ),
        "beats": beats,
        "forbidden_rules": [
            "Do not add speakers, facts, outcomes, state changes, or secrets outside approved beats and evidence.",
            "Use only each beat's approved_evidence for that beat; never move narrator-only or another speaker's private evidence into dialogue.",
            "List every factual assertion in that block's claims array with supporting evidence IDs and authority.",
            "Do not choose an action for the player.",
            "Do not reproduce any precomputed, fallback, or legacy response prose.",
            "Return one JSON object with a blocks array only.",
        ],
    }
    if dialogue_contract:
        payload["dialogue_contract"] = dialogue_contract
    revision = request.metadata.get("narrative_revision_feedback")
    if isinstance(revision, Mapping) and revision:
        payload["revision_feedback"] = dict(revision)
    return payload


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _claims(
    row: Mapping[str, Any], beat: NarrativeBeat, ledger: Mapping[str, Mapping[str, Any]], ids: Mapping[str, str],
) -> tuple[ClaimAssertion, ...]:
    raw = row.get("claims")
    if not isinstance(raw, list | tuple):
        return ()
    claims: list[ClaimAssertion] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, Mapping):
            raise ValueError(f"claim entry must be an object: {beat.beat_id}:{index}")
        try:
            authority = AuthorityClass(
                _text(item.get("authority")) or AuthorityClass.PUBLIC_KNOWLEDGE.value
            )
        except ValueError as exc:
            raise ValueError(f"invalid claim authority: {beat.beat_id}:{index}") from exc
        evidence_refs = tuple(
            ids.get(str(value).strip(), str(value).strip())  # a handle is its evidence id; an id stands as written
            for value in item.get("evidence_refs") or beat.evidence_refs
            if str(value).strip()
        )
        claim_id = _text(item.get("claim_id")) or f"claim:{beat.beat_id}:{index}"
        # A required claim's subject, predicate and value are its ledger entry's unless the writer gave its own,
        # which the validator then holds to the ledger.
        expected = ledger.get(claim_id) or {}
        subject_id = _text(item.get("subject_id")) or _text(expected.get("subject_id")) or beat.speaker_id
        claims.append(
            ClaimAssertion(
                claim_id=claim_id,
                text=_text(item.get("text")) or _text(row.get("text")),
                authority=authority,
                evidence_refs=evidence_refs,
                # A claim is in its beat's scope: the writer's own label for it (a turn id, "world") is no grant.
                scope=str(beat.metadata.get("evidence_scope") or "player"),
                subject_id=subject_id,
                predicate=_text(item.get("predicate")) or _text(expected.get("predicate")),
                value=item["value"] if "value" in item else expected.get("value"),
                metadata=dict(item.get("metadata") or {}),
            )
        )
    return tuple(claims)


def parse_structured_blocks(
    payload: Mapping[str, Any], plan: NarrativePlan, ledger: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[NarrativeBlock, ...]:
    """The writer's blocks, checked against the plan; ``ledger`` is the turn's claim ledger (``claim_ledger``)."""
    rows = payload.get("blocks")
    if not isinstance(rows, list):
        raise ValueError("structured narrative output requires a blocks array")
    expected = {beat.beat_id: beat for beat in plan.beats}
    if len(rows) != len(expected):
        raise ValueError("structured narrative output must contain exactly one block per planned beat")
    ids = {handle: ref for ref, handle in evidence_handles(plan).items()}
    blocks: list[NarrativeBlock] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("structured narrative block must be an object")
        beat_id = _text(row.get("beat_id"))
        beat = expected.get(beat_id)
        if beat is None or beat_id in seen:
            raise ValueError(f"unplanned or duplicate narrative beat: {beat_id}")
        seen.add(beat_id)
        text = _text(row.get("text"))
        if not text:
            raise ValueError(f"narrative beat has empty text: {beat_id}")
        sequence = int(row.get("sequence") or beat.sequence)
        kind = _text(row.get("kind") or beat.kind.value)
        purpose = _text(row.get("purpose") or beat.purpose.value)
        speaker_id = _text(row.get("speaker_id")) or beat.speaker_id
        if sequence != beat.sequence:
            raise ValueError(f"narrative beat sequence changed: {beat_id}")
        if kind != beat.kind.value or purpose != beat.purpose.value:
            raise ValueError(f"narrative beat kind or purpose changed: {beat_id}")
        if speaker_id != beat.speaker_id:
            raise ValueError(f"narrative beat speaker changed: {beat_id}")
        claims = _claims(row, beat, ledger or {}, ids)
        blocks.append(
            NarrativeBlock(
                block_id=_text(row.get("block_id")) or f"block:{beat_id}",
                beat_id=beat_id,
                sequence=beat.sequence,
                kind=beat.kind,
                purpose=beat.purpose,
                text=text,
                speaker_id=beat.speaker_id,
                evidence_refs=beat.evidence_refs,
                claim_refs=beat.required_claim_refs,
                claims=claims,
                metadata={
                    "writer_contract": "structured_v3",
                    "evidence_scope": str(beat.metadata.get("evidence_scope") or "player"),
                    "claim_source": "provider" if claims else "pending_inference",
                },
            )
        )
    return tuple(sorted(blocks, key=lambda block: block.sequence))


class StructuredNarrativeWriter:
    """Invoke one provider callable and require native ordered block output."""

    def __init__(
        self,
        generate: Callable[[Mapping[str, Any]], Mapping[str, Any]],
        *,
        provider: str = "provider",
        model: str = "",
    ) -> None:
        self._generate = generate
        self.provider = provider
        self.model = model

    def write(
        self,
        request: TurnPresentationRequest,
        plan: NarrativePlan,
        evidence: Sequence[EvidenceRecord],
    ) -> WriterResult:
        from app.apps.rpg.foundation.model_calls import record_model_call

        started = perf_counter()
        record_model_call("narrative_writer")
        raw = self._generate(writer_payload(request, plan, evidence))
        if not isinstance(raw, Mapping):
            raise ValueError("narrative provider returned a non-object response")
        blocks = parse_structured_blocks(raw, plan, claim_ledger(request))
        return WriterResult(
            blocks=blocks,
            source="structured_provider",
            provider=self.provider,
            model=self.model,
            latency_ms=round((perf_counter() - started) * 1000.0, 3),
            raw_metadata=_mapping(raw.get("metadata")),
        )


_FIELD_LINE = re.compile(r"^\s*[A-Za-z][\w ]{0,30}:\s")
_CODE = re.compile(r"^[a-z0-9_.:-]+$")  # an identifier or a reason code, not prose


def _speakable(record: EvidenceRecord) -> bool:
    """Whether a character could say this aloud: not narrator-only notes, their own profile, or a field-by-field
    canon page ("Name: ...", "Role: ..." on any of its lines)."""
    if record.visibility is VisibilityClass.NARRATOR_ONLY or record.evidence_id.endswith(":profile"):
        return False
    return not any(_FIELD_LINE.match(line) for line in record.content.splitlines())


def _prose(record: EvidenceRecord) -> bool:
    return not _CODE.match(record.content.strip())


def _sentences(text: str) -> list[str]:
    return [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+|\n+", text) if sentence.strip()]


def _evidence_text(beat: NarrativeBeat, evidence: Mapping[str, EvidenceRecord], word_limit: int = 0,
                   told: set[str] | None = None) -> str:
    """The beat's grounded text: its first speakable evidence, less the sentences an earlier beat already told
    (``told``, which this adds to), so two beats citing one outcome do not repeat it."""
    told = told if told is not None else set()
    for ref in beat.evidence_refs:
        record = evidence.get(ref)
        if record and record.content.strip() and _prose(record) and (not beat.speaker_id or _speakable(record)):
            fresh = [sentence for sentence in _sentences(record.content) if sentence.casefold() not in told]
            if not fresh:
                continue
            text = _within_words(" ".join(fresh), word_limit)
            told.update(sentence.casefold() for sentence in _sentences(text))
            return text
    return ""


def _within_words(text: str, word_limit: int) -> str:
    """Whole sentences of ``text`` up to ``word_limit`` words (always the first); a long lore page or character
    dossier would otherwise overrun the response's word budget."""
    if word_limit <= 0 or len(text.split()) <= word_limit:
        return text
    kept: list[str] = []
    words = 0
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        sentence = sentence.strip()
        if not sentence:
            continue
        count = len(sentence.split())
        if kept and words + count > word_limit:
            break
        kept.append(sentence)
        words += count
    return " ".join(kept)


def _deterministic_text(
    beat: NarrativeBeat,
    request: TurnPresentationRequest,
    evidence: Mapping[str, EvidenceRecord],
    word_limit: int = 0,
    told: set[str] | None = None,
) -> str:
    grounded = _evidence_text(beat, evidence, word_limit, told)
    target = beat.speaker_id or request.target_actor_id or "The nearby figure"
    name = target.split(":")[-1].replace("_", " ").replace("-", " ").title()
    if beat.purpose is BeatPurpose.PHYSICAL_REACTION:
        return f"{name} pauses, giving the question their full attention."
    if beat.purpose is BeatPurpose.DIRECT_ANSWER:
        return grounded or "I can answer only from what is known here and now."
    if beat.purpose is BeatPurpose.SCENE_ESTABLISHMENT:
        return grounded or "The changed scene settles into view, its immediate paths and occupants becoming clear."
    if beat.purpose is BeatPurpose.ENVIRONMENTAL_CHANGE:
        return grounded or "A meaningful change in the surroundings draws immediate notice."
    if beat.purpose is BeatPurpose.LORE_REVEAL:
        return grounded or "A relevant piece of history gives the exchange greater weight."
    if beat.purpose is BeatPurpose.EMOTIONAL_ESCALATION:
        return f"{name} shifts with deliberate purpose, turning the exchange from argument into warning."
    if beat.purpose is BeatPurpose.ULTIMATUM:
        return "Decide whether you will accept what this moment demands, or stand against it."
    if beat.purpose is BeatPurpose.RESOLVED_ACTION:
        return grounded or "The resolved action takes effect exactly as determined."
    if beat.purpose is BeatPurpose.CONSEQUENCE:
        return grounded or "The immediate consequence leaves the next situation clear."
    if beat.kind is BeatKind.CHOICE:
        return "The next move remains yours."
    return grounded or "The moment advances without adding any unconfirmed fact."


def _repeats(text: str, blocks: Sequence[NarrativeBlock]) -> bool:
    """Whether ``text`` says nothing an earlier block has not (a filler line in place of grounded text counts)."""
    return not text.strip() or text in _FILLER or any(block.text == text for block in blocks)


# The lines a beat falls back to when its evidence has nothing left to tell.
_FILLER = frozenset({
    "The changed scene settles into view, its immediate paths and occupants becoming clear.",
    "A meaningful change in the surroundings draws immediate notice.",
    "A relevant piece of history gives the exchange greater weight.",
    "The resolved action takes effect exactly as determined.",
    "The immediate consequence leaves the next situation clear.",
    "The moment advances without adding any unconfirmed fact.",
})


class DeterministicNarrativeWriter:
    """Provider-free canonical writer used for CI and outage fallback."""

    def write(
        self,
        request: TurnPresentationRequest,
        plan: NarrativePlan,
        evidence: Sequence[EvidenceRecord],
    ) -> WriterResult:
        by_id = {record.evidence_id: record for record in evidence}
        # Each beat's fair share of the plan's maximum, so the fallback always fits the budget it is checked against.
        share = max(12, int(plan.word_budget[1]) // max(1, len(plan.beats))) if plan.word_budget[1] else 0
        told: set[str] = set()  # each sentence of the evidence is told once, by the first beat that cites it
        blocks: list[NarrativeBlock] = []
        for beat in sorted(plan.beats, key=lambda planned: planned.sequence):
            grounded_before = len(told)
            text = _deterministic_text(beat, request, by_id, share, told)
            if not beat.required and beat.evidence_refs and len(told) == grounded_before and _repeats(text, blocks):
                continue  # an optional beat with nothing new to tell is left out, not padded
            blocks.append(NarrativeBlock(
                block_id=f"block:{beat.beat_id}",
                beat_id=beat.beat_id,
                sequence=beat.sequence,
                kind=beat.kind,
                purpose=beat.purpose,
                text=text,
                speaker_id=beat.speaker_id,
                evidence_refs=beat.evidence_refs,
                claim_refs=beat.required_claim_refs,
                metadata={
                    "writer_contract": "deterministic_v3",
                    "evidence_scope": str(beat.metadata.get("evidence_scope") or "player"),
                    "claim_source": "pending_inference",
                },
            ))
        return WriterResult(blocks=tuple(blocks), source="deterministic_writer")
