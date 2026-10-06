"""Phase 7.8 — Live Narrative Steering / Arc Control.

This package provides explicit arc state, live steering controls,
reveal timing control, pacing plans, tension steering, scene-type
biasing, and stateful director guidance.

Architectural rule: 7.8 is a **steering layer**, not a truth layer.
- Do NOT let arc state override coherence truth directly.
- Do NOT let the story director become an authority source.
- DO use arc state to bias selection, pacing, framing, and reveal timing.
- DO keep everything serializable and replay-safe.
"""

from .arc_registry import ArcRegistry
from .controller import ArcControlController
from .directive_adapter import ArcDirectiveAdapter
from .models import (
    NarrativeArc,
    PacingPlanState,
    RevealDirectiveState,
    SceneBiasState,
)
from .pacing_plan import PacingPlanController
from .presenters import ArcControlPresenter
from .reveal_scheduler import RevealScheduler
from .scene_bias import SceneBiasController

__all__ = [
    "NarrativeArc",
    "RevealDirectiveState",
    "PacingPlanState",
    "SceneBiasState",
    "ArcRegistry",
    "RevealScheduler",
    "PacingPlanController",
    "SceneBiasController",
    "ArcDirectiveAdapter",
    "ArcControlController",
    "ArcControlPresenter",
]
