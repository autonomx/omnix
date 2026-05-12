# Story module for RPG system.
#
# Keep this package import light. Tests and runtime modules often import
# app.rpg.story.story_arc_lifecycle directly; __init__ should not eagerly import
# heavier director/plot modules that may have optional dependencies.

from __future__ import annotations

from typing import Any

from .story_arc_lifecycle import (
    ArcFailureRule,
    ArcResolutionRule,
    ArcRuntimeState,
    apply_story_arc_lifecycle,
)
from .tavern_story_arc_rules import tavern_story_arc_rules

_LEGACY_EXPORTS = {
    "StoryDirector": ".director",
    "DirectorAgent": ".director_agent",
    "DirectorOutput": ".director_agent",
    "DirectorOutputOriginal": ".director_types",
    "DynamicQuestGenerator": ".dynamic_quest_generator",
    "PlotEngine": ".plot_engine",
    "Quest": ".plot_engine",
    "QuestManager": ".plot_engine",
    "Setup": ".plot_engine",
    "SetupTracker": ".plot_engine",
}


def __getattr__(name: str) -> Any:
    if name not in _LEGACY_EXPORTS:
        raise AttributeError(name)

    import importlib

    module = importlib.import_module(_LEGACY_EXPORTS[name], package=__name__)

    if name == "DirectorOutputOriginal":
        return getattr(module, "DirectorOutput")

    return getattr(module, name)


__all__ = [
    "ArcFailureRule",
    "ArcResolutionRule",
    "ArcRuntimeState",
    "apply_story_arc_lifecycle",
    "tavern_story_arc_rules",
    "StoryDirector",
    "DirectorAgent",
    "DirectorOutput",
    "DirectorOutputOriginal",
    "PlotEngine",
    "Quest",
    "QuestManager",
    "Setup",
    "SetupTracker",
    "DynamicQuestGenerator",
]