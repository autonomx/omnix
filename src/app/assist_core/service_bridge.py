from __future__ import annotations

from typing import Any

from .hermes_sidecar_config import HermesSidecarConfig
from .service_plan_client import service_plan_payload


def service_bridge_payload(
    request: dict[str, Any],
    transport=None,
    config: HermesSidecarConfig | None = None,
) -> dict[str, Any]:
    result = service_plan_payload(request, transport=transport, config=config)
    return {
        **result,
        "source": "service_bridge",
        "read_only": True,
        "executes": False,
    }
