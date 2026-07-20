"""Player-safe Campaign Genesis progress and Lore routes."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from app.rpg.session.genesis.campaign_lore_api import (
    LoreDocumentForbidden,
    LoreDocumentNotFound,
    campaign_genesis_progress_payload,
    campaign_lore_document_payload,
    campaign_lore_payload,
    transition_lore_discovery,
)
from app.rpg.session.genesis.campaign_lore_store import (
    LoreRegenerationUnavailable,
    load_campaign_lore,
    persist_campaign_lore,
    regenerate_campaign_lore_document,
)
from app.rpg.session.genesis.runtime_materialization import (
    RuntimeMaterializationConflict,
    RuntimeMaterializationUnavailable,
    materialize_runtime_lore,
)
from app.rpg.session.service import load_session


class LoreDiscoveryRequest(BaseModel):
    document_id: str
    status: str
    source: str = "gameplay"


class LoreRegenerationRequest(BaseModel):
    document_id: str = Field(min_length=1, max_length=300)
    direction: str = Field(default="", max_length=1000)


class LoreMaterializationRequest(BaseModel):
    kind: Literal["creature", "location"]
    name: str = Field(min_length=1, max_length=120)
    direction: str = Field(default="", max_length=1000)
    document_id: str = Field(default="", max_length=300)


def _session_or_404(session_id: str) -> dict[str, Any]:
    session = load_session(session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail={
                "ok": False,
                "error": "session_not_found",
                "session_id": session_id,
            },
        )
    return session


def _kick_genesis_recovery() -> None:
    from app.rpg.session.genesis.async_coordinator import (
        campaign_genesis_async_enabled,
        kick_campaign_genesis_worker,
    )

    if campaign_genesis_async_enabled():
        kick_campaign_genesis_worker()


def _lore_error(exc: Exception, session_id: str) -> HTTPException:
    if isinstance(exc, LoreDocumentNotFound):
        return HTTPException(
            status_code=404,
            detail={
                "ok": False,
                "error": "lore_document_not_found",
                "session_id": session_id,
            },
        )
    if isinstance(exc, LoreDocumentForbidden):
        return HTTPException(
            status_code=403,
            detail={
                "ok": False,
                "error": "lore_document_not_visible",
                "session_id": session_id,
            },
        )
    return HTTPException(
        status_code=400,
        detail={
            "ok": False,
            "error": "invalid_lore_discovery_transition",
            "session_id": session_id,
            "message": str(exc),
        },
    )


def register_rpg_campaign_lore_routes(app: FastAPI) -> None:
    @app.on_event("startup")
    async def recover_rpg_campaign_genesis_jobs() -> None:
        _kick_genesis_recovery()

    @app.get(
        "/api/rpg/sessions/{session_id}/campaign-genesis",
        tags=["rpg-session"],
        include_in_schema=False,
    )
    def rpg_campaign_genesis(session_id: str) -> dict[str, Any]:
        _kick_genesis_recovery()
        session = _session_or_404(session_id)
        session, storage = load_campaign_lore(
            session_id,
            session,
            ensure_current_location=False,
        )
        return {
            "ok": True,
            "session_id": session_id,
            "generation": campaign_genesis_progress_payload(session),
            "storage": storage,
        }

    @app.get(
        "/api/rpg/sessions/{session_id}/lore",
        tags=["rpg-session"],
        include_in_schema=False,
    )
    def rpg_campaign_lore(session_id: str) -> dict[str, Any]:
        session = _session_or_404(session_id)
        session, storage = load_campaign_lore(
            session_id,
            session,
            ensure_current_location=True,
        )
        return {
            **campaign_lore_payload(session),
            "session_id": session_id,
            "storage": storage,
        }

    @app.get(
        "/api/rpg/sessions/{session_id}/lore/document",
        tags=["rpg-session"],
        include_in_schema=False,
    )
    def rpg_campaign_lore_document(
        session_id: str,
        document_id: str = Query(min_length=1, max_length=300),
    ) -> dict[str, Any]:
        session = _session_or_404(session_id)
        session, storage = load_campaign_lore(
            session_id,
            session,
            ensure_current_location=True,
        )
        try:
            return {
                **campaign_lore_document_payload(
                    session,
                    document_id,
                ),
                "session_id": session_id,
                "storage": storage,
            }
        except Exception as exc:
            raise _lore_error(exc, session_id) from exc

    @app.post(
        "/api/rpg/sessions/{session_id}/lore/regenerate",
        tags=["rpg-session"],
        include_in_schema=False,
    )
    def rpg_campaign_lore_regenerate(
        session_id: str,
        request: LoreRegenerationRequest,
    ) -> dict[str, Any]:
        session = _session_or_404(session_id)
        try:
            updated, storage = regenerate_campaign_lore_document(
                session_id,
                session,
                document_id=request.document_id,
                direction=request.direction,
            )
            return {
                "ok": True,
                "session_id": session_id,
                "document": campaign_lore_document_payload(
                    updated,
                    request.document_id,
                )["document"],
                "lore": {
                    **campaign_lore_payload(updated),
                    "session_id": session_id,
                    "storage": storage,
                },
                "storage": storage,
            }
        except (LoreDocumentNotFound, LoreDocumentForbidden) as exc:
            raise _lore_error(exc, session_id) from exc
        except LoreRegenerationUnavailable as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "ok": False,
                    "error": "lore_regeneration_unavailable",
                    "session_id": session_id,
                    "message": str(exc),
                },
            ) from exc

    @app.post(
        "/api/rpg/sessions/{session_id}/lore/discovery",
        tags=["rpg-session"],
        include_in_schema=False,
    )
    def rpg_campaign_lore_discovery(
        session_id: str,
        request: LoreDiscoveryRequest,
    ) -> dict[str, Any]:
        session = _session_or_404(session_id)
        session, _storage = load_campaign_lore(
            session_id,
            session,
            ensure_current_location=True,
        )
        try:
            updated = transition_lore_discovery(
                session,
                document_id=request.document_id,
                status=request.status,
                source=request.source,
            )
            saved, storage = persist_campaign_lore(session_id, updated)
            return {
                "ok": True,
                "session_id": session_id,
                "document_id": request.document_id,
                "status": request.status,
                "lore": campaign_lore_payload(saved),
                "storage": storage,
            }
        except Exception as exc:
            raise _lore_error(exc, session_id) from exc

    @app.post(
        "/api/rpg/sessions/{session_id}/lore/materialize",
        tags=["rpg-session"],
        include_in_schema=False,
    )
    def rpg_campaign_lore_materialize(
        session_id: str,
        request: LoreMaterializationRequest,
    ) -> dict[str, Any]:
        session = _session_or_404(session_id)
        try:
            updated, storage = materialize_runtime_lore(
                session_id,
                session,
                kind=request.kind,
                name=request.name,
                direction=request.direction,
                document_id=request.document_id,
            )
            document_id = str(storage["document_id"])
            return {
                "ok": True,
                "session_id": session_id,
                "document": campaign_lore_document_payload(
                    updated,
                    document_id,
                )["document"],
                "definition": storage["definition"],
                "lore": {
                    **campaign_lore_payload(updated),
                    "session_id": session_id,
                    "storage": storage,
                },
                "storage": storage,
            }
        except RuntimeMaterializationConflict as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "ok": False,
                    "error": "runtime_materialization_conflict",
                    "session_id": session_id,
                    "message": str(exc),
                },
            ) from exc
        except RuntimeMaterializationUnavailable as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "ok": False,
                    "error": "runtime_materialization_unavailable",
                    "session_id": session_id,
                    "message": str(exc),
                },
            ) from exc
