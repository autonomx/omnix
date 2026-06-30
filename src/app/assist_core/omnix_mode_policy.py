from __future__ import annotations

from typing import Literal, TypedDict

from .omnix_mode_router import OmnixMode, list_omnix_mode_routes, omnix_mode_route

ModeCapability = Literal["observe", "suggest", "critique", "plan", "request_execution"]


class OmnixModePolicy(TypedDict):
    mode: OmnixMode
    hermes_capabilities: list[ModeCapability]
    requires_review: bool
    owner: str
    notes: list[str]


MODE_CAPABILITIES: dict[OmnixMode, list[ModeCapability]] = {
    "normal_chat": [],
    "live_chat": ["observe"],
    "agent_mode": ["observe", "plan", "request_execution"],
    "house_ai": ["observe", "plan", "request_execution"],
    "podcast": ["observe", "critique", "plan"],
    "rpg": ["observe", "suggest", "critique"],
}


def omnix_mode_policy(mode: str) -> OmnixModePolicy:
    route = omnix_mode_route(mode)
    capabilities = MODE_CAPABILITIES[route["mode"]]
    notes = [
        f"Execution owner: {route['execution_owner']}",
        f"Hermes role: {route['hermes_role']}",
    ]
    if route["requires_approval"]:
        notes.append("Review is required before any owned system action is applied.")
    else:
        notes.append("No extra review is required for readout-only or suggestion-only use.")
    return {
        "mode": route["mode"],
        "hermes_capabilities": list(capabilities),
        "requires_review": route["requires_approval"],
        "owner": route["execution_owner"],
        "notes": notes,
    }


def list_omnix_mode_policies() -> list[OmnixModePolicy]:
    return [omnix_mode_policy(route["mode"]) for route in list_omnix_mode_routes()]


def omnix_mode_policy_payload(mode: str | None = None) -> dict[str, object]:
    if mode:
        try:
            return {"ok": True, "policy": omnix_mode_policy(mode)}
        except KeyError:
            return {"ok": False, "error": "unknown_mode", "mode": mode}
    return {"ok": True, "policies": list_omnix_mode_policies()}
