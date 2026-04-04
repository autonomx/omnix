"""Phase 8.2 — Encounter Package.

Stable public export surface for the encounter system.
"""

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
from .resolver import EncounterResolver

__all__ = [
    "EncounterController",
    "EncounterResolver",
    "EncounterPresenter",
    "EncounterState",
    "EncounterParticipant",
    "EncounterObjective",
    "EncounterChoiceContext",
    "EncounterResolution",
    "EncounterSnapshot",
    "SUPPORTED_ENCOUNTER_MODES",
    "SUPPORTED_ENCOUNTER_STATUSES",
]
