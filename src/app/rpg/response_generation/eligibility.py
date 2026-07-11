from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from .contracts import (
    AgencyEffect,
    GateDecision,
    ResponseCandidate,
    ResponseRequest,
    SectionType,
)


_FACTUAL_SECTION_TYPES = {
    SectionType.ACTION,
    SectionType.NPC_DIALOGUE,
    SectionType.RESULT,
    SectionType.STATE_CHANGE,
}


class EligibilityPolicy:
    """Evaluate non-negotiable response gates before prose ranking."""

    def evaluate(
        self,
        candidate: ResponseCandidate,
        request: ResponseRequest,
    ) -> ResponseCandidate:
        result = _mapping(request.authoritative_turn_result)
        strict_claim_refs = bool(
            request.feature_flags.get("strict_claim_refs")
            or result.get("strict_claim_refs")
        )
        decisions = (
            self._state_claim_gate(candidate, result, strict_claim_refs=strict_claim_refs),
            self._visibility_gate(candidate, result),
            self._speaker_gate(candidate, result),
            self._proposal_gate(candidate, result),
            self._agency_gate(candidate, result),
            self._semantic_reference_gate(
                candidate,
                strict_claim_refs=strict_claim_refs,
            ),
            self._mutation_gate(candidate),
        )
        return replace(candidate, gate_decisions=decisions)

    @staticmethod
    def _state_claim_gate(
        candidate: ResponseCandidate,
        result: Mapping[str, Any],
        *,
        strict_claim_refs: bool,
    ) -> GateDecision:
        allowed = _string_set(
            result.get("allowed_claim_refs")
            or result.get("claim_refs")
            or result.get("allowed_claims")
        )
        prohibited = _string_set(
            result.get("prohibited_claim_refs")
            or result.get("forbidden_claim_refs")
        )
        claims = {
            claim
            for section in candidate.plan.sections
            for claim in section.claim_refs
            if claim
        }
        reasons: list[str] = []
        if prohibited & claims:
            reasons.extend(f"prohibited_claim:{claim}" for claim in sorted(prohibited & claims))
        if allowed:
            unsupported = claims - allowed
            reasons.extend(f"unsupported_claim:{claim}" for claim in sorted(unsupported))
        elif strict_claim_refs and claims:
            reasons.extend(f"unverified_claim:{claim}" for claim in sorted(claims))
        return GateDecision("state_claims", not reasons, tuple(reasons))

    @staticmethod
    def _visibility_gate(
        candidate: ResponseCandidate,
        result: Mapping[str, Any],
    ) -> GateDecision:
        hidden_refs = _string_set(
            result.get("hidden_fact_refs")
            or result.get("hidden_claim_refs")
            or result.get("hidden_facts")
        )
        referenced = {
            ref
            for section in candidate.plan.sections
            for ref in (*section.claim_refs, *section.soft_truth_refs)
            if ref
        }
        reasons = [
            f"hidden_reference:{ref}"
            for ref in sorted(hidden_refs & referenced)
        ]
        for section in candidate.plan.sections:
            if bool(section.metadata.get("hidden")):
                reasons.append(f"hidden_section:{section.section_id}")
            if str(section.metadata.get("visibility") or "").casefold() == "hidden":
                reasons.append(f"hidden_section:{section.section_id}")
        return GateDecision("visibility", not reasons, tuple(dict.fromkeys(reasons)))

    @staticmethod
    def _speaker_gate(
        candidate: ResponseCandidate,
        result: Mapping[str, Any],
    ) -> GateDecision:
        allowed_speakers = _string_set(
            result.get("allowed_speakers")
            or result.get("present_npcs")
            or result.get("allowed_npcs")
        )
        knowledge_by_speaker = _mapping(result.get("speaker_knowledge_refs"))
        reasons: list[str] = []
        for section in candidate.plan.sections:
            if section.section_type is not SectionType.NPC_DIALOGUE:
                continue
            if not section.speaker_id:
                reasons.append(f"missing_speaker:{section.section_id}")
                continue
            if allowed_speakers and section.speaker_id not in allowed_speakers:
                reasons.append(f"invalid_speaker:{section.speaker_id}")
            known_refs = _string_set(knowledge_by_speaker.get(section.speaker_id))
            if known_refs:
                unsupported = set(section.claim_refs) - known_refs
                reasons.extend(
                    f"speaker_out_of_scope:{section.speaker_id}:{ref}"
                    for ref in sorted(unsupported)
                )
        return GateDecision("speaker_scope", not reasons, tuple(reasons))

    @staticmethod
    def _proposal_gate(
        candidate: ResponseCandidate,
        result: Mapping[str, Any],
    ) -> GateDecision:
        approved = _string_set(
            result.get("approved_proposal_refs")
            or result.get("approved_proposals")
        )
        proposal_refs = set(candidate.plan.proposal_refs)
        for section in candidate.plan.sections:
            proposal_refs.update(section.proposal_refs)
        reasons: list[str] = []
        if proposal_refs:
            unsupported = proposal_refs - approved
            reasons.extend(
                f"unapproved_proposal:{proposal}"
                for proposal in sorted(unsupported)
            )
        return GateDecision("proposal_permissions", not reasons, tuple(reasons))

    @staticmethod
    def _agency_gate(
        candidate: ResponseCandidate,
        result: Mapping[str, Any],
    ) -> GateDecision:
        metadata = candidate.plan.metadata
        reasons: list[str] = []
        takes_choice = bool(
            metadata.get("takes_player_choice")
            or metadata.get("auto_accepts_lead")
            or metadata.get("auto_starts_investigation")
        )
        clear_intent = bool(
            result.get("clear_player_intent")
            or result.get("mechanic_resolved")
            or candidate.plan.agency_effect
            in {AgencyEffect.RESOLVED_MECHANIC, AgencyEffect.PLAYER_CONFIRMED}
        )
        if takes_choice and not clear_intent:
            reasons.append("player_choice_taken_without_authority")
        irreversible = bool(metadata.get("irreversible_consequence"))
        if irreversible and not clear_intent:
            reasons.append("irreversible_consequence_without_authority")
        return GateDecision("player_agency", not reasons, tuple(reasons))

    @staticmethod
    def _semantic_reference_gate(
        candidate: ResponseCandidate,
        *,
        strict_claim_refs: bool,
    ) -> GateDecision:
        if not strict_claim_refs:
            return GateDecision("semantic_references", True, ())
        reasons: list[str] = []
        for section in candidate.plan.sections:
            factual = (
                section.section_type in _FACTUAL_SECTION_TYPES
                or bool(section.metadata.get("factual"))
            )
            if factual and not section.claim_refs and not section.soft_truth_refs:
                reasons.append(f"missing_claim_reference:{section.section_id}")
        return GateDecision("semantic_references", not reasons, tuple(reasons))

    @staticmethod
    def _mutation_gate(candidate: ResponseCandidate) -> GateDecision:
        metadata = candidate.plan.metadata
        reasons: list[str] = []
        if metadata.get("authoritative_mutation"):
            reasons.append("presentation_attempted_authoritative_mutation")
        if metadata.get("executes_tools"):
            reasons.append("presentation_attempted_tool_execution")
        return GateDecision("no_direct_mutation", not reasons, tuple(reasons))


def eligibility_reasons(candidate: ResponseCandidate) -> tuple[str, ...]:
    return tuple(
        reason
        for decision in candidate.gate_decisions
        if not decision.passed
        for reason in decision.reasons
    )


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _string_set(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, Mapping):
        return {str(key) for key, enabled in value.items() if enabled}
    if isinstance(value, str):
        return {value} if value else set()
    try:
        return {str(item) for item in value if str(item)}
    except TypeError:
        return set()
