from __future__ import annotations

from app.assist_core.sidecar_status_endpoint import sidecar_status_endpoint_payload


def test_status_payload_source() -> None:
    payload = sidecar_status_endpoint_payload()

    assert payload["source"] == "sidecar_status_endpoint"
