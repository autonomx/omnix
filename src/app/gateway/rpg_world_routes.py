"""Gateway routes for reusable RPG worlds, releases, and scenarios."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Mapping

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import ValidationError

from app.rpg.worlds.contracts import (
    CampaignWorldBinding,
    ScenarioProjectCreate,
    ScenarioRevisionDocument,
    WorldProjectCreate,
    WorldReleaseDocument,
    WorldRevisionDocument,
)
from app.rpg.worlds.postgres_service import (
    bind_campaign_world,
    create_scenario_project,
    create_world_project,
    list_world_projects,
    publish_scenario_revision,
    publish_world_release,
    publish_world_revision,
    read_campaign_world_binding,
)

_ROUTE_SENTINEL = "_omnix_rpg_world_routes_registered"
_HOOK_SENTINEL = "_omnix_rpg_world_route_hook_installed"


def _body(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise HTTPException(
            status_code=422,
            detail={"ok": False, "error": "request_body_must_be_object"},
        )
    return value


def _validation_error(exc: ValidationError) -> HTTPException:
    return HTTPException(status_code=422, detail=exc.errors())


def register_rpg_world_routes(app: FastAPI) -> None:
    if getattr(app.state, _ROUTE_SENTINEL, False):
        return
    setattr(app.state, _ROUTE_SENTINEL, True)

    @app.get(
        "/api/rpg/worlds",
        tags=["rpg-world"],
        include_in_schema=False,
    )
    def rpg_list_worlds(
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict[str, Any]:
        return {"ok": True, "worlds": list_world_projects(limit=limit)}

    @app.post(
        "/api/rpg/worlds",
        tags=["rpg-world"],
        include_in_schema=False,
    )
    async def rpg_create_world(request: Request) -> dict[str, Any]:
        try:
            contract = WorldProjectCreate.model_validate(_body(await request.json()))
            return {"ok": True, "world": create_world_project(contract)}
        except ValidationError as exc:
            raise _validation_error(exc) from exc

    @app.post(
        "/api/rpg/worlds/{world_id}/revisions",
        tags=["rpg-world"],
        include_in_schema=False,
    )
    async def rpg_publish_world_revision(
        world_id: str,
        request: Request,
    ) -> dict[str, Any]:
        raw = dict(_body(await request.json()))
        raw["world_id"] = world_id
        try:
            document = WorldRevisionDocument.model_validate(raw)
            expected_revision = max(0, document.revision - 1)
            stored = publish_world_revision(
                document,
                expected_revision=expected_revision,
            )
            return {"ok": True, "world_revision": stored}
        except ValidationError as exc:
            raise _validation_error(exc) from exc

    @app.post(
        "/api/rpg/worlds/{world_id}/revisions/{world_revision}/releases",
        tags=["rpg-world"],
        include_in_schema=False,
    )
    async def rpg_publish_world_release(
        world_id: str,
        world_revision: int,
        request: Request,
    ) -> dict[str, Any]:
        raw = dict(_body(await request.json()))
        raw["world_id"] = world_id
        raw["world_revision"] = world_revision
        try:
            document = WorldReleaseDocument.model_validate(raw)
            stored = publish_world_release(document)
            return {"ok": True, "world_release": stored}
        except ValidationError as exc:
            raise _validation_error(exc) from exc

    @app.post(
        "/api/rpg/scenarios",
        tags=["rpg-world"],
        include_in_schema=False,
    )
    async def rpg_create_scenario(request: Request) -> dict[str, Any]:
        try:
            contract = ScenarioProjectCreate.model_validate(_body(await request.json()))
            return {"ok": True, "scenario": create_scenario_project(contract)}
        except ValidationError as exc:
            raise _validation_error(exc) from exc

    @app.post(
        "/api/rpg/scenarios/{scenario_id}/revisions",
        tags=["rpg-world"],
        include_in_schema=False,
    )
    async def rpg_publish_scenario_revision(
        scenario_id: str,
        request: Request,
    ) -> dict[str, Any]:
        raw = dict(_body(await request.json()))
        raw["scenario_id"] = scenario_id
        try:
            document = ScenarioRevisionDocument.model_validate(raw)
            stored = publish_scenario_revision(document)
            return {"ok": True, "scenario_revision": stored}
        except ValidationError as exc:
            raise _validation_error(exc) from exc

    @app.get(
        "/api/rpg/campaigns/{campaign_id}/world-binding",
        tags=["rpg-world"],
        include_in_schema=False,
    )
    def rpg_read_campaign_world_binding(campaign_id: str) -> dict[str, Any]:
        binding = read_campaign_world_binding(campaign_id)
        if binding is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "ok": False,
                    "error": "campaign_world_binding_not_found",
                    "campaign_id": campaign_id,
                },
            )
        return {"ok": True, "binding": binding}

    @app.post(
        "/api/rpg/campaigns/{campaign_id}/world-binding",
        tags=["rpg-world"],
        include_in_schema=False,
    )
    async def rpg_bind_campaign_world(
        campaign_id: str,
        request: Request,
    ) -> dict[str, Any]:
        raw = dict(_body(await request.json()))
        raw["campaign_id"] = campaign_id
        try:
            binding = CampaignWorldBinding.model_validate(raw)
            return {"ok": True, "binding": bind_campaign_world(binding)}
        except ValidationError as exc:
            raise _validation_error(exc) from exc


def install_rpg_world_route_hook() -> None:
    if getattr(FastAPI, _HOOK_SENTINEL, False):
        return
    original_init: Callable[..., None] = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        if kwargs.get("title") == "Omnix Web Gateway" or (
            args and args[0] == "Omnix Web Gateway"
        ):
            register_rpg_world_routes(self)

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _HOOK_SENTINEL, True)
