"""Hidden local APIs for durable content-free Live Chat evaluation."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, FastAPI, HTTPException, Query

from .live_chat_evaluation_store import (
    LiveChatEvaluationStore,
    PresencePolicyVersion,
    PresencePolicyVersionCreate,
    VoiceSessionEvaluationCreate,
    VoiceSessionEvaluationRecord,
    default_live_chat_evaluation_store,
)
from .live_chat_release_aggregation import evaluate_durable_live_chat_records
from .live_chat_release_gate import LiveChatReleaseGateReport

_ROUTE_SENTINEL = "_omnix_live_chat_evaluation_routes_registered"


def register_live_chat_evaluation_routes(
    gateway: FastAPI,
    *,
    store: LiveChatEvaluationStore | None = None,
) -> None:
    if getattr(gateway.state, _ROUTE_SENTINEL, False):
        return
    setattr(gateway.state, _ROUTE_SENTINEL, True)
    evaluation_store = store or default_live_chat_evaluation_store()
    router = APIRouter(prefix="/api/tts/live-call", include_in_schema=False)

    @router.post("/evaluations", response_model=VoiceSessionEvaluationRecord)
    async def upsert_voice_session_evaluation(
        request: VoiceSessionEvaluationCreate,
    ) -> VoiceSessionEvaluationRecord:
        return evaluation_store.upsert(request)

    @router.get("/evaluations", response_model=list[VoiceSessionEvaluationRecord])
    async def list_voice_session_evaluations(
        session_id: str | None = None,
        presence_preset: str | None = None,
        limit: Annotated[int, Query(ge=1, le=1_000)] = 100,
    ) -> list[VoiceSessionEvaluationRecord]:
        if presence_preset not in {None, "quiet", "natural", "engaged", "listener"}:
            raise HTTPException(status_code=422, detail="unknown presence preset")
        return evaluation_store.list(
            session_id=session_id,
            presence_preset=presence_preset,  # type: ignore[arg-type]
            limit=limit,
        )

    @router.get("/evaluations/release-gate", response_model=LiveChatReleaseGateReport)
    async def evaluate_durable_voice_session_evidence(
        limit: Annotated[int, Query(ge=1, le=1_000)] = 1_000,
        persist_status: bool = True,
    ) -> LiveChatReleaseGateReport:
        records = evaluation_store.list(limit=limit)
        report = evaluate_durable_live_chat_records(records)
        if persist_status:
            for record in records:
                evaluation_store.update_release_gate_status(record.evaluation_id, report.status)
        return report

    @router.get("/evaluations/export")
    async def export_voice_session_evaluations() -> dict:
        return evaluation_store.export()

    @router.get("/evaluations/{evaluation_id}", response_model=VoiceSessionEvaluationRecord)
    async def get_voice_session_evaluation(evaluation_id: str) -> VoiceSessionEvaluationRecord:
        record = evaluation_store.get(evaluation_id)
        if record is None:
            raise HTTPException(status_code=404, detail="voice session evaluation not found")
        return record

    @router.get("/presence-presets", response_model=dict[str, PresencePolicyVersion])
    async def active_presence_policies() -> dict[str, PresencePolicyVersion]:
        return evaluation_store.active_policies()

    @router.get("/presence-presets/versions", response_model=list[PresencePolicyVersion])
    async def list_presence_policy_versions(
        preset: str | None = None,
    ) -> list[PresencePolicyVersion]:
        if preset not in {None, "quiet", "natural", "engaged", "listener"}:
            raise HTTPException(status_code=422, detail="unknown presence preset")
        return evaluation_store.list_policy_versions(preset)  # type: ignore[arg-type]

    @router.post("/presence-presets/{preset}/versions", response_model=PresencePolicyVersion)
    async def create_presence_policy_version(
        preset: str,
        request: PresencePolicyVersionCreate,
    ) -> PresencePolicyVersion:
        if preset not in {"quiet", "natural", "engaged", "listener"}:
            raise HTTPException(status_code=422, detail="unknown presence preset")
        try:
            return evaluation_store.create_policy_version(preset, request)  # type: ignore[arg-type]
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/presence-presets/{preset}/activate/{version}", response_model=PresencePolicyVersion)
    async def activate_presence_policy(preset: str, version: int) -> PresencePolicyVersion:
        if preset not in {"quiet", "natural", "engaged", "listener"}:
            raise HTTPException(status_code=422, detail="unknown presence preset")
        try:
            return evaluation_store.activate_policy(preset, version)  # type: ignore[arg-type]
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.post("/presence-presets/{preset}/rollback", response_model=PresencePolicyVersion)
    async def rollback_presence_policy(preset: str) -> PresencePolicyVersion:
        if preset not in {"quiet", "natural", "engaged", "listener"}:
            raise HTTPException(status_code=422, detail="unknown presence preset")
        try:
            return evaluation_store.rollback_policy(preset)  # type: ignore[arg-type]
        except KeyError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    gateway.include_router(router)
