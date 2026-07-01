from __future__ import annotations

from app.assist_core.hermes_sidecar_config import hermes_sidecar_config


def test_hermes_sidecar_config_defaults(monkeypatch) -> None:
    monkeypatch.delenv("OMNIX_HERMES_SIDECAR_ENABLED", raising=False)
    monkeypatch.delenv("OMNIX_HERMES_SIDECAR_URL", raising=False)
    monkeypatch.delenv("OMNIX_HERMES_SIDECAR_TIMEOUT_SECONDS", raising=False)

    config = hermes_sidecar_config()

    assert config.enabled is False
    assert config.base_url == "http://127.0.0.1:8765"
    assert config.timeout_seconds == 5
