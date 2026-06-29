from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .hermes_contract import HermesToolSpec


def hermes_catalog_specs() -> list[HermesToolSpec]:
    return [
        HermesToolSpec(name="get_house_status", description="Read mock house status.", risk="low", args_schema={}),
        HermesToolSpec(name="get_hermes_status", description="Read Hermes status.", risk="low", args_schema={}),
        HermesToolSpec(name="get_hermes_diagnostics_schema", description="Read diagnostics schema.", risk="low", args_schema={}),
    ]


def hermes_catalog_payload() -> dict[str, Any]:
    return {"tools": [asdict(item) for item in hermes_catalog_specs()]}
