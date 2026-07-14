"""Fail-closed validation, bounded repair, and deterministic fallback."""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Sequence

from .authority import BeatKind
from .contracts import (
    EvidenceRecord,
    NarrativeBlock,
    TurnPresentationRequest,
    ValidationIssue,
    ValidationReport,
)
from .planner import NarrativePlan
from .renderer import deduplicate_blocks
from .writer import DeterministicNarrativeWriter, NarrativeWriter, WriterResult

_TRUNCATION_MARKERS = ("...[truncated]", "[truncated]", "<truncated>")
_LABEL_PREFIX = re.compile(r"^(?:narrator|action|npc|result|reward)\s*:\s*", re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")


def _scripts(text: str) -> set[str]:
    found: set[str] = set()
    for char in text:
        code = ord(char)
        if "A" <= char <= "Z" or "a" <= char <= "z":
            found.add("latin")
        elif 0x0400 <= code <= 0x04FF:
            found.add("cyrillic")
        elif 0x0600 <= code <= 0x06FF:
            found.add("arabic")
        elif 0xAC00 <= code <= 0xD7AF:
            found.add("hangul")
        elif 0x4E00 <= code <= 0x9FFF:
            found.add("han")
    return found


def _allowed_claim_refs(request: TurnPresentationRequest) -> set[str]:
    raw = request.authoritative_outcome.get("allowed_claim_refs") or request.metadata.get("allowed_claim_refs") or ()
    return {str(value) for value in raw if str(value).strip()}


def _word_count(blocks: Sequence[NarrativeBlock]) -> int:
    return sum(len(block.text.split()) for block in blocks)


class NarrativeValidator:
    """Validate structure, evidence, knowledge, claims, agency, and output quality."""

    def validate(
        self,
        request: TurnPresentationRequest,
        plan: NarrativePlan,
        evidence: Sequence[EvidenceRecord],
        blocks: Sequence[NarrativeBlock],
    ) -> ValidationReport:
        issues: list[ValidationIssue] = []
        expected = {beat.beat_id: beat for beat in plan.beats}
        evidence_ids = {record.evidence_id for record in evidence}
        allowed_claims = _allowed_claim_refs(request)
        valid_speakers = set(request.actor_ids)
        if request.target_actor_id:
            valid_speakers.add(request.target_actor_id)
        seen_beats: set[str] = set()
        seen_text: set[str] = set()

        for block in blocks:
            beat = expected.get(block.beat_id)
            if beat is None:
                issues.append(ValidationIssue("unplanned_block", "Block does not map to an approved beat.", block.block_id))
                continue
            if block.beat_id in seen_beats:
                issues.append(ValidationIssue("duplicate_beat", "A planned beat was written more than once.", block.block_id))
            seen_beats.add(block.beat_id)
            if block.sequence != beat.sequence or block.kind is not beat.kind or block.purpose is not beat.purpose:
                issues.append(ValidationIssue("beat_contract_changed", "Block changed the approved beat contract.", block.block_id))
            if block.speaker_id != beat.speaker_id:
                issues.append(ValidationIssue("speaker_changed", "Block changed the approved speaker.", block.block_id))
            if block.kind is BeatKind.DIALOGUE and (not block.speaker_id or block.speaker_id not in valid_speakers):
                issues.append(ValidationIssue("invalid_speaker", "Dialogue speaker is not present or permitted.", block.block_id))
            unknown_evidence = set(block.evidence_refs).difference(evidence_ids)
            if unknown_evidence:
                issues.append(ValidationIssue("unknown_evidence", f"Unknown evidence references: {sorted(unknown_evidence)}", block.block_id))
            if not set(block.evidence_refs).issubset(set(beat.evidence_refs)):
                issues.append(ValidationIssue("unplanned_evidence", "Block references evidence not approved for its beat.", block.block_id))
            unknown_claims = set(block.claim_refs).difference(allowed_claims)
            if unknown_claims:
                issues.append(ValidationIssue("unapproved_claim", f"Unapproved claim references: {sorted(unknown_claims)}", block.block_id))
            if not set(beat.required_claim_refs).issubset(set(block.claim_refs)):
                issues.append(ValidationIssue("missing_claim_ref", "Block omitted a required authoritative claim reference.", block.block_id))
            text = block.text.strip()
            if not text:
                issues.append(ValidationIssue("empty_block", "Block text is empty.", block.block_id))
                continue
            normalized = " ".join(text.casefold().split())
            if normalized in seen_text:
                issues.append(ValidationIssue("duplicate_text", "Visible text repeats another block.", block.block_id))
            seen_text.add(normalized)
            if "�" in text or any(marker in text.casefold() for marker in _TRUNCATION_MARKERS):
                issues.append(ValidationIssue("malformed_or_truncated", "Output contains malformed or truncated text.", block.block_id))
            scripts = _scripts(text)
            if "latin" in scripts and len(scripts) > 1 and not block.metadata.get("allow_multiscript"):
                issues.append(ValidationIssue("mixed_script_corruption", f"Unexpected mixed scripts: {sorted(scripts)}", block.block_id))
            if block.kind is BeatKind.DIALOGUE and text.count("\"") % 2 == 1:
                issues.append(ValidationIssue("unbalanced_quote", "Dialogue contains an unbalanced quote.", block.block_id))

        required_beats = {beat.beat_id for beat in plan.beats if beat.required}
        missing = required_beats.difference(seen_beats)
        if missing:
            issues.append(ValidationIssue("missing_required_beats", f"Missing required beats: {sorted(missing)}"))
        sequences = [block.sequence for block in blocks]
        if sequences != sorted(sequences) or len(sequences) != len(set(sequences)):
            issues.append(ValidationIssue("invalid_sequence", "Blocks are not in a unique ascending sequence."))
        if _word_count(blocks) > plan.word_budget[1]:
            issues.append(ValidationIssue("word_budget_exceeded", "Response exceeds the configured maximum word budget."))
        return ValidationReport(passed=not issues, issues=tuple(issues))


class NarrativeRepairer:
    """Apply only mechanically safe repairs that do not invent new meaning."""

    def repair(self, plan: NarrativePlan, blocks: Sequence[NarrativeBlock]) -> tuple[tuple[NarrativeBlock, ...], tuple[str, ...]]:
        expected = {beat.beat_id: beat for beat in plan.beats}
        repaired: list[NarrativeBlock] = []
        history: list[str] = []
        for block in deduplicate_blocks(blocks):
            beat = expected.get(block.beat_id)
            if beat is None:
                history.append(f"removed_unplanned:{block.block_id}")
                continue
            text = _WHITESPACE.sub(" ", _LABEL_PREFIX.sub("", block.text)).strip()
            if text != block.text:
                history.append(f"normalized_text:{block.block_id}")
            repaired.append(
                replace(
                    block,
                    sequence=beat.sequence,
                    kind=beat.kind,
                    purpose=beat.purpose,
                    speaker_id=beat.speaker_id,
                    evidence_refs=beat.evidence_refs,
                    claim_refs=beat.required_claim_refs,
                    text=text,
                )
            )
        return tuple(sorted(repaired, key=lambda block: block.sequence)), tuple(history)


@dataclass(frozen=True)
class ValidatedWriterResult:
    writer_result: WriterResult
    validation: ValidationReport
    fallback_used: bool


def write_validate_repair(
    request: TurnPresentationRequest,
    plan: NarrativePlan,
    evidence: Sequence[EvidenceRecord],
    writer: NarrativeWriter,
    *,
    validator: NarrativeValidator | None = None,
    repairer: NarrativeRepairer | None = None,
    fallback_writer: NarrativeWriter | None = None,
) -> ValidatedWriterResult:
    validator = validator or NarrativeValidator()
    repairer = repairer or NarrativeRepairer()
    fallback_writer = fallback_writer or DeterministicNarrativeWriter()
    try:
        result = writer.write(request, plan, evidence)
    except Exception:
        fallback = fallback_writer.write(request, plan, evidence)
        report = validator.validate(request, plan, evidence, fallback.blocks)
        return ValidatedWriterResult(fallback, report, True)

    report = validator.validate(request, plan, evidence, result.blocks)
    if report.passed:
        return ValidatedWriterResult(result, report, False)
    repaired, history = repairer.repair(plan, result.blocks)
    repaired_report = validator.validate(request, plan, evidence, repaired)
    if repaired_report.passed:
        return ValidatedWriterResult(
            replace(result, blocks=repaired),
            replace(repaired_report, repair_history=history),
            False,
        )
    fallback = fallback_writer.write(request, plan, evidence)
    fallback_report = validator.validate(request, plan, evidence, fallback.blocks)
    return ValidatedWriterResult(fallback, fallback_report, True)
