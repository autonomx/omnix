"""Phase 8.3 — World Simulation Package.

Stable public export surface for the background world simulation system.
"""

from .controller import WorldSimController
from .models import (
    SUPPORTED_LOCATION_CONDITIONS,
    SUPPORTED_WORLD_EFFECT_TYPES,
    SUPPORTED_WORLD_SIM_STATUSES,
    FactionDriftState,
    LocationConditionState,
    NPCActivityState,
    RumorPropagationState,
    WorldEffect,
    WorldPressureState,
    WorldSimState,
    WorldSimTickResult,
)
from .presenter import WorldSimPresenter

__all__ = [
    "WorldSimController",
    "WorldSimPresenter",
    "WorldSimState",
    "WorldSimTickResult",
    "WorldEffect",
    "FactionDriftState",
    "RumorPropagationState",
    "LocationConditionState",
    "NPCActivityState",
    "WorldPressureState",
    "SUPPORTED_WORLD_EFFECT_TYPES",
    "SUPPORTED_LOCATION_CONDITIONS",
    "SUPPORTED_WORLD_SIM_STATUSES",
]
