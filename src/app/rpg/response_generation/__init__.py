"""Canonical RPG response-generation contracts and policies.

The package is introduced incrementally by the response-generation roadmap.
Simulation remains authoritative; modules in this package operate on presentation
contracts, evidence, proposals, and validated delivery only.
"""

from .baseline import (
    BaselineMetrics,
    BaselineObservation,
    BaselineScenario,
    evaluate_baseline,
    load_baseline_scenarios,
    validate_scenarios,
)

__all__ = [
    "BaselineMetrics",
    "BaselineObservation",
    "BaselineScenario",
    "evaluate_baseline",
    "load_baseline_scenarios",
    "validate_scenarios",
]
