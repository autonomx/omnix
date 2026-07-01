from __future__ import annotations

from typing import Any


SURFACES: tuple[dict[str, Any], ...] = (
    {"name": "status", "kind": "diagnostic", "route": "/api/hermes/status", "active": True},
    {"name": "test", "kind": "diagnostic", "route": "/api/hermes/test", "active": True, "dry_run_only": True},
    {"name": "adapter_preview", "kind": "preview", "route": "/api/hermes/adapter/preview", "active": True},
    {"name": "candidate_demo", "kind": "preview", "route": "/api/hermes/candidate/demo", "active": True},
    {"name": "rpg_context", "kind": "read_only", "route": "/api/hermes/rpg/context", "active": True},
    {"name": "rpg_suggestions", "kind": "preview", "route": "/api/hermes/rpg/suggestions", "active": True},
    {"name": "rpg_turn_readout", "kind": "read_only", "route": "/api/hermes/rpg/turn-readout", "active": True},
    {"name": "approve", "kind": "blocked", "route": "/api/hermes/approve", "active": False},
    {"name": "lookup", "kind": "dry_run", "route": "/api/hermes/lookup", "active": True},
)

MISSING_ACTIVE: tuple[str, ...] = (
    "planner_contract",
    "bounded_planner_context",
    "active_sidecar_request",
    "proposal_normalizer",
    "proposal_validator",
    "active_plan_route",
)


def hermes_completion_audit_payload() -> dict[str, Any]:
    active = [item for item in SURFACES if item["active"]]
    preview = [item for item in SURFACES if item["kind"] in {"preview", "read_only", "dry_run"}]
    return {
        "ok": True,
        "source": "hermes_completion_audit",
        "surface_count": len(SURFACES),
        "active_surface_count": len(active),
        "surfaces": list(SURFACES),
        "preview_or_read_only_count": len(preview),
        "missing_active": list(MISSING_ACTIVE),
        "complete_for_active_rpg_flow": False,
        "next_phase": "planner_contract",
    }
