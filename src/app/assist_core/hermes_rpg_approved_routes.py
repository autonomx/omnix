from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body

from .hermes_rpg_approved_flow import hermes_rpg_approved_flow
from .hermes_rpg_canonical_submitter import hermes_rpg_canonical_submitter
from .hermes_rpg_submit_bridge import RpgSubmitter

hermes_rpg_approved_bp = APIRouter()


def hermes_rpg_approved_flow_enabled(payload: dict[str, Any]) -> bool:
    return payload.get("enabled") is True


def hermes_rpg_approved_flow_route_payload(
    payload: dict[str, Any] | None,
    *,
    submitter: RpgSubmitter | None = None,
) -> dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    if not hermes_rpg_approved_flow_enabled(data):
        return {
            "ok": False,
            "source": "hermes_rpg_approved_flow_route",
            "error": "hermes_rpg_approved_flow_disabled",
            "enabled": False,
            "state_changed": False,
        }

    user_step = data.get("user_step") if isinstance(data.get("user_step"), dict) else {}
    replay_entry = data.get("replay_entry") if isinstance(data.get("replay_entry"), dict) else {}
    context = data.get("context") if isinstance(data.get("context"), dict) else {}
    flow = hermes_rpg_approved_flow(
        user_step,
        replay_entry,
        context,
        submitter or hermes_rpg_canonical_submitter,
    )
    return {
        "ok": flow.get("ok") is True,
        "source": "hermes_rpg_approved_flow_route",
        "enabled": True,
        "flow": flow,
        "state_changed": flow.get("state_changed") is True,
    }


@hermes_rpg_approved_bp.post("/api/hermes/rpg/approved-flow")
def hermes_rpg_approved_flow_route(payload: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:
    return hermes_rpg_approved_flow_route_payload(payload)
