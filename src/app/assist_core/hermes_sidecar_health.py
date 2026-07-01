from __future__ import annotations

from typing import Any

from .hermes_sidecar_config import HermesSidecarConfig, hermes_sidecar_config


def hermes_sidecar_health_payload(
    config: HermesSidecarConfig | None = None,
    probe_ok: bool | None = None,
) -> dict[str, Any]:
    selected = config or hermes_sidecar_config()
    if not selected.enabled:
        return {"ok": True, "enabled": False, "status": "disabled", "base_url": selected.base_url}
    if probe_ok is None:
        return {"ok": False, "enabled": True, "status": "unavailable", "base_url": selected.base_url}
    return {"ok": probe_ok, "enabled": True, "status": "healthy" if probe_ok else "error", "base_url": selected.base_url}
