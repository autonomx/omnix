"""Canonical orchestration service for the isolated Narrative Engine."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .authority import DeliveryMode
from .contracts import (
    CanonicalNarrativeResponse,
    DeliveryMetadata,
    EvidenceRecord,
    GenerationMetadata,
    TurnPresentationRequest,
)
from .delivery import NarrativeDeliveryCoordinator
from .evidence import (
    EvidenceAccessContext,
    EvidenceBroker,
    EvidenceQuery,
    EvidenceRetrievalResult,
)
from .planner import DeterministicBeatPlanner, NarrativePlan
from .repository import (
    InMemoryNarrativeResponseRepository,
    NarrativeResponseRepository,
)
from .validation import (
    ValidatedWriterResult,
    write_validate_repair,
)
from .writer import DeterministicNarrativeWriter, NarrativeWriter


@dataclass(frozen=True)
class NarrativeEngineResult:
    request: TurnPresentationRequest
    retrieval: EvidenceRetrievalResult
    plan: NarrativePlan
    response: CanonicalNarrativeResponse
    writer_result: ValidatedWriterResult


class NarrativeEngineService:
    """Retrieve, plan, write, validate, persist, and deliver one response."""

    def __init__(
        self,
        *,
        evidence_broker: EvidenceBroker,
        writer: NarrativeWriter | None = None,
        planner: DeterministicBeatPlanner | None = None,
        repository: NarrativeResponseRepository | None = None,
        delivery: NarrativeDeliveryCoordinator | None = None,
    ) -> None:
        self.evidence_broker = evidence_broker
        self.writer = writer or DeterministicNarrativeWriter()
        self.planner = planner or DeterministicBeatPlanner()
        self.repository = repository or InMemoryNarrativeResponseRepository()
        self.delivery = delivery or NarrativeDeliveryCoordinator()

    def generate(self, request: TurnPresentationRequest) -> NarrativeEngineResult:
        retrieval = self.evidence_broker.retrieve(self._query(request))
        evidence = retrieval.evidence
        plan = self.planner.plan(request, evidence)
        validated = write_validate_repair(
            request,
            plan,
            evidence,
            self.writer,
        )
        if not validated.validation.passed:
            codes = ",".join(
                issue.code for issue in validated.validation.issues
            )
            raise RuntimeError(
                f"canonical narrative failed validation: {codes}"
            )
        canonical = self._assemble(
            request,
            plan,
            evidence,
            validated,
        )
        persisted = self.repository.save(canonical)
        delivered = self.delivery.prepare(
            persisted,
            request.delivery_mode,
        )
        return NarrativeEngineResult(
            request=request,
            retrieval=retrieval,
            plan=plan,
            response=delivered,
            writer_result=validated,
        )

    @staticmethod
    def _query(request: TurnPresentationRequest) -> EvidenceQuery:
        speaker = (
            request.target_actor_id
            or str(request.metadata.get("speaker_id") or "")
            or None
        )
        entity_ids = tuple(
            dict.fromkeys(
                value
                for value in (
                    *request.actor_ids,
                    request.target_actor_id or "",
                )
                if value
            )
        )
        return EvidenceQuery(
            text=request.player_input,
            entity_ids=entity_ids,
            limit=int(request.metadata.get("evidence_limit") or 12),
            access=EvidenceAccessContext(
                player_id=str(
                    request.metadata.get("player_id") or "player"
                ),
                speaker_id=speaker,
                actor_ids=request.actor_ids,
                faction_ids=tuple(
                    request.metadata.get("faction_ids") or ()
                ),
                narrator_mode=True,
            ),
        )

    @staticmethod
    def _assemble(
        request: TurnPresentationRequest,
        plan: NarrativePlan,
        evidence: Sequence[EvidenceRecord],
        validated: ValidatedWriterResult,
    ) -> CanonicalNarrativeResponse:
        writer_result = validated.writer_result
        evidence_used = tuple(
            dict.fromkeys(
                ref
                for block in writer_result.blocks
                for ref in block.evidence_refs
            )
        )
        revision = max(
            1,
            int(
                request.metadata.get("presentation_revision")
                or 1
            ),
        )
        response_id = str(
            request.metadata.get("response_id")
            or (
                f"narrative:{request.campaign_id}:"
                f"{request.turn_id}:{revision}"
            )
        )
        grounding_metadata = {
            "hermes_research_id": str(
                request.metadata.get("hermes_research_id") or ""
            ),
            "canon_topic_count": int(
                request.metadata.get("canon_topic_count") or 0
            ),
            "canon_topic_titles": list(
                request.metadata.get("canon_topic_titles") or ()
            ),
            "hermes_source_ids": list(
                request.metadata.get("hermes_source_ids") or ()
            ),
            "campaign_bible_revision": int(
                request.metadata.get("campaign_bible_revision") or 0
            ),
            "campaign_bible_hash": str(
                request.metadata.get("campaign_bible_hash") or ""
            ),
            "campaign_bible_evidence_count": int(
                request.metadata.get("campaign_bible_evidence_count")
                or 0
            ),
            "runtime_evidence_count": int(
                request.metadata.get("runtime_evidence_count") or 0
            ),
            "hermes_evidence_count": int(
                request.metadata.get("hermes_evidence_count") or 0
            ),
            "grounding_passed": (
                request.metadata.get("grounding_passed") is True
            ),
        }
        return CanonicalNarrativeResponse(
            response_id=response_id,
            request_id=request.request_id,
            turn_id=request.turn_id,
            campaign_id=request.campaign_id,
            revision=revision,
            blocks=writer_result.blocks,
            evidence_used=evidence_used,
            validation=validated.validation,
            generation=GenerationMetadata(
                source=writer_result.source,
                provider=writer_result.provider,
                model=writer_result.model,
                latency_ms=writer_result.latency_ms,
                attempt_count=writer_result.attempt_count,
                evidence_count=len(evidence),
                beat_count=len(plan.beats),
                hermes_used=(
                    request.metadata.get("hermes_used") is True
                ),
                metadata={
                    "fallback_used": validated.fallback_used,
                    "retrieval_selected_ids": list(evidence_used),
                    **grounding_metadata,
                },
            ),
            delivery=DeliveryMetadata(
                mode=DeliveryMode.BLOCKING,
                status="approved",
            ),
            metadata={
                "mode": plan.mode,
                "profile": plan.profile.value,
                "word_budget": list(plan.word_budget),
                "grounding": grounding_metadata,
            },
        ).with_content_hash()
