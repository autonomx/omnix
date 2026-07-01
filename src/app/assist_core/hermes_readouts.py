from __future__ import annotations

from typing import Any

READOUT_NAMES = {
    "get_house_status",
    "get_hermes_status",
    "get_hermes_diagnostics_schema",
    "get_hermes_rpg_plan_summary",
}


def readout_payload(name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    clean = str(name or "").strip()
    _ = args or {}
    if clean == "get_house_status":
        from .house_state import load_house_state

        return {"ok": True, "name": clean, "payload": {"state": load_house_state()}}
    if clean == "get_hermes_status":
        from .hermes_status import hermes_status_payload

        return {"ok": True, "name": clean, "payload": hermes_status_payload()}
    if clean == "get_hermes_diagnostics_schema":
        from .hermes_diagnostics import hermes_diagnostics_schema

        return {"ok": True, "name": clean, "payload": hermes_diagnostics_schema()}
    if clean == "get_hermes_rpg_plan_summary":
        from .hermes_rpg_plan_summary import hermes_rpg_plan_summary_payload

        return {"ok": True, "name": clean, "payload": hermes_rpg_plan_summary_payload()}
    return {"ok": False, "name": clean, "error": "unknown_readout"}
