"""Gateway routes for reusable RPG worlds, releases, and scenarios."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Mapping

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import ValidationError

from app.rpg.worlds.authorship_audit import (
    audit_world_authorship,
    remediate_world_authorship,
)
from app.rpg.worlds.contracts import (
    CampaignWorldBinding,
    ScenarioProjectCreate,
    ScenarioRevisionDocument,
    WorldProjectCreate,
    WorldReleaseDocument,
    WorldRevisionDocument,
)
from app.rpg.worlds.legacy_bible_import import import_campaign_bible_as_world
from app.rpg.worlds.lifecycle_service import (
    archive_scenario_project,
    archive_world_project,
    restore_scenario_project,
    restore_world_project,
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
from app.rpg.worlds.topic_history import (
    list_world_topic_history,
    restore_world_topic_draft,
)

from .rpg_world_library_routes import register_rpg_world_library_routes

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


def _domain_error(exc: Exception) -> HTTPException:
    if isinstance(exc, KeyError):
        return HTTPException(
            status_code=404,
            detail={"ok": False, "error": str(exc).strip("'")},
        )
    return HTTPException(
        status_code=409,
        detail={"ok": False, "error": str(exc)},
    )


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
        "/api/rpg/worlds/{world_id}/archive",
        tags=["rpg-world"],
        include_in_schema=False,
    )
    def rpg_archive_world(world_id: str) -> dict[str, Any]:
        try:
            return archive_world_project(world_id)
        except (KeyError, ValueError) as exc:
            raise _domain_error(exc) from exc

    @app.post(
        "/api/rpg/worlds/{world_id}/restore",
        tags=["rpg-world"],
        include_in_schema=False,
    )
    def rpg_restore_world(world_id: str) -> dict[str, Any]:
        try:
            return restore_world_project(world_id)
        except (KeyError, ValueError) as exc:
            raise _domain_error(exc) from exc

    @app.get(
        "/api/rpg/worlds/{world_id}/authorship-audit",
        tags=["rpg-world"],
        include_in_schema=False,
    )
    def rpg_audit_world_authorship(world_id: str) -> dict[str, Any]:
        try:
            return audit_world_authorship(world_id)
        except (KeyError, ValueError) as exc:
            raise _domain_error(exc) from exc

    @app.post(
        "/api/rpg/worlds/{world_id}/authorship-audit/remediate",
        tags=["rpg-world"],
        include_in_schema=False,
    )
    async def rpg_remediate_world_authorship(
        world_id: str,
        request: Request,
    ) -> dict[str, Any]:
        payload = dict(_body(await request.json()))
        try:
            return remediate_world_authorship(
                world_id,
                queue_regeneration=bool(payload.get("queue_regeneration", True)),
            )
        except (KeyError, ValueError) as exc:
            raise _domain_error(exc) from exc

    @app.get(
        "/api/rpg/worlds/{world_id}/topic-history",
        tags=["rpg-world"],
        include_in_schema=False,
    )
    def rpg_world_topic_history(
        world_id: str,
        draft_revision: int | None = Query(default=None, ge=1),
        latest_per_topic: bool = Query(default=False),
    ) -> dict[str, Any]:
        try:
            return {
                "ok": True,
                "history": list_world_topic_history(
                    world_id,
                    draft_revision=draft_revision,
                    latest_per_topic=latest_per_topic,
                ),
            }
        except (KeyError, ValueError) as exc:
            raise _domain_error(exc) from exc

    @app.post(
        "/api/rpg/worlds/{world_id}/drafts/{source_draft_revision}/restore",
        tags=["rpg-world"],
        include_in_schema=False,
    )
    async def rpg_restore_world_topic_draft(
        world_id: str,
        source_draft_revision: int,
        request: Request,
    ) -> dict[str, Any]:
        payload = dict(_body(await request.json()))
        try:
            return restore_world_topic_draft(
                world_id,
                source_draft_revision=source_draft_revision,
                expected_current_draft_revision=int(
                    payload.get("expected_current_draft_revision") or 0
                ),
            )
        except (KeyError, ValueError) as exc:
            raise _domain_error(exc) from exc

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
        except (KeyError, ValueError) as exc:
            raise _domain_error(exc) from exc

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
        except (KeyError, ValueError) as exc:
            raise _domain_error(exc) from exc

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
        except (KeyError, ValueError) as exc:
            raise _domain_error(exc) from exc

    @app.post(
        "/api/rpg/scenarios/{scenario_id}/archive",
        tags=["rpg-world"],
        include_in_schema=False,
    )
    def rpg_archive_scenario(scenario_id: str) -> dict[str, Any]:
        try:
            return archive_scenario_project(scenario_id)
        except (KeyError, ValueError) as exc:
            raise _domain_error(exc) from exc

    @app.post(
        "/api/rpg/scenarios/{scenario_id}/restore",
        tags=["rpg-world"],
        include_in_schema=False,
    )
    def rpg_restore_scenario(scenario_id: str) -> dict[str, Any]:
        try:
            return restore_scenario_project(scenario_id)
        except (KeyError, ValueError) as exc:
            raise _domain_error(exc) from exc

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
        except (KeyError, ValueError) as exc:
            raise _domain_error(exc) from exc

    @app.post(
        "/api/rpg/campaigns/{campaign_id}/legacy-world-import",
        tags=["rpg-world"],
        include_in_schema=False,
    )
    async def rpg_import_legacy_campaign_bible(
        campaign_id: str,
        request: Request,
    ) -> dict[str, Any]:
        payload = dict(_body(await request.json()))
        try:
            return import_campaign_bible_as_world(
                campaign_id,
                world_id=str(payload.get("world_id") or "") or None,
                scenario_id=str(payload.get("scenario_id") or "") or None,
            )
        except (KeyError, ValueError) as exc:
            raise _domain_error(exc) from exc

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
        except (KeyError, ValueError) as exc:
            raise _domain_error(exc) from exc

    register_rpg_world_library_routes(app)


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
