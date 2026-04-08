"""Phase 8.1 — Structured Dialogue Layer.

Deterministic dialogue planning that turns existing state and action
results into better structured NPC response payloads.

This package does not replace execution.resolver, npc_agency,
coherence, social_state, or ux.  It is a presentation/planning
layer that sits on top of those existing systems.

Exports the public Phase 8.1 surface.
"""

from .acts import (
    SUPPORTED_DIALOGUE_ACTS,
    map_arc_pressure_to_reveal_level,
    map_npc_outcome_to_primary_act,
    map_relationship_to_stance,
    map_relationship_to_tone,
    map_scene_bias_to_dialogue_tags,
    normalize_dialogue_act,
)
from .context_builder import DialogueContextBuilder
from .core import DialogueCore
from .models import (
    DialogueActDecision,
    DialogueLogEntry,
    DialoguePresentation,
    DialogueResponsePlan,
    DialogueTurnContext,
)
from .presenter import DialoguePresenter
from .response_planner import DialogueResponsePlanner

__all__ = [
    # Models
    "DialogueTurnContext",
    "DialogueActDecision",
    "DialogueResponsePlan",
    "DialoguePresentation",
    "DialogueLogEntry",
    # Acts
    "SUPPORTED_DIALOGUE_ACTS",
    "map_npc_outcome_to_primary_act",
    "map_relationship_to_tone",
    "map_relationship_to_stance",
    "map_arc_pressure_to_reveal_level",
    "map_scene_bias_to_dialogue_tags",
    "normalize_dialogue_act",
    # Builders / Planners / Presenters
    "DialogueContextBuilder",
    "DialogueResponsePlanner",
    "DialoguePresenter",
    "DialogueCore",
]
