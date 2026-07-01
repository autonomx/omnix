from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class HermesSidecarConfig:
    enabled: bool
    base_url: str
    timeout_seconds: float


def hermes_sidecar_config() -> HermesSidecarConfig:
    return HermesSidecarConfig(
        enabled=os.getenv("OMNIX_HERMES_SIDECAR_ENABLED", "false").lower() == "true",
        base_url=os.getenv("OMNIX_HERMES_SIDECAR_URL", "http://127.0.0.1:8765").rstrip("/"),
        timeout_seconds=float(os.getenv("OMNIX_HERMES_SIDECAR_TIMEOUT_SECONDS", "5")),
    )
