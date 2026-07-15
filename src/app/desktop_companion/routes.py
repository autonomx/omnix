"""Internal Desktop Companion observation, preflight, evaluation, and rollout endpoints."""
from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, Query
from pydantic import BaseModel, ConfigDict, Field

from .build_identity import DesktopCompanionBuildIdentity, resolve_desktop_companion_build_identity
from .evaluation import (
    DesktopCompanionEvaluationCreate,
    DesktopCompanionEvaluationRecord,
    DesktopCompanionEvaluationStore,
    DesktopCompanionReleaseGateReport,
    DesktopCompanionRolloutStatus,
    RolloutStage,
    default_desktop_companion_evaluation_store,
    resolve_desktop_companion_rollout,
)
from .operations import DesktopCompanionOperationalStatus, desktop_companion_operational_status
from .preflight import (
    DesktopCompanionPreflightRequest,
    DesktopCompanionPreflightResult,
    DesktopCompanionPreflightService,
    default_desktop_companion_preflight_service,
)
from .release_gate import (
    DesktopCompanionEvidencePartition,
    build_partitioned_desktop_companion_release_gate,
    build_partitioned_desktop_companion_speech_gate,
    desktop_companion_speech_canary_enabled,
)
from .runtime import (
    DesktopCompanionObserveRequest,
    DesktopCompanionObserveResponse,
    DesktopCompanionOrchestrator,
    default_desktop_companion_orchestrator,
)


class DesktopCompanionResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=160)
    capture_generation: str | None = Field(default=None, max_length=160)


class DesktopCompanionResetResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    reset: bool = True
    session_id: str


def register_desktop_companion_routes(
    app: FastAPI,
    *,
    evaluation_store_factory: Callable[[], DesktopCompanionEvaluationStore] = default_desktop_companion_evaluation_store,
    orchestrator_factory: Callable[[], DesktopCompanionOrchestrator] = default_desktop_companion_orchestrator,
    preflight_service_factory: Callable[[], DesktopCompanionPreflightService] = default_desktop_companion_preflight_service,
    build_identity_factory: Callable[[], DesktopCompanionBuildIdentity] = resolve_desktop_companion_build_identity,
    speech_canary_factory: Callable[[], bool] = desktop_companion_speech_canary_enabled,
    operational_status_factory: Callable[[], DesktopCompanionOperationalStatus] = desktop_companion_operational_status,
) -> None:
    @app.get(
        "/api/desktop-companion/operational-status",
        response_model=DesktopCompanionOperationalStatus,
        tags=["desktop-companion"],
        include_in_schema=False,
    )
    def desktop_companion_operations() -> DesktopCompanionOperationalStatus:
        return operational_status_factory()

    @app.get(
        "/api/desktop-companion/build-identity",
        response_model=DesktopCompanionBuildIdentity,
        tags=["desktop-companion"],
        include_in_schema=False,
    )
    def desktop_companion_build_identity() -> DesktopCompanionBuildIdentity:
        return build_identity_factory()

    @app.post(
        "/api/desktop-companion/preflight",
        response_model=DesktopCompanionPreflightResult,
        tags=["desktop-companion"],
        include_in_schema=False,
    )
    def preflight_desktop_companion(
        request: DesktopCompanionPreflightRequest,
    ) -> DesktopCompanionPreflightResult:
        operations = operational_status_factory()
        if not operations.available:
            return DesktopCompanionPreflightResult(
                ready=False,
                model_id=request.vision_model_id,
                reason=operations.reason,
            )
        return preflight_service_factory().check(request)

    @app.post(
        "/api/desktop-companion/observe",
        response_model=DesktopCompanionObserveResponse,
        tags=["desktop-companion"],
        include_in_schema=False,
    )
    def observe_desktop_companion(
        request: DesktopCompanionObserveRequest,
    ) -> DesktopCompanionObserveResponse:
        operations = operational_status_factory()
        if not operations.available:
            return DesktopCompanionObserveResponse(status="suppressed", reason=operations.reason)
        return orchestrator_factory().observe(request)

    @app.post(
        "/api/desktop-companion/reset",
        response_model=DesktopCompanionResetResponse,
        tags=["desktop-companion"],
        include_in_schema=False,
    )
    def reset_desktop_companion(
        request: DesktopCompanionResetRequest,
    ) -> DesktopCompanionResetResponse:
        orchestrator_factory().reset(request.session_id, request.capture_generation)
        return DesktopCompanionResetResponse(session_id=request.session_id)

    @app.post(
        "/api/desktop-companion/evaluations",
        response_model=DesktopCompanionEvaluationRecord,
        tags=["desktop-companion"],
        include_in_schema=False,
    )
    async def upsert_desktop_companion_evaluation(
        request: DesktopCompanionEvaluationCreate,
    ) -> DesktopCompanionEvaluationRecord:
        return evaluation_store_factory().upsert(request)

    @app.get(
        "/api/desktop-companion/evaluations",
        response_model=list[DesktopCompanionEvaluationRecord],
        tags=["desktop-companion"],
        include_in_schema=False,
    )
    async def list_desktop_companion_evaluations(
        limit: int = Query(default=100, ge=1, le=1_000),
        session_id: str | None = Query(default=None, max_length=160),
    ) -> list[DesktopCompanionEvaluationRecord]:
        return evaluation_store_factory().list(limit=limit, session_id=session_id)

    @app.get(
        "/api/desktop-companion/evaluations/export",
        response_model=dict,
        tags=["desktop-companion"],
        include_in_schema=False,
    )
    async def export_desktop_companion_evaluations() -> dict:
        return evaluation_store_factory().export()

    def evidence_partition(
        *,
        exact_commit_sha: str | None,
        observation_schema_version: int,
        attention_policy_version: int,
        vision_provider: str | None,
        vision_model_hash: str | None,
        remote_provider: bool | None,
    ) -> DesktopCompanionEvidencePartition:
        identity = build_identity_factory()
        return DesktopCompanionEvidencePartition(
            exact_commit_sha=exact_commit_sha or identity.exact_commit_sha,
            observation_schema_version=observation_schema_version,
            attention_policy_version=attention_policy_version,
            vision_provider=vision_provider,
            vision_model_hash=vision_model_hash,
            remote_provider=remote_provider,
        )

    @app.get(
        "/api/desktop-companion/release-gate",
        response_model=DesktopCompanionReleaseGateReport,
        tags=["desktop-companion"],
        include_in_schema=False,
    )
    async def desktop_companion_release_gate(
        stage: RolloutStage = Query(default="text"),
        exact_commit_sha: str | None = Query(default=None, min_length=7, max_length=64),
        observation_schema_version: int = Query(default=1, ge=1),
        attention_policy_version: int = Query(default=1, ge=1),
        vision_provider: str | None = Query(default=None, max_length=80),
        vision_model_hash: str | None = Query(default=None, max_length=128),
        remote_provider: bool | None = Query(default=None),
        limit: int = Query(default=1_000, ge=1, le=5_000),
    ) -> DesktopCompanionReleaseGateReport:
        partition = evidence_partition(
            exact_commit_sha=exact_commit_sha,
            observation_schema_version=observation_schema_version,
            attention_policy_version=attention_policy_version,
            vision_provider=vision_provider,
            vision_model_hash=vision_model_hash,
            remote_provider=remote_provider,
        )
        records = evaluation_store_factory().list(limit=limit)
        if stage == "speech":
            return build_partitioned_desktop_companion_speech_gate(records, partition)
        return build_partitioned_desktop_companion_release_gate(records, partition)

    @app.get(
        "/api/desktop-companion/rollout-status",
        response_model=DesktopCompanionRolloutStatus,
        tags=["desktop-companion"],
        include_in_schema=False,
    )
    async def desktop_companion_rollout_status(
        requested_stage: RolloutStage = Query(default="disabled"),
        exact_commit_sha: str | None = Query(default=None, min_length=7, max_length=64),
        observation_schema_version: int = Query(default=1, ge=1),
        attention_policy_version: int = Query(default=1, ge=1),
        vision_provider: str | None = Query(default=None, max_length=80),
        vision_model_hash: str | None = Query(default=None, max_length=128),
        remote_provider: bool | None = Query(default=None),
        limit: int = Query(default=1_000, ge=1, le=5_000),
    ) -> DesktopCompanionRolloutStatus:
        operations = operational_status_factory()
        if not operations.available:
            return DesktopCompanionRolloutStatus(
                requested_stage=requested_stage,
                effective_stage="disabled",
                enabled=False,
                reason=operations.reason,
                release_gate_status="insufficient",
                evidence_evaluation_ids=(),
            )
        partition = evidence_partition(
            exact_commit_sha=exact_commit_sha,
            observation_schema_version=observation_schema_version,
            attention_policy_version=attention_policy_version,
            vision_provider=vision_provider,
            vision_model_hash=vision_model_hash,
            remote_provider=remote_provider,
        )
        records = evaluation_store_factory().list(limit=limit)
        text_report = build_partitioned_desktop_companion_release_gate(records, partition)
        if requested_stage != "speech":
            return resolve_desktop_companion_rollout(requested_stage, text_report)
        if text_report.status != "pass":
            return resolve_desktop_companion_rollout(requested_stage, text_report)
        speech_report = build_partitioned_desktop_companion_speech_gate(records, partition)
        if speech_report.status == "pass":
            return DesktopCompanionRolloutStatus(
                requested_stage="speech",
                effective_stage="speech",
                enabled=True,
                reason="speech_rollout_gate_passed",
                release_gate_status="pass",
                evidence_evaluation_ids=speech_report.evidence_evaluation_ids,
            )
        if speech_canary_factory():
            return DesktopCompanionRolloutStatus(
                requested_stage="speech",
                effective_stage="speech",
                enabled=True,
                reason="speech_validation_canary",
                release_gate_status=speech_report.status,
                evidence_evaluation_ids=speech_report.evidence_evaluation_ids,
            )
        return DesktopCompanionRolloutStatus(
            requested_stage="speech",
            effective_stage="text",
            enabled=True,
            reason="speech_evidence_missing",
            release_gate_status=speech_report.status,
            evidence_evaluation_ids=text_report.evidence_evaluation_ids,
        )


__all__ = ["register_desktop_companion_routes"]
