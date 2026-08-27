from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.agent_runtime.capabilities import default_capability_registry

from .hermes_contract import HermesToolSpec


def hermes_catalog_specs() -> list[HermesToolSpec]:
    """Project Hermes planner tools from the canonical capability registry."""
    return [
        HermesToolSpec(
            name=capability.id,
            description=capability.description,
            risk=capability.risk,
            args_schema=dict(capability.input_schema),
        )
        for capability in default_capability_registry().hermes_projection()
    ]


def hermes_catalog_payload() -> dict[str, Any]:
    return {"tools": [asdict(item) for item in hermes_catalog_specs()]}
