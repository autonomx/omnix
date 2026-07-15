"""Internal Desktop Companion observation, evaluation, and rollout endpoints."""
from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, Query
from pydantic import BaseModel, ConfigDict, Field

from .evaluation import (
    DesktopCompanionEvaluationCreate,
    DesktopCompanionEvaluationRecord,
    DesktopCompanionEvaluationStore,
    DesktopCompanionReleaseGateReport,
    DesktopCompanionRolloutStatus,
    RolloutStage,
    build_desktop_companion_release_gate,
    default_desktop_companion_evaluation_store,
    resolve_desktop_companion_rollout,
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
) -> None:
    @app.post(
        "/api/desktop-companion/observe",
        response_model=DesktopCompanionObserveResponse,
        tags=["desktop-companion"],
        include_in_schema=False,
    )
    def observe_desktop_companion(
        request: DesktopCompanionObserveRequest,
    ) -> DesktopCompanionObserveResponse:
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

    @app.get(
        "/api/desktop-companion/release-gate",
        response_model=DesktopCompanionReleaseGateReport,
        tags=["desktop-companion"],
        include_in_schema=False,
    )
    async def desktop_companion_release_gate(
        limit: int = Query(default=1_000, ge=1, le=5_000),
    ) -> DesktopCompanionReleaseGateReport:
        records = evaluation_store_factory().list(limit=limit)
        return build_desktop_companion_release_gate(records)

    @app.get(
        "/api/desktop-companion/rollout-status",
        response_model=DesktopCompanionRolloutStatus,
        tags=["desktop-companion"],
        include_in_schema=False,
    )
    async def desktop_companion_rollout_status(
        requested_stage: RolloutStage = Query(default="disabled"),
        limit: int = Query(default=1_000, ge=1, le=5_000),
    ) -> DesktopCompanionRolloutStatus:
        records = evaluation_store_factory().list(limit=limit)
        report = build_desktop_companion_release_gate(records)
        return resolve_desktop_companion_rollout(requested_stage, report)


__all__ = ["register_desktop_companion_routes"]
