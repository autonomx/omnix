from __future__ import annotations

from typing import Any

from .hermes_sidecar_health import hermes_sidecar_health_payload


def sidecar_status_endpoint_payload(probe_ok: bool | None = None) -> dict[str, Any]:
    payload = hermes_sidecar_health_payload(probe_ok=probe_ok)
    return {
        **payload,
        "source": "sidecar_status_endpoint",
        "read_only": True,
        "executes": False,
    }
