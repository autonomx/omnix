"""Composition feature for routes joining chat, characters, memory, and initiative."""
from __future__ import annotations

from fastapi import APIRouter

from app.platform.assistant_memory.contracts import SCENE_MEMORY_CHARACTERS
from app.platform.chat.contracts import CHAT_FLOOR
from app.runtime.features import FeatureContext, FeatureModule
from app.runtime.ports import ContributionSpec

from .routes import register_character_integration_routes


def _router(context: FeatureContext) -> APIRouter:
    router = APIRouter()
    register_character_integration_routes(
        router,
        chat_store_factory=lambda: context.services.chat,
        job_store_factory=lambda: context.services.jobs,
    )
    return router


def _floor(_context: FeatureContext):
    from .floor import SceneFloor

    return SceneFloor()


def _scene_memory_characters(_context: FeatureContext):
    from .floor import SceneMemoryCharacters

    return SceneMemoryCharacters()


FEATURE = FeatureModule(
    id="character-interactions",
    title="Character interactions",
    tier="app",
    depends_on=("characters", "chat", "assistant-memory", "companion-activity"),
    routers=(_router,),
    # The person speaking ends a character line in progress, and the echo check reads it (companion 6.3, 6.5).
    # ... and a prompt carries the newest few memories about each character present (companion 6.6).
    contributions=(ContributionSpec(CHAT_FLOOR, _floor),
                   ContributionSpec(SCENE_MEMORY_CHARACTERS, _scene_memory_characters)),
)
