"""Community world routes: browse and download shared worlds, adopt one, and share your own by pull request."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from app.persistence.unit_of_work import unit_of_work
from app.runtime.tenant_context import current_tenant
from app.apps.rpg.genesis.worlds.world_adoption import adopt_shared_world, shared_world_state
from app.apps.rpg.genesis.worlds.world_catalog import catalog_cover, import_catalog_world, list_catalog
from app.apps.rpg.genesis.worlds.world_sharing import (
    GitHubError,
    connect_with_token,
    disconnect,
    poll_device_sign_in,
    share_world,
    sharing_status,
    start_device_sign_in,
)
from app.apps.rpg.edge.api.web_contracts import (
    RpgGitHubDeviceSignInResponse,
    RpgSharedWorldStateResponse,
    RpgWorldAdoptionResponse,
    RpgWorldCatalogInstallResponse,
    RpgWorldCatalogResponse,
    RpgWorldShareResponse,
    RpgWorldSharingStatusResponse,
    documented,
)

_ROUTE_SENTINEL = "_omnix_rpg_world_sharing_routes_registered"


class RpgWorldAdoptRequestBody(BaseModel):
    bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class RpgWorldShareRequestBody(BaseModel):
    summary: str = Field(default="", max_length=2000)


class RpgGitHubTokenRequestBody(BaseModel):
    token: str = Field(min_length=1, max_length=500)


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, KeyError):
        return HTTPException(status_code=404, detail={"ok": False, "error": str(exc).strip("'")})
    if isinstance(exc, GitHubError):
        return HTTPException(status_code=502, detail={"ok": False, "error": str(exc)})
    return HTTPException(status_code=409, detail={"ok": False, "error": str(exc)})


def register_rpg_world_sharing_routes(router: APIRouter, state) -> None:
    if getattr(state, _ROUTE_SENTINEL, False):
        return
    setattr(state, _ROUTE_SENTINEL, True)

    @router.get("/api/rpg/world-catalog", tags=["rpg-world"], responses=documented(RpgWorldCatalogResponse))
    def rpg_world_catalog() -> dict[str, Any]:
        try:
            return list_catalog()
        except (KeyError, ValueError) as exc:
            raise _error(exc) from exc

    @router.get(
        "/api/rpg/world-catalog/{entry_id}/cover",
        tags=["rpg-world"],
        response_class=Response,
        responses={200: {"description": "The catalog world's cover image.", "content": {"image/webp": {}}}},
    )
    def rpg_world_catalog_cover(entry_id: str) -> Response:
        try:
            content, media_type = catalog_cover(entry_id)
        except (KeyError, ValueError) as exc:
            raise _error(exc) from exc
        return Response(
            content=content,
            media_type=media_type,
            headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"},
        )

    @router.post(
        "/api/rpg/world-catalog/{entry_id}/install",
        tags=["rpg-world"],
        responses=documented(RpgWorldCatalogInstallResponse),
    )
    def rpg_world_catalog_install(entry_id: str) -> dict[str, Any]:
        try:
            return import_catalog_world(entry_id)
        except (KeyError, ValueError) as exc:
            raise _error(exc) from exc

    @router.get("/api/rpg/worlds/{world_id}/shared", tags=["rpg-world"], responses=documented(RpgSharedWorldStateResponse))
    def rpg_world_shared_state(world_id: str) -> dict[str, Any]:
        context = current_tenant()
        with unit_of_work() as work:
            world = work.world_scenarios.get_world(context, world_id)
            work.rollback()
        if world is None:
            raise _error(KeyError(f"world_not_found:{world_id}"))
        return {"ok": True, "world_id": world_id, **shared_world_state(world)}

    @router.post("/api/rpg/worlds/{world_id}/adopt", tags=["rpg-world"], responses=documented(RpgWorldAdoptionResponse))
    def rpg_world_adopt(world_id: str, request_body: RpgWorldAdoptRequestBody) -> dict[str, Any]:
        try:
            return adopt_shared_world(world_id, bundle_sha256=request_body.bundle_sha256)
        except (KeyError, ValueError) as exc:
            raise _error(exc) from exc

    @router.post("/api/rpg/worlds/{world_id}/share", tags=["rpg-world"], responses=documented(RpgWorldShareResponse))
    def rpg_world_share(world_id: str, request_body: RpgWorldShareRequestBody) -> dict[str, Any]:
        try:
            return share_world(world_id, summary=request_body.summary)
        except (KeyError, ValueError) as exc:
            raise _error(exc) from exc

    @router.get("/api/rpg/world-sharing/github", tags=["rpg-world"], responses=documented(RpgWorldSharingStatusResponse))
    def rpg_world_sharing_github() -> dict[str, Any]:
        return sharing_status()

    @router.put(
        "/api/rpg/world-sharing/github/token",
        tags=["rpg-world"],
        responses=documented(RpgWorldSharingStatusResponse),
    )
    def rpg_world_sharing_github_token(request_body: RpgGitHubTokenRequestBody) -> dict[str, Any]:
        try:
            return connect_with_token(request_body.token)
        except ValueError as exc:
            raise _error(exc) from exc

    @router.post(
        "/api/rpg/world-sharing/github/device",
        tags=["rpg-world"],
        responses=documented(RpgGitHubDeviceSignInResponse),
    )
    def rpg_world_sharing_github_device() -> dict[str, Any]:
        try:
            return start_device_sign_in()
        except ValueError as exc:
            raise _error(exc) from exc

    @router.post(
        "/api/rpg/world-sharing/github/device/{flow_id}/poll",
        tags=["rpg-world"],
        responses=documented(RpgWorldSharingStatusResponse),
    )
    def rpg_world_sharing_github_device_poll(flow_id: str) -> dict[str, Any]:
        try:
            return poll_device_sign_in(flow_id)
        except ValueError as exc:
            raise _error(exc) from exc

    @router.delete(
        "/api/rpg/world-sharing/github",
        tags=["rpg-world"],
        responses=documented(RpgWorldSharingStatusResponse),
    )
    def rpg_world_sharing_github_disconnect() -> dict[str, Any]:
        return disconnect()


__all__ = ["register_rpg_world_sharing_routes"]
