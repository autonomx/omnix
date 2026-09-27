"""Validated deployment policy, independent of providers and the web framework."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
import os
from urllib.parse import urlsplit


class GatewayRole(str, Enum):
    WORKER = "worker"
    API = "api"


def _url(value: str, *, origin: bool = False) -> str:
    try:
        parsed = urlsplit(value)
        valid = (
            parsed.scheme in {"http", "https"}
            and bool(parsed.hostname)
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment
            and not any(char.isspace() for char in value)
            and (parsed.port is None or 1 <= parsed.port <= 65535)
            and (not origin or parsed.path in {"", "/"})
        )
    except ValueError:
        valid = False
    if not valid:
        # Never echo an invalid URL: it may contain credentials.
        raise ValueError("Service URLs must be absolute HTTP(S) URLs without credentials, query or fragment")
    host = parsed.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    port = parsed.port
    suffix = f":{port}" if port and (parsed.scheme, port) not in {("http", 80), ("https", 443)} else ""
    return f"{parsed.scheme}://{host}{suffix}{parsed.path.rstrip('/')}"


@dataclass(frozen=True, slots=True)
class ServiceEndpoint:
    url: str
    required: bool = False

    def __post_init__(self):
        object.__setattr__(self, "url", _url(self.url))


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    gateway_role: GatewayRole = GatewayRole.WORKER
    tts: ServiceEndpoint | None = None
    stt: ServiceEndpoint | None = None
    image: ServiceEndpoint | None = None
    use_remote_tts: bool = False
    api_replica_origins: tuple[str, ...] = ()
    required_workers: tuple[str, ...] = ()
    build_revision: str = "unversioned"
    worker_environment: tuple[tuple[str, str], ...] = ()
    enabled_features: tuple[str, ...] = ("all",)
    disabled_features: tuple[str, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "gateway_role", GatewayRole(self.gateway_role))
        origins = tuple(_url(value, origin=True) for value in self.api_replica_origins)
        if len(set(origins)) != len(origins):
            raise ValueError("Duplicate API replica origins")
        if len(origins) > 8:
            raise ValueError("At most eight API replica origins are supported")
        object.__setattr__(self, "api_replica_origins", origins)
        object.__setattr__(self, "required_workers", tuple(sorted(set(self.required_workers))))
        enabled = tuple(dict.fromkeys(value.strip() for value in self.enabled_features if value.strip()))
        disabled = tuple(dict.fromkeys(value.strip() for value in self.disabled_features if value.strip()))
        object.__setattr__(self, "enabled_features", enabled or ("all",))
        object.__setattr__(self, "disabled_features", disabled)
        workers = tuple((key, _url(value) if key.endswith('_URL') and value else value)
                        for key, value in self.worker_environment)
        object.__setattr__(self, 'worker_environment', workers)
        if self.gateway_role is GatewayRole.API and self.tts is not None:
            object.__setattr__(self, "use_remote_tts", True)
        if self.use_remote_tts and self.tts is None:
            raise ValueError("Gateway HTTP TTS requires OMNIX_TTS_URL")

    @property
    def owns_background_runtime(self) -> bool:
        return self.gateway_role is GatewayRole.WORKER

    @property
    def allow_local_tts(self) -> bool:
        return self.owns_background_runtime and not self.use_remote_tts

    @classmethod
    def from_environment(cls, env: Mapping[str, str] | None = None) -> RuntimeConfig:
        env = os.environ if env is None else env

        def flag(name: str, default: bool) -> bool:
            value = env.get(name)
            if value is None:
                return default
            value = value.strip().lower()
            if value in {"1", "true", "yes", "on"}:
                return True
            if value in {"0", "false", "no", "off"}:
                return False
            raise ValueError(f"{name} must be a boolean")

        role = GatewayRole(env.get("OMNIX_GATEWAY_BACKGROUND_ROLE", "worker").strip())
        owns = role is GatewayRole.WORKER
        if flag("OMNIX_GATEWAY_OWNS_BACKGROUND_RUNTIME", owns) != owns:
            raise ValueError("Explicit background ownership contradicts gateway role")
        required = tuple(value.strip() for value in env.get("OMNIX_GATEWAY_REQUIRED_WORKERS", "").split(",") if value.strip())

        def endpoint(name: str):
            value = env.get(f"OMNIX_{name.upper()}_URL", "").strip()
            return ServiceEndpoint(value, name in required) if value else None

        tts = endpoint("tts")
        remote = flag("OMNIX_GATEWAY_TTS_HTTP", False) or (not owns and tts is not None)
        local = owns and not remote
        if flag("OMNIX_GATEWAY_ALLOW_LOCAL_TTS", local) != local:
            raise ValueError("Explicit local TTS policy contradicts gateway topology")
        return cls(
            gateway_role=role, tts=tts, stt=endpoint("stt"), image=endpoint("image"),
            use_remote_tts=remote,
            api_replica_origins=tuple(value.strip() for value in env.get("OMNIX_GATEWAY_API_ORIGINS", "").split(",") if value.strip()),
            required_workers=required,
            build_revision=env.get("OMNIX_SOFTWARE_REVISION", "unversioned"),
            worker_environment=tuple(sorted((key, value) for key, value in env.items()
                                     if key.startswith('OMNIX_WORKER_') or key in {
                                         'OMNIX_GATEWAY_WORKERS', 'OMNIX_GATEWAY_MOCK_WORKERS', 'OMNIX_GATEWAY_MOCK_WORKERS_LIST'})),
            enabled_features=tuple(
                value.strip()
                for value in env.get("OMNIX_FEATURES", "all").split(",")
                if value.strip()
            ),
            disabled_features=tuple(
                value.strip()
                for value in env.get("OMNIX_FEATURES_DISABLED", "").split(",")
                if value.strip()
            ),
        )

    def worker_discovery_environment(self) -> dict[str, str]:
        env = dict(self.worker_environment)
        for name in ('tts', 'stt', 'image'):
            endpoint = getattr(self, name)
            if endpoint is not None:
                env[f'OMNIX_{name.upper()}_URL'] = endpoint.url
        return env


_process_config: RuntimeConfig | None = None


def install_runtime_config(config: RuntimeConfig) -> None:
    """Bind policy before production imports; a serving process cannot change role."""
    global _process_config
    if _process_config is not None and _process_config != config:
        raise RuntimeError("Runtime configuration is already bound to this process")
    if _process_config is None:
        _process_config = config


def get_runtime_config() -> RuntimeConfig:
    # Provider-free tools/tests can use deployment defaults without binding a
    # serving process. Production always installs its immutable instance first.
    return _process_config if _process_config is not None else RuntimeConfig.from_environment()
