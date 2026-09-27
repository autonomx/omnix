"""Startup configuration loader."""
from __future__ import annotations

from collections.abc import Mapping

from app.runtime.config import RuntimeConfig

from .env import env_bool, env_int, env_str, env_url, environment
from .models import DatabaseConfig, NetworkConfig, ObservabilityConfig, OmnixConfig


def load_config(env: Mapping[str, str] | None = None) -> OmnixConfig:
    source = environment() if env is None else env
    runtime = RuntimeConfig.from_environment(source)
    return OmnixConfig(
        runtime=runtime,
        network=NetworkConfig(
            bind_host=(env_str("OMNIX_BIND_HOST", "127.0.0.1", env=source) or "127.0.0.1").strip(),
            gateway_port=env_int("OMNIX_GATEWAY_PORT", 8001, minimum=1, maximum=65535, env=source),
        ),
        database=DatabaseConfig(
            url=env_url("OMNIX_DATABASE_URL", None, env=source),
            migration_url=env_url("OMNIX_MIGRATION_DATABASE_URL", None, env=source),
            require_role_separation=env_bool("OMNIX_REQUIRE_ROLE_SEPARATION", False, env=source),
        ),
        observability=ObservabilityConfig(
            environment=(env_str("OMNIX_ENV", "development", env=source) or "development").strip(),
            software_revision=(env_str("OMNIX_SOFTWARE_REVISION", "unversioned", env=source) or "unversioned").strip(),
        ),
    )
