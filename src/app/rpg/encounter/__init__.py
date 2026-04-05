"""Phase 8.2 — Encounter Package.

Stable public export surface for the encounter system.
"""

from .encounter_state import ensure_encounter_state
from .encounter_builder import build_encounter_from_scene
from .encounter_resolver import EncounterResolver
from .encounter_actions import build_player_actions

# Also re-export existing modules for backward compatibility
from .controller import EncounterController
from .models import (
    SUPPORTED_ENCOUNTER_MODES,
    SUPPORTED_ENCOUNTER_STATUSES,
    EncounterChoiceContext,
    EncounterObjective,
    EncounterParticipant,
    EncounterResolution,
    EncounterSnapshot,
    EncounterState,
)
from .presenter import EncounterPresenter
from .resolver import EncounterResolver as ExistingEncounterResolver

__all__ = [
    # New dict-based encounter system (Phase 8.2)
    "ensure_encounter_state",
    "build_encounter_from_scene",
    "EncounterResolver",
    "build_player_actions",
    # Existing object-based encounter system
    "EncounterController",
    "EncounterPresenter",
    "ExistingEncounterResolver",
    "EncounterState",
    "EncounterParticipant",
    "EncounterObjective",
    "EncounterChoiceContext",
    "EncounterResolution",
    "EncounterSnapshot",
    "SUPPORTED_ENCOUNTER_MODES",
    "SUPPORTED_ENCOUNTER_STATUSES",
]