"""The call's floor between the person and its characters' talk (companion 6.3, 6.5), for chat's ``CHAT_FLOOR``.

The person speaking ends a scene turn in progress: its lease is finished under the authority's lock, so its commit
gets ``initiative_lease_inactive``. What that turn streamed so far is read for the echo check before the person's
message is saved, because finishing the lease ends what the read can see.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from app.platform.companion_activity.contracts import default_companion_initiative_authority

logger = logging.getLogger(__name__)

_SCENE_OWNER = "scene"


class SceneFloor:
    """Backed by the initiative authority; chat calls it best effort, and the lease's TTL and the commit's anchor
    check hold without it."""

    def __init__(self, authority_factory: Callable[[], Any] = default_companion_initiative_authority) -> None:
        self._authority_factory = authority_factory

    def person_took_floor(self, session_id: str, user_message_id: str) -> None:
        finished = self._authority_factory().finish_owner(
            session_id=session_id, owner=_SCENE_OWNER, finished_at=datetime.now(timezone.utc), delivered=False)
        if finished:
            logger.info("scene turn ended by the person's message %s in %s", user_message_id, session_id)

    def active_scene_line_text(self, session_id: str) -> str | None:
        attempt = self._authority_factory().active_scene_attempt(session_id, now=datetime.now(timezone.utc))
        return None if attempt is None else attempt.streamed_text or None


__all__ = ["SceneFloor", "SceneMemoryCharacters"]


class SceneMemoryCharacters:
    """Assistant memory's ``SCENE_MEMORY_CHARACTERS``: the Live Chat cap, and the person's characters by name."""

    def per_character(self, session_id: str) -> int:
        from app.platform.characters.contracts import default_live_conversation_profile_store

        return int(default_live_conversation_profile_store().get(session_id).effective.scene_memory_per_character)

    def character_named(self, name: str) -> str | None:
        from app.platform.characters.contracts import default_character_service

        wanted = " ".join(str(name or "").split()).casefold()
        if not wanted:
            return None
        found = [character.id for character in default_character_service().list().characters
                 if " ".join(character.display_name.split()).casefold() == wanted]
        return found[0] if len(found) == 1 else None
