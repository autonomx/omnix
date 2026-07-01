from __future__ import annotations

from app.assist_core.hermes_sidecar_config import HermesSidecarConfig
from app.assist_core.hermes_sidecar_health import hermes_sidecar_health_payload


def test_sidecar_status_values() -> None:
    config = HermesSidecarConfig(True, "x", 5)

    assert hermes_sidecar_health_payload(config)["status"] == "unavailable"
    assert hermes_sidecar_health_payload(config, probe_ok=True)["ok"] is True
    assert hermes_sidecar_health_payload(config, probe_ok=False)["ok"] is False
