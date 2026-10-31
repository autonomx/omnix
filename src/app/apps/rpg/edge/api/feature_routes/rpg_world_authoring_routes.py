"""World-authoring projections, metadata, and safe topic routes."""
from __future__ import annotations
from fastapi import APIRouter

from typing import Any, Mapping

from fastapi import HTTPException, Request

from app.apps.rpg.genesis.worlds.authoring_service import (
    read_authoring_manifest,
    read_authoring_section,
    update_world_metadata,
)
from app.apps.rpg.genesis.worlds.entity_authoring import (
    add_world_entity,
    read_world_entity,
    regenerate_world_entity,
    update_world_entity,
)
from app.apps.rpg.genesis.worlds.play_section_authoring import (
    PlaySectionsInvalidError,
    draft_play_sections_from_lore,
    publish_play_sections,
    read_play_sections,
    save_play_sections,
)
from app.apps.rpg.genesis.worlds.topic_authoring import (
    read_world_topic,
    restore_world_topic,
    update_world_topic,
)

from pydantic import BaseModel as _TypedRequestBaseModel, ConfigDict as _TypedRequestConfigDict, Field as _typed_field
from typing import Any as _TypedRequestAny
from app.apps.rpg.edge.api.web_contracts import (
    documented,
    RpgAuthoringEntityMutationResponse,
    RpgAuthoringManifestResponse,
    RpgPlaySectionsDraftResponse,
    RpgPlaySectionsResponse,
)
from app.apps.rpg.edge.api.route_contracts import (
    RpgAuthoringEntityDetailResponse,
    RpgAuthoringSectionPage,
    RpgAuthoringTopicDetailResponse,
    RpgAuthoringTopicMutationResponse,
    RpgWorldResponse,
)

class _TypedRequestModel(_TypedRequestBaseModel):
    model_config = _TypedRequestConfigDict(extra="allow", populate_by_name=True)

class RpgUpdateWorldMetadataRequestBody(_TypedRequestModel):
    expected_draft_revision: int = _typed_field(ge=1)
    title: str | None = None
    description: str | None = None
    genre: str | None = None
    tone: str | None = None
    seed: int | None = None
    metadata: dict[str, Any] | None = None

class RpgUpdateWorldTopicRequestBody(_TypedRequestModel):
    approved: bool | None = False
    content: _TypedRequestAny = None
    generation_lock: bool | None = True

class RpgUpdateWorldEntityRequestBody(_TypedRequestModel):
    changes: _TypedRequestAny = None

class RpgAddWorldEntityRequestBody(_TypedRequestModel):
    entity: _TypedRequestAny = None
    collection: _TypedRequestAny = None  # the topic's list it goes in ("characters"); else the one the topic keeps


class RpgRegenerateWorldEntityRequestBody(_TypedRequestModel):
    directives: _TypedRequestAny = None

class RpgRestoreWorldTopicRequestBody(_TypedRequestModel):
    history_sequence: _TypedRequestAny = None

class RpgSavePlaySectionsRequestBody(_TypedRequestBaseModel):
    model_config = _TypedRequestConfigDict(extra="forbid")
    expected_content_hash: str = _typed_field(min_length=1)
    # Checked by the service, which names each error (play_section_invalid:<where>:<why>).
    document: dict[str, Any]


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


def register_rpg_world_authoring_routes(router: APIRouter, state) -> None:
    if getattr(state, _ROUTE_SENTINEL, False):
        return
    setattr(state, _ROUTE_SENTINEL, True)

    @router.get(
        "/api/rpg/worlds/{world_id}/authoring-manifest",
        tags=["rpg-world"],
        responses=documented(RpgAuthoringManifestResponse),
    )
    def rpg_world_authoring_manifest(world_id: str) -> dict[str, Any]:
        try:
            return read_authoring_manifest(world_id)
        except Exception as exc:
            _raise_domain_error(exc)
            raise

    @router.get(
        "/api/rpg/worlds/{world_id}/authoring-sections/{section_id}",
        tags=["rpg-world"],
        responses=documented(RpgAuthoringSectionPage),
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

    @router.patch(
        "/api/rpg/worlds/{world_id}",
        tags=["rpg-world"],
        responses=documented(RpgWorldResponse),
    )
    def rpg_update_world_metadata(
        world_id: str,
        request: Request, request_body: RpgUpdateWorldMetadataRequestBody,
    ) -> dict[str, Any]:
        payload = dict(_body(request_body.model_dump(exclude_unset=True, by_alias=True)))
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

    @router.get(
        "/api/rpg/worlds/{world_id}/play-sections",
        tags=["rpg-world"],
        responses=documented(RpgPlaySectionsResponse),
    )
    def rpg_read_world_play_sections(world_id: str) -> dict[str, Any]:
        try:
            return read_play_sections(world_id)
        except Exception as exc:
            _raise_domain_error(exc)
            raise

    @router.put(
        "/api/rpg/worlds/{world_id}/play-sections",
        tags=["rpg-world"],
        responses=documented(RpgPlaySectionsResponse),
    )
    def rpg_save_world_play_sections(world_id: str, request_body: RpgSavePlaySectionsRequestBody) -> dict[str, Any]:
        try:
            return save_play_sections(
                world_id,
                expected_content_hash=request_body.expected_content_hash,
                document=request_body.document,
            )
        except PlaySectionsInvalidError as exc:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "error": "world_play_sections_invalid", "findings": list(exc.findings)},
            ) from exc
        except Exception as exc:
            _raise_domain_error(exc)
            raise

    @router.post(
        "/api/rpg/worlds/{world_id}/play-sections/publish",
        tags=["rpg-world"],
        responses=documented(RpgPlaySectionsResponse),
    )
    def rpg_publish_world_play_sections(world_id: str) -> dict[str, Any]:
        try:
            return publish_play_sections(world_id)
        except Exception as exc:
            _raise_domain_error(exc)
            raise

    @router.post(
        "/api/rpg/worlds/{world_id}/play-sections/draft-from-lore",
        tags=["rpg-world"],
        responses=documented(RpgPlaySectionsDraftResponse),
    )
    def rpg_draft_world_play_sections(world_id: str) -> dict[str, Any]:
        try:
            return draft_play_sections_from_lore(world_id)
        except Exception as exc:
            _raise_domain_error(exc)
            raise

    @router.get(
        "/api/rpg/worlds/{world_id}/topics/{topic_id}",
        tags=["rpg-world"],
        responses=documented(RpgAuthoringTopicDetailResponse),
    )
    def rpg_read_world_topic(world_id: str, topic_id: str) -> dict[str, Any]:
        try:
            return read_world_topic(world_id, topic_id)
        except Exception as exc:
            _raise_domain_error(exc)
            raise

    @router.patch(
        "/api/rpg/worlds/{world_id}/topics/{topic_id}",
        tags=["rpg-world"],
        responses=documented(RpgAuthoringTopicMutationResponse),
    )
    def rpg_update_world_topic(
        world_id: str,
        topic_id: str,
        request: Request, request_body: RpgUpdateWorldTopicRequestBody,
    ) -> dict[str, Any]:
        payload = dict(_body(request_body.model_dump(exclude_unset=True, by_alias=True)))
        revision, content_hash = _expected(payload)
        content = payload.get("content")
        if not isinstance(content, Mapping):
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "error": "topic_content_required"},
            )
        try:
            return update_world_topic(
                world_id,
                topic_id,
                expected_draft_revision=revision,
                expected_content_hash=content_hash,
                content=content,
                generation_lock=bool(payload.get("generation_lock", True)),
                approved=bool(payload.get("approved", False)),
            )
        except Exception as exc:
            _raise_domain_error(exc)
            raise

    @router.post(
        "/api/rpg/worlds/{world_id}/topics/{topic_id}/entities",
        tags=["rpg-world"],
        responses=documented(RpgAuthoringEntityMutationResponse),
    )
    def rpg_add_world_entity(
        world_id: str,
        topic_id: str,
        request: Request, request_body: RpgAddWorldEntityRequestBody,
    ) -> dict[str, Any]:
        """An author adds an entity to a topic (EV-6)."""
        payload = dict(_body(request_body.model_dump(exclude_unset=True, by_alias=True)))
        revision, content_hash = _expected(payload)
        entity = payload.get("entity")
        if not isinstance(entity, Mapping):
            raise HTTPException(status_code=422, detail={"ok": False, "error": "entity_required"})
        try:
            return add_world_entity(world_id, topic_id, expected_draft_revision=revision,
                                    expected_content_hash=content_hash, entity=entity,
                                    collection=str(payload.get("collection") or ""))
        except Exception as exc:
            _raise_domain_error(exc)
            raise

    @router.get(
        "/api/rpg/worlds/{world_id}/topics/{topic_id}/entities/{entity_id}",
        tags=["rpg-world"],
        responses=documented(RpgAuthoringEntityDetailResponse),
    )
    def rpg_read_world_entity(
        world_id: str,
        topic_id: str,
        entity_id: str,
    ) -> dict[str, Any]:
        try:
            return read_world_entity(world_id, topic_id, entity_id)
        except Exception as exc:
            _raise_domain_error(exc)
            raise

    @router.patch(
        "/api/rpg/worlds/{world_id}/topics/{topic_id}/entities/{entity_id}",
        tags=["rpg-world"],
        responses=documented(RpgAuthoringEntityMutationResponse),
    )
    def rpg_update_world_entity(
        world_id: str,
        topic_id: str,
        entity_id: str,
        request: Request, request_body: RpgUpdateWorldEntityRequestBody,
    ) -> dict[str, Any]:
        payload = dict(_body(request_body.model_dump(exclude_unset=True, by_alias=True)))
        revision, content_hash = _expected(payload)
        changes = payload.get("changes")
        if not isinstance(changes, Mapping):
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "error": "entity_changes_required"},
            )
        try:
            return update_world_entity(
                world_id,
                topic_id,
                entity_id,
                expected_draft_revision=revision,
                expected_content_hash=content_hash,
                changes=changes,
            )
        except Exception as exc:
            _raise_domain_error(exc)
            raise

    @router.post(
        "/api/rpg/worlds/{world_id}/topics/{topic_id}/entities/{entity_id}/regenerate",
        tags=["rpg-world"],
        responses=documented(RpgAuthoringEntityMutationResponse),
    )
    def rpg_regenerate_world_entity(
        world_id: str,
        topic_id: str,
        entity_id: str,
        request: Request, request_body: RpgRegenerateWorldEntityRequestBody,
    ) -> dict[str, Any]:
        payload = dict(_body(request_body.model_dump(exclude_unset=True, by_alias=True)))
        revision, content_hash = _expected(payload)
        directives = payload.get("directives")
        if directives is not None and not isinstance(directives, Mapping):
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "error": "entity_directives_must_be_object"},
            )
        try:
            return regenerate_world_entity(
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

    @router.post(
        "/api/rpg/worlds/{world_id}/topics/{topic_id}/restore",
        tags=["rpg-world"],
        responses=documented(RpgAuthoringTopicMutationResponse),
    )
    def rpg_restore_world_topic(
        world_id: str,
        topic_id: str,
        request: Request, request_body: RpgRestoreWorldTopicRequestBody,
    ) -> dict[str, Any]:
        payload = dict(_body(request_body.model_dump(exclude_unset=True, by_alias=True)))
        revision, content_hash = _expected(payload)
        history_sequence = int(payload.get("history_sequence") or 0)
        if history_sequence < 1:
            raise HTTPException(
                status_code=422,
                detail={"ok": False, "error": "history_sequence_required"},
            )
        try:
            return restore_world_topic(
                world_id,
                topic_id,
                history_sequence=history_sequence,
                expected_draft_revision=revision,
                expected_content_hash=content_hash,
            )
        except Exception as exc:
            _raise_domain_error(exc)
            raise
