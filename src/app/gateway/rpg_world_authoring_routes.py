"""World-authoring projections and metadata routes."""
from __future__ import annotations

from typing import Any, Mapping

from fastapi import FastAPI, HTTPException, Request

from app.rpg.worlds.authoring_service import (
    read_authoring_manifest,
    read_authoring_section,
    update_world_metadata,
)

_ROUTE_SENTINEL = "_omnix_rpg_world_authoring_routes_registered"


def _body(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise HTTPException(
            status_code=422,
            detail={"ok": False, "error": "request_body_must_be_object"},
        )
    return value


def _raise_domain_error(exc: Exception) -> None:
    if isinstance(exc, KeyError):
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "error": str(exc).strip("'")},
        ) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(
            status_code=409,
            detail={"ok": False, "error": str(exc)},
        ) from exc
    raise exc


def register_rpg_world_authoring_routes(app: FastAPI) -> None:
    if getattr(app.state, _ROUTE_SENTINEL, False):
        return
    setattr(app.state, _ROUTE_SENTINEL, True)

    @app.get(
        "/api/rpg/worlds/{world_id}/authoring-manifest",
        tags=["rpg-world"],
        include_in_schema=False,
    )
    def rpg_world_authoring_manifest(world_id: str) -> dict[str, Any]:
        try:
            return read_authoring_manifest(world_id)
        except Exception as exc:
            _raise_domain_error(exc)
            raise

    @app.get(
        "/api/rpg/worlds/{world_id}/authoring-sections/{section_id}",
        tags=["rpg-world"],
        include_in_schema=False,
    )
    def rpg_world_authoring_section(
        world_id: str,
        section_id: str,
    ) -> dict[str, Any]:
        try:
            return read_authoring_section(world_id, section_id)
        except Exception as exc:
            _raise_domain_error(exc)
            raise

    @app.patch(
        "/api/rpg/worlds/{world_id}",
        tags=["rpg-world"],
        include_in_schema=False,
    )
    async def rpg_update_world_metadata(
        world_id: str,
        request: Request,
    ) -> dict[str, Any]:
        payload = dict(_body(await request.json()))
        expected_revision = int(payload.pop("expected_draft_revision", 0) or 0)
        if expected_revision < 1:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "error": "expected_draft_revision_required"},
            )
        try:
            return update_world_metadata(
                world_id,
                expected_draft_revision=expected_revision,
                changes=payload,
            )
        except Exception as exc:
            _raise_domain_error(exc)
            raise
