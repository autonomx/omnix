from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .agent_plan_request import agent_plan_request_payload
from .hermes_sidecar_config import HermesSidecarConfig
from .service_bridge import service_bridge_payload

PlanTransport = Callable[[str, dict[str, Any], float], dict[str, Any]]


def _safe_error(status: str, objective: str = "") -> dict[str, Any]:
    return {
        "ok": False,
        "status": status,
        "sent": False,
        "request": agent_plan_request_payload(objective, {}),
        "review_required": True,
        "read_only": True,
        "executes": False,
    }


def plan_endpoint_payload(
    objective: str,
    context: dict[str, Any] | None = None,
    transport: PlanTransport | None = None,
    config: HermesSidecarConfig | None = None,
) -> dict[str, Any]:
    cleaned = objective.strip()
    if not cleaned:
        return _safe_error("invalid_request", "")
    if context is None:
        return _safe_error("invalid_request", cleaned)

    request = agent_plan_request_payload(cleaned, context)
    payload = service_bridge_payload(request, transport=transport, config=config)
    return {
        **payload,
        "request": request,
        "review_required": True,
        "read_only": True,
        "executes": False,
    }
