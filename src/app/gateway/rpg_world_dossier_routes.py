"""Editorial-only rich dossier routes for reusable RPG world entities."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Mapping

from fastapi import FastAPI, HTTPException, Request

from app.rpg.worlds.dossier_authoring import (
    regenerate_world_entity_dossier,
    update_world_entity_dossier,
)
from app.rpg.worlds.dossier_quality_service import (
    enrich_world_dossiers,
    world_dossier_quality,
)
from app.rpg.worlds.dossier_regeneration_preview import (
    preview_world_entity_dossier_regeneration,
)

_ROUTE_SENTINEL = "_omnix_rpg_world_dossier_routes_registered"
_HOOK_SENTINEL = "_omnix_rpg_world_dossier_route_hook_installed"


def _body(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise HTTPException(
            status_code=422,
            detail={"ok": False, "error": "request_body_must_be_object"},
        )
    return value


def _expected(payload: Mapping[str, Any]) -> tuple[int, str]:
    revision = int(payload.get("expected_draft_revision") or 0)
    content_hash = str(payload.get("expected_content_hash") or "").strip()
    if revision < 1 or not content_hash:
        raise HTTPException(
            status_code=422,
            detail={
                "ok": False,
                "error": "expected_draft_revision_and_content_hash_required",
            },
        )
    return revision, content_hash


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


def register_rpg_world_dossier_routes(app: FastAPI) -> None:
    if getattr(app.state, _ROUTE_SENTINEL, False):
        return
    setattr(app.state, _ROUTE_SENTINEL, True)

    @app.get(
        "/api/rpg/worlds/{world_id}/dossier-quality",
        tags=["rpg-world"],
        include_in_schema=False,
    )
    def rpg_world_dossier_quality(world_id: str) -> dict[str, Any]:
        try:
            return world_dossier_quality(world_id)
        except Exception as exc:
            _raise_domain_error(exc)
            raise

    @app.post(
        "/api/rpg/worlds/{world_id}/enrich-dossiers",
        tags=["rpg-world"],
        include_in_schema=False,
    )
    async def rpg_enrich_world_dossiers(
        world_id: str,
        request: Request,
    ) -> dict[str, Any]:
        payload = dict(_body(await request.json()))
        directives = payload.get("directives")
        if directives is not None and not isinstance(directives, Mapping):
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "error": "entity_directives_must_be_object"},
            )
        try:
            return enrich_world_dossiers(
                world_id,
                limit=max(1, min(int(payload.get("limit") or 10), 25)),
                all_candidates=bool(payload.get("all_candidates", False)),
                dry_run=bool(payload.get("dry_run", True)),
                directives=dict(directives or {}),
            )
        except Exception as exc:
            _raise_domain_error(exc)
            raise

    @app.patch(
        "/api/rpg/worlds/{world_id}/topics/{topic_id}/entities/{entity_id}/dossier",
        tags=["rpg-world"],
        include_in_schema=False,
    )
    async def rpg_update_world_entity_dossier(
        world_id: str,
        topic_id: str,
        entity_id: str,
        request: Request,
    ) -> dict[str, Any]:
        payload = dict(_body(await request.json()))
        revision, content_hash = _expected(payload)
        dossier = payload.get("dossier")
        if not isinstance(dossier, Mapping):
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "error": "entity_dossier_required"},
            )
        try:
            return update_world_entity_dossier(
                world_id,
                topic_id,
                entity_id,
                expected_draft_revision=revision,
                expected_content_hash=content_hash,
                short_summary=str(payload.get("short_summary") or ""),
                dossier=dossier,
            )
        except Exception as exc:
            _raise_domain_error(exc)
            raise

    @app.post(
        "/api/rpg/worlds/{world_id}/topics/{topic_id}/entities/{entity_id}/regenerate-dossier-preview",
        tags=["rpg-world"],
        include_in_schema=False,
    )
    async def rpg_preview_world_entity_dossier_regeneration(
        world_id: str,
        topic_id: str,
        entity_id: str,
        request: Request,
    ) -> dict[str, Any]:
        payload = dict(_body(await request.json()))
        revision, content_hash = _expected(payload)
        directives = payload.get("directives")
        if directives is not None and not isinstance(directives, Mapping):
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "error": "entity_directives_must_be_object"},
            )
        try:
            return preview_world_entity_dossier_regeneration(
                world_id,
                topic_id,
                entity_id,
                expected_draft_revision=revision,
                expected_content_hash=content_hash,
                directives=dict(directives or {}),
            )
        except Exception as exc:
            _raise_domain_error(exc)
            raise

    @app.post(
        "/api/rpg/worlds/{world_id}/topics/{topic_id}/entities/{entity_id}/regenerate-dossier",
        tags=["rpg-world"],
        include_in_schema=False,
    )
    async def rpg_regenerate_world_entity_dossier(
        world_id: str,
        topic_id: str,
        entity_id: str,
        request: Request,
    ) -> dict[str, Any]:
        payload = dict(_body(await request.json()))
        revision, content_hash = _expected(payload)
        directives = payload.get("directives")
        if directives is not None and not isinstance(directives, Mapping):
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "error": "entity_directives_must_be_object"},
            )
        try:
            return regenerate_world_entity_dossier(
                world_id,
                topic_id,
                entity_id,
                expected_draft_revision=revision,
                expected_content_hash=content_hash,
                directives=dict(directives or {}),
            )
        except Exception as exc:
            _raise_domain_error(exc)
            raise


def install_rpg_world_dossier_route_hook() -> None:
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return
    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if kwargs.get("title") == "Omnix Web Gateway" or (
            args and args[0] == "Omnix Web Gateway"
        ):
            register_rpg_world_dossier_routes(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)
