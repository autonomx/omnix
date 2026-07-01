from __future__ import annotations

from app.assist_core.hermes_sidecar_config import HermesSidecarConfig
from app.assist_core.service_bridge import service_bridge_payload


def test_service_bridge_is_read_only() -> None:
    config = HermesSidecarConfig(False, "http://local", 5)
    payload = service_bridge_payload({}, config=config)

    assert payload["read_only"] is True
    assert payload["executes"] is False
    assert payload["sent"] is False
