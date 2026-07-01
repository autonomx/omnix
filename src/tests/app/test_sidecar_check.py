from __future__ import annotations

from app.assist_core.hermes_sidecar_config import HermesSidecarConfig
from app.assist_core.hermes_sidecar_health import hermes_sidecar_health_payload


def test_sidecar_check_states() -> None:
    config = HermesSidecarConfig(True, "x", 5)

    assert hermes_sidecar_health_payload(config, probe_status="timeout")["status"] == "timeout"
    assert hermes_sidecar_health_payload(config, probe_status="unreachable")["status"] == "unreachable"
    assert hermes_sidecar_health_payload(config, probe_ok=True)["status"] == "healthy"
