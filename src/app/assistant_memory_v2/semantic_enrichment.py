from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable, Literal

from .consolidation import ConsolidationPlan
from .contracts import (
    GraphAssertion,
    GraphEntityRef,
    GraphValue,
    MemoryDomain,
    MemorySpaceKey,
    Observation,
)
from .temporal import TemporalClaim, apply_temporal_claim

SemanticOperation = Literal["assert", "retract"]


@dataclass(frozen=True, slots=True)
class SemanticMemoryProposal:
    """Provider-neutral semantic proposal; never a direct graph write."""

    subject: GraphEntityRef
    predicate: str
    domain: MemoryDomain
    effective_at: datetime
    operation: SemanticOperation = "assert"
    value: GraphValue | None = None
    confidence: float = 1.0
    single_valued: bool = True

    def __post_init__(self) -> None:
        if not self.predicate:
            raise ValueError("semantic proposal predicate is required")
        if self.operation == "assert" and self.value is None:
            raise ValueError("assert proposal requires a value")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("semantic proposal confidence must be between 0 and 1")


SemanticExtractor = Callable[[Observation], Iterable[SemanticMemoryProposal]]

_AUTHORITATIVE_SEMANTIC_EVENTS = {
    "user_said",
    "assistant_experienced",
    "external_observed",
    "system_event",
    "imported_legacy_memory",
}


def _replace_assertion(
    working: list[GraphAssertion],
    replacement: GraphAssertion,
) -> None:
    for index, item in enumerate(working):
        if item.assertion_id == replacement.assertion_id:
            working[index] = replacement
            return
    working.append(replacement)


class VoiceMemDerivedSemanticEnricher:
    """Port VoiceMem-style semantic extraction into Omnix Memory v2 authority contracts.

    Extractors only return proposals. This class applies deterministic temporal policy and
    emits a ConsolidationPlan; persistence remains the consolidator's responsibility.
    """

    def __init__(
        self,
        extractor: SemanticExtractor,
        *,
        derivation_version: str = "voicemem-derived-semantic@1",
        dispute_threshold: float = 0.6,
    ) -> None:
        self.extractor = extractor
        self.derivation_version = derivation_version
        self.dispute_threshold = dispute_threshold

    def project(
        self,
        space: MemorySpaceKey,
        observations: tuple[Observation, ...],
        existing: tuple[GraphAssertion, ...],
    ) -> ConsolidationPlan:
        if any(item.space != space for item in observations):
            raise ValueError("semantic enrichment window crosses memory spaces")
        if any(item.space != space for item in existing):
            raise ValueError("semantic enrichment graph crosses memory spaces")

        working = list(existing)
        changed: dict[str, GraphAssertion] = {}
        for observation in sorted(observations, key=lambda item: item.authority_sequence):
            if observation.event_type not in _AUTHORITATIVE_SEMANTIC_EVENTS:
                continue
            proposals = tuple(self.extractor(observation))
            for proposal in proposals:
                claim = TemporalClaim(
                    subject=proposal.subject,
                    predicate=proposal.predicate,
                    domain=proposal.domain,
                    effective_at=proposal.effective_at,
                    operation=proposal.operation,
                    value=proposal.value,
                    confidence=proposal.confidence,
                    single_valued=proposal.single_valued,
                )
                plan = apply_temporal_claim(
                    space,
                    observation,
                    tuple(working),
                    claim,
                    derivation_version=self.derivation_version,
                    dispute_threshold=self.dispute_threshold,
                )
                for assertion in plan.assertions:
                    _replace_assertion(working, assertion)
                    changed[assertion.assertion_id] = assertion
        return ConsolidationPlan(
            assertions=tuple(sorted(changed.values(), key=lambda item: item.assertion_id))
        )
