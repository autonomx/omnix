"""Player-safe Campaign Genesis progress and Lore routes."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from app.rpg.session.genesis.campaign_lore_api import (
    LoreDocumentForbidden,
    LoreDocumentNotFound,
    campaign_genesis_progress_payload,
    campaign_lore_document_payload,
    campaign_lore_payload,
    transition_lore_discovery,
)
from app.rpg.session.service import load_session, save_session


class LoreDiscoveryRequest(BaseModel):
    document_id: str
    status: str
    source: str = "gameplay"


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
        return {
            "ok": True,
            "session_id": session_id,
            "generation": campaign_genesis_progress_payload(session),
        }

    @app.get(
        "/api/rpg/sessions/{session_id}/lore",
        tags=["rpg-session"],
        include_in_schema=False,
    )
    def rpg_campaign_lore(session_id: str) -> dict[str, Any]:
        session = _session_or_404(session_id)
        return {
            **campaign_lore_payload(session),
            "session_id": session_id,
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
        try:
            return {
                **campaign_lore_document_payload(
                    session,
                    document_id,
                ),
                "session_id": session_id,
            }
        except Exception as exc:
            raise _lore_error(exc, session_id) from exc

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
        try:
            updated = transition_lore_discovery(
                session,
                document_id=request.document_id,
                status=request.status,
                source=request.source,
            )
            saved = save_session(updated, compact=True)
            return {
                "ok": True,
                "session_id": session_id,
                "document_id": request.document_id,
                "status": request.status,
                "lore": campaign_lore_payload(saved),
            }
        except Exception as exc:
            raise _lore_error(exc, session_id) from exc
