from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .hermes_contract import HermesToolSpec


def hermes_catalog_specs() -> list[HermesToolSpec]:
    return [
        HermesToolSpec(
            name="get_house_status",
            description="Read mock house status.",
            risk="low",
            args_schema={},
        ),
        HermesToolSpec(
            name="get_hermes_status",
            description="Read Hermes status.",
            risk="low",
            args_schema={},
        ),
        HermesToolSpec(
            name="get_hermes_diagnostics_schema",
            description="Read diagnostics schema.",
            risk="low",
            args_schema={},
        ),
        HermesToolSpec(
            name="kasa_discover_devices",
            description="Discover supported TP-Link Kasa devices on the user's local network.",
            risk="low",
            args_schema={},
        ),
        HermesToolSpec(
            name="kasa_get_state",
            description="Read the current on/off state of a selected Kasa smart plug.",
            risk="low",
            args_schema={"target": "string alias, host, or device id; optional when exactly one device exists"},
        ),
        HermesToolSpec(
            name="kasa_turn_on",
            description="Propose turning on one selected Kasa smart plug. User confirmation is mandatory.",
            risk="medium",
            args_schema={"target": "string alias, host, or device id"},
        ),
        HermesToolSpec(
            name="kasa_turn_off",
            description="Propose turning off one selected Kasa smart plug. User confirmation is mandatory.",
            risk="medium",
            args_schema={"target": "string alias, host, or device id"},
        ),
    ]


def hermes_catalog_payload() -> dict[str, Any]:
    return {"tools": [asdict(item) for item in hermes_catalog_specs()]}
