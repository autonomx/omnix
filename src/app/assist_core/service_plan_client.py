from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .hermes_sidecar_config import HermesSidecarConfig, hermes_sidecar_config

ServiceTransport = Callable[[str, dict[str, Any], float], dict[str, Any]]


def service_plan_payload(
    request: dict[str, Any],
    transport: ServiceTransport | None = None,
    config: HermesSidecarConfig | None = None,
) -> dict[str, Any]:
    selected = config or hermes_sidecar_config()
    if not selected.enabled:
        return {"ok": False, "status": "disabled", "sent": False}
    if transport is None:
        return {"ok": False, "status": "transport_missing", "sent": False}
    response = transport(f"{selected.base_url}/agent/plan", request, selected.timeout_seconds)
    return {"ok": bool(response.get("ok")), "status": response.get("status", "ok"), "sent": True, "response": response}
