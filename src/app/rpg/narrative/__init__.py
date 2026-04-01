"""Narrative module — Story arcs, narrative events, and narrative generation.

This module implements the narrative layer from the RPG design spec:
- NarrativeEvent: Structured event representation with importance scoring
- NarrativeDirector: Converts world events to narrative events
- SceneManager: Tracks active scenes and scene context
- NarrativeGenerator: Turns events into narrative prose
- StoryArc: Story arc management

Architecture:
    World Events → NarrativeDirector → NarrativeEvents → Focus Selection
                                              ↓
                                        SceneManager → Scene Context
                                              ↓
                                    NarrativeGenerator → Prose
"""

from .narrative_event import NarrativeEvent
from .narrative_director import NarrativeDirector
from .scene_manager import Scene, SceneManager
from .narrative_generator import NarrativeGenerator
from .story_arc import StoryArc, StoryArcManager

__all__ = [
    "NarrativeEvent",
    "NarrativeDirector",
    "Scene",
    "SceneManager",
    "NarrativeGenerator",
    "StoryArc",
    "StoryArcManager",
]