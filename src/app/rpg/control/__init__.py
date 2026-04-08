
"""Phase 7.2 — Gameplay Control Layer.

This module provides the control layer that sits on top of the coherence
and creator/GM layers. It is responsible for:

- generating deterministic, priority-ranked choice options
- applying pacing and framing biases to options
- producing stable, inspectable choice sets for the player/UX
"""

from __future__ import annotations

from .controller import GameplayControlController
from .framing import FramingEngine
from .models import (
    ChoiceOption,
    ChoiceSet,
    FramingState,
    OptionConstraint,
    PacingState,
)
from .option_engine import OptionEngine

__all__ = [
    "ChoiceOption",
    "ChoiceSet",
    "OptionConstraint",
    "PacingState",
    "FramingState",
    "OptionEngine",
    "PacingController",
    "GameplayControlController",
    "FramingEngine",
]
