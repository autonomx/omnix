from __future__ import annotations

from app.assist_core.hermes_sidecar_config import HermesSidecarConfig
from app.assist_core.hermes_sidecar_health import hermes_sidecar_health_payload


def test_sidecar_check_states() -> None:
    off = HermesSidecarConfig(False, "x", 5)
    on = HermesSidecarConfig(True, "x", 5)

    assert hermes_sidecar_health_payload(off)["status"] == "disabled"
    assert hermes_sidecar_health_payload(on)["status"] == "unavailable"
    assert hermes_sidecar_health_payload(on, probe_ok=False)["status"] == "error"
    assert hermes_sidecar_health_payload(on, probe_ok=True)["status"] == "healthy"
