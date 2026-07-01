from __future__ import annotations

from app.assist_core.hermes_sidecar_config import HermesSidecarConfig
from app.assist_core.service_plan_client import service_plan_payload


def test_service_plan_payload_disabled() -> None:
    config = HermesSidecarConfig(False, "http://local", 5)

    assert service_plan_payload({}, config=config)["sent"] is False


def test_service_plan_payload_missing_transport() -> None:
    config = HermesSidecarConfig(True, "http://local", 5)

    assert service_plan_payload({}, config=config)["status"] == "transport_missing"
