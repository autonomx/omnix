"""Compatibility aliases for the first world-resolution path.

Interpretive adjudication is the legacy/internal name for the initial
non-mutating world-resolution behavior. New code may import this module while
older reports and tests continue to use the interpretive names.
"""
from __future__ import annotations

from app.rpg.session.contract_attachment import add_contracts_to_interpretive_result
from app.rpg.session.interpretive_adjudication import (
    build_interpretive_adjudication_result,
    classify_interpretive_intent,
    interpretive_intent_family,
    should_use_interpretive_adjudication,
)

WORLD_RESOLUTION_SOURCE = "world_resolution_alias_v1"
LEGACY_WORLD_RESOLUTION_SOURCE = "world_grounded_interpretive_adjudication_v1"


def classify_world_resolution_intent(*args, **kwargs) -> str:
    return classify_interpretive_intent(*args, **kwargs)


def world_resolution_intent_family(intent: str) -> str:
    return interpretive_intent_family(intent)


def should_use_world_resolution(*args, **kwargs) -> bool:
    return should_use_interpretive_adjudication(*args, **kwargs)


def build_world_resolution_result(*args, **kwargs) -> dict:
    return add_contracts_to_interpretive_result(build_interpretive_adjudication_result(*args, **kwargs))
