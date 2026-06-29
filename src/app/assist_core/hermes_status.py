from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from .hermes_client import HermesSidecarClient


def _flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _timeout() -> float:
    raw = os.environ.get("HERMES_TIMEOUT_SECONDS", "45")
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 45.0


@dataclass
class HermesRuntimeConfig:
    enabled: bool = False
    base_url: str = "http://127.0.0.1:8642"
    api_key_configured: bool = False
    timeout_seconds: float = 45.0


@dataclass
class HermesStatus:
    enabled: bool
    reachable: bool
    base_url: str
    health: dict[str, Any] = field(default_factory=dict)
    capabilities: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


def hermes_runtime_config() -> HermesRuntimeConfig:
    return HermesRuntimeConfig(
        enabled=_flag("HERMES_ENABLED", default=False),
        base_url=os.environ.get("HERMES_BASE_URL", "http://127.0.0.1:8642"),
        api_key_configured=bool(os.environ.get("HERMES_API_KEY")),
        timeout_seconds=_timeout(),
    )


def hermes_status() -> HermesStatus:
    config = hermes_runtime_config()
    if not config.enabled:
        return HermesStatus(enabled=False, reachable=False, base_url=config.base_url, error="hermes_disabled")
    client = HermesSidecarClient(
        base_url=config.base_url,
        api_key=os.environ.get("HERMES_API_KEY") or None,
        timeout=min(config.timeout_seconds, 8.0),
    )
    try:
        health = client.health()
        capabilities = client.capabilities()
        return HermesStatus(enabled=True, reachable=True, base_url=config.base_url, health=health, capabilities=capabilities)
    except Exception as exc:
        return HermesStatus(enabled=True, reachable=False, base_url=config.base_url, error=str(exc))


def hermes_status_payload() -> dict[str, Any]:
    status = hermes_status()
    return {
        "enabled": status.enabled,
        "reachable": status.reachable,
        "base_url": status.base_url,
        "health": status.health,
        "capabilities": status.capabilities,
        "error": status.error,
    }
