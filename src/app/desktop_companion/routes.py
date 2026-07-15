"""Internal Desktop Companion evaluation and rollout endpoints."""
from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, Query

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


def register_desktop_companion_routes(
    app: FastAPI,
    *,
    evaluation_store_factory: Callable[[], DesktopCompanionEvaluationStore] = default_desktop_companion_evaluation_store,
) -> None:
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
