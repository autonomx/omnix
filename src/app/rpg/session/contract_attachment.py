"""Contract attachment helpers."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

_CONTRACT_KEYS = (
    "intent_result",
    "world_assessment",
    "response_authority",
    "turn_plan",
    "reasoning_trace",
)


def attach_contracts_to_result(result: dict[str, Any], contracts: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with contract dictionaries attached in standard locations."""

    copied = deepcopy(_d(result))
    clean_contracts = {key: deepcopy(_d(contracts.get(key))) for key in _CONTRACT_KEYS}
    for key, value in clean_contracts.items():
        copied[key] = deepcopy(value)
    for container_key in ("result", "resolved_result", "grounding_validation"):
        container = _d(copied.get(container_key))
        if container:
            for key, value in clean_contracts.items():
                container[key] = deepcopy(value)
            copied[container_key] = container
    return copied


def contract_attachment_ready() -> bool:
    return True


def _d(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}
