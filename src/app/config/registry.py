"""Machine-readable environment variable registry."""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class EnvironmentVariable:
    name: str
    type: str
    default: str | None
    feature: str
    description: str


VARIABLES: tuple[EnvironmentVariable, ...] = (
    EnvironmentVariable("OMNIX_BIND_HOST", "host", "127.0.0.1", "kernel", "Gateway bind host."),
    EnvironmentVariable("OMNIX_GATEWAY_PORT", "integer", "8001", "kernel", "Gateway port."),
    EnvironmentVariable("OMNIX_DATABASE_URL", "url", None, "kernel", "Runtime PostgreSQL role URL."),
    EnvironmentVariable("OMNIX_MIGRATION_DATABASE_URL", "url", None, "kernel", "DDL/migration PostgreSQL role URL."),
    EnvironmentVariable("OMNIX_REQUIRE_ROLE_SEPARATION", "boolean", "false", "kernel", "Require distinct runtime and migration roles."),
    EnvironmentVariable("OMNIX_ENV", "string", "development", "kernel", "Deployment environment."),
    EnvironmentVariable("OMNIX_SOFTWARE_REVISION", "string", "unversioned", "kernel", "Build/software revision."),
    EnvironmentVariable("OMNIX_FEATURES", "list", "all", "kernel", "Enabled optional feature ids."),
    EnvironmentVariable("OMNIX_FEATURES_DISABLED", "list", "", "kernel", "Disabled optional feature ids."),
    EnvironmentVariable("OMNIX_GATEWAY_BACKGROUND_ROLE", "enum", "worker", "kernel", "Gateway process role."),
    EnvironmentVariable("OMNIX_GATEWAY_REQUIRED_WORKERS", "list", "", "kernel", "Required worker ids."),
    EnvironmentVariable("OMNIX_TTS_URL", "url", None, "voice", "TTS worker endpoint."),
    EnvironmentVariable("OMNIX_STT_URL", "url", None, "voice", "STT worker endpoint."),
    EnvironmentVariable("OMNIX_IMAGE_URL", "url", None, "image", "Image worker endpoint."),
)


def registry_payload() -> list[dict[str, str | None]]:
    return [asdict(item) for item in VARIABLES]


def render_configuration_markdown() -> str:
    lines = [
        "# Omnix configuration",
        "",
        "Generated from app.config.registry. Values are intentionally never emitted.",
        "",
        "| Variable | Type | Default | Owner | Description |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in VARIABLES:
        default = item.default if item.default not in (None, "") else "—"
        lines.append(
            f"| {item.name} | {item.type} | {default} | {item.feature} | {item.description} |"
        )
    return "\n".join(lines) + "\n"
