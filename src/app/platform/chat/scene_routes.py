"""A call's scene: who is on it, and adding or removing a guest (companion 5.1)."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.conversation.scene import MAX_SCENE_GUESTS

SCENE_PATH = "/api/chat/sessions/{session_id}/scene"


class SceneMemberView(BaseModel):
    character_id: str
    display_name: str
    role: Literal["host", "guest"]
    seat: int | None = None


class SceneView(BaseModel):
    """The chat's call members: the host, then the guests by seat. ``available`` says whether guests can join."""

    available: bool
    reason: Literal["ready", "scene_needs_character_chat", "scene_needs_postgresql"]
    max_guests: int = MAX_SCENE_GUESTS
    members: list[SceneMemberView] = Field(default_factory=list)


class AddSceneGuestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    character_id: str = Field(min_length=1, max_length=200)


def scene_view(session: Any, *, repository: Any = None, member: Callable[[str], Any] | None = None) -> SceneView:
    from .scene import resolve_member, scene_repository, scenes_available

    member = member or resolve_member
    if not scenes_available(session):
        return SceneView(available=False, reason="scene_needs_character_chat")
    repository = repository if repository is not None else scene_repository()
    if repository is None:
        return SceneView(available=False, reason="scene_needs_postgresql")
    members: list[SceneMemberView] = []
    host = member(session.character_id)
    if host is not None:
        members.append(SceneMemberView(character_id=host.character_id, display_name=host.display_name, role="host"))
    for seat in repository.guests(session.id):
        guest = member(seat.character_id)
        # A guest who was disabled or lost its name sits out: they are not in the call.
        if guest is not None and guest.character_id != session.character_id:
            members.append(SceneMemberView(character_id=guest.character_id, display_name=guest.display_name,
                                           role="guest", seat=seat.seat))
    return SceneView(available=True, reason="ready", members=members)


def register_scene_routes(router: APIRouter, *, chat_store_factory: Callable[[], Any]) -> None:
    """The scene is read and changed only through its own chat; code checks every guest."""

    def _session(session_id: str) -> Any:
        session = chat_store_factory().get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session_not_found")
        return session

    @router.get(SCENE_PATH, response_model=SceneView)
    async def get_chat_scene(session_id: str) -> SceneView:
        return await asyncio.to_thread(lambda: scene_view(_session(session_id)))

    @router.post(SCENE_PATH + "/guests", response_model=SceneView)
    async def add_chat_scene_guest(session_id: str, request: AddSceneGuestRequest) -> SceneView:
        from .scene import SceneError, add_guest

        def add() -> SceneView:
            session = _session(session_id)
            try:
                add_guest(session, request.character_id)
            except SceneError as exc:
                raise HTTPException(status_code=409, detail=exc.code) from exc
            except LookupError as exc:
                raise HTTPException(status_code=404, detail="session_not_found") from exc
            return scene_view(session)

        return await asyncio.to_thread(add)

    @router.delete(SCENE_PATH + "/guests/{character_id}", response_model=SceneView)
    async def remove_chat_scene_guest(session_id: str, character_id: str) -> SceneView:
        from .scene import remove_guest

        def remove() -> SceneView:
            session = _session(session_id)
            if not remove_guest(session, character_id):
                raise HTTPException(status_code=404, detail="guest_not_found")
            return scene_view(session)

        return await asyncio.to_thread(remove)


__all__ = ["AddSceneGuestRequest", "SCENE_PATH", "SceneMemberView", "SceneView", "register_scene_routes", "scene_view"]
