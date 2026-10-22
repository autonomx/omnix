"""The environment every desktop child process runs with (desktop roadmap §4.2, the environment contract).

The Electron shell starts ``python -m app.desktop.supervise`` with a launch
config (folders and persisted ports) and the secrets it keeps in the OS
credential store. This module turns those into complete child environments,
built from scratch rather than inherited from the user's shell:

- only the system variables Python needs are kept (``SystemRoot``, ``TEMP``,
  proxies, ...); every inherited ``OMNIX_*``, ``PYTHON*`` and ``HF_*`` variable
  is dropped, so nothing from a developer's Omnix leaks in;
- the gateway and job worker get production defaults, invite-only accounts,
  the exact origin, the runtime database role, the persisted ports, the packs
  folder, and every writable path and credential under the desktop data folder
  (never ``%LOCALAPPDATA%\\Omnix``);
- each model service gets only what it needs: the service token, the runtime
  database role (device permits and settings, under row-level security), its
  persisted port, ``OMNIX_LAUNCHER_KILL_PORT=0`` (a busy port is an error, never
  a reason to kill another process), the offline Hugging Face cache and its
  model folder. It never gets the run token key or the owner database role.
"""
from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

SYSTEM_ALLOWLIST = (
    "SystemRoot", "SYSTEMROOT", "windir", "WINDIR", "SystemDrive", "SYSTEMDRIVE",
    "TEMP", "TMP", "USERPROFILE", "USERNAME", "LOCALAPPDATA", "APPDATA", "PROGRAMDATA", "ProgramData",
    "COMPUTERNAME", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "OS", "PATHEXT", "COMSPEC", "ComSpec",
    # NVML (nvidia-smi, the hardware probe) fails to initialise without the Program Files folders.
    "ProgramFiles", "PROGRAMFILES", "ProgramW6432", "PROGRAMW6432", "ProgramFiles(x86)", "CommonProgramFiles",
    "CommonProgramW6432",
    "HOME", "LANG", "LC_ALL", "TZ",
    "TMPDIR", "USER", "LOGNAME", "__CF_USER_TEXT_ENCODING",  # macOS
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy",
)
DROPPED_PREFIXES = ("OMNIX_", "PYTHON", "HF_", "HUGGINGFACE_", "OMNIXDESKTOP_")
# Secrets the shell passes the supervisor; read here and never copied as they are.
SECRET_VARIABLES = (
    "OMNIXDESKTOP_DB_OWNER_PASSWORD",
    "OMNIXDESKTOP_DB_APP_PASSWORD",
    "OMNIXDESKTOP_NOTIFY_SECRET",
    "OMNIXDESKTOP_GOOGLE_CLIENT_SECRET",
)
DB_OWNER = "omnix_desktop_owner"
DB_APP = "omnix_app"
DB_NAME = "omnix"
# Docker names of this install's agent sandbox (DT-3.5), apart from a developer Omnix's.
SANDBOX_IMAGE = "omnix-desktop-agent-sandbox:pi-0.85.1"
SANDBOX_NETWORK = "omnix-desktop-agent-sandbox"
SANDBOX_RELAY = "omnix-desktop-agent-relay"
MODEL_SERVICES = ("stt", "tts", "image")


@dataclass(frozen=True)
class LaunchConfig:
    """What the shell decides once and persists: folders and ports (a port is part of the origin; it never moves)."""

    install_root: Path
    data_dir: Path
    http_port: int
    pg_port: int
    metrics_port: int
    notify_port: int
    service_ports: Mapping[str, int] = field(default_factory=dict)
    postgres_bin: Path | None = None
    ffmpeg: Path | None = None
    packs_dir: Path | None = None
    google_client_id: str | None = None
    features: str | None = None

    @classmethod
    def load(cls, path: Path) -> LaunchConfig:
        raw = json.loads(path.read_text(encoding="utf-8"))
        ports = {str(name): int(port) for name, port in dict(raw.get("service_ports") or {}).items()}
        return cls(
            install_root=Path(raw["install_root"]),
            data_dir=Path(raw["data_dir"]),
            http_port=int(raw["http_port"]),
            pg_port=int(raw["pg_port"]),
            metrics_port=int(raw["metrics_port"]),
            notify_port=int(raw["notify_port"]),
            service_ports=ports,
            postgres_bin=Path(raw["postgres_bin"]) if raw.get("postgres_bin") else None,
            ffmpeg=Path(raw["ffmpeg"]) if raw.get("ffmpeg") else None,
            packs_dir=Path(raw["packs_dir"]) if raw.get("packs_dir") else None,
            google_client_id=(raw.get("google_client_id") or None),
            features=(raw.get("features") or None),
        )

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.http_port}"

    @property
    def web_dist(self) -> Path:
        return self.install_root / "web" / "dist"

    @property
    def packs(self) -> Path:
        return self.packs_dir or self.data_dir / "packs"

    @property
    def models_cache(self) -> Path:
        return self.packs / "models"

    def port(self, service: str) -> int:
        try:
            return int(self.service_ports[service])
        except KeyError:
            raise ValueError(f"the launch config has no port for the {service} service") from None


def _database_url(user: str, password: str, port: int) -> str:
    return f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}@127.0.0.1:{port}/{DB_NAME}"


def _system(source: Mapping[str, str], config: LaunchConfig) -> dict[str, str]:
    env = {name: source[name] for name in SYSTEM_ALLOWLIST if source.get(name)}
    system_root = source.get("SystemRoot") or source.get("SYSTEMROOT") or source.get("windir") or ""
    path_parts = []
    if config.postgres_bin is not None:
        # persistence/cli.py finds pg_dump and pg_restore on PATH.
        path_parts.append(str(config.postgres_bin))
    if config.ffmpeg is not None:
        path_parts.append(str(config.ffmpeg.parent))
    if system_root:
        path_parts += [str(Path(system_root) / "System32"), system_root]
    path_parts += [part for part in source.get("PATH", source.get("Path", "")).split(os.pathsep) if part]
    env["PATH"] = os.pathsep.join(dict.fromkeys(path_parts))
    return env


def _common(config: LaunchConfig) -> dict[str, str]:
    """What the gateway and the model services share."""
    data = config.data_dir
    secrets = data / "secrets"
    env = {
        "OMNIX_ENV": "production",
        "OMNIX_BIND_HOST": "127.0.0.1",
        "OMNIX_RESOURCES_DIR": str(data / "resources"),
        "OMNIX_MODELS_DIR": str(data / "models"),
        "OMNIX_PACKS_DIR": str(config.packs),
        "HF_HUB_CACHE": str(config.models_cache),
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "HF_HUB_DISABLE_SYMLINKS_WARNING": "1",
        "OMNIX_PROVIDER_SECRETS_PATH": str(secrets / "provider-api-keys.dpapi"),
        # DPAPI on Windows; on macOS the same protected file with its key in the Keychain (S-8).
        "OMNIX_SECRET_STORE": "dpapi",
        "OMNIX_SECRET_STORE_PATH": str(secrets / "omnix-secrets.dpapi"),
        # macOS: the desktop app's own Keychain item, apart from a developer Omnix's (S-8).
        "OMNIX_KEYCHAIN_SERVICE": "Omnix Desktop",
        "OMNIX_LOG_FORMAT": "json",
        # Bytecode caches go to the data folder: the install folder (a signed bundle on macOS) is never written.
        "PYTHONPYCACHEPREFIX": str(data / "pycache"),
        "PYTHONNOUSERSITE": "1",
        "PYTHONSAFEPATH": "1",
    }
    if config.ffmpeg is not None:
        env["OMNIX_FFMPEG"] = str(config.ffmpeg)
    return env


def child_environment(config: LaunchConfig, inherited: Mapping[str, str] | None = None, *,
                      owner: bool = True) -> dict[str, str]:
    """The gateway's, job worker's and database tools' environment.

    ``owner`` adds the owner role's URL (OMNIX_MIGRATION_DATABASE_URL) for migrations, backup, restore and grants.
    The running gateway gets ``owner=False``: it reaches PostgreSQL only as omnix_app under row-level security."""
    source = dict(os.environ if inherited is None else inherited)
    required = ("OMNIXDESKTOP_DB_OWNER_PASSWORD",) if owner else ()
    missing = [name for name in (*required, "OMNIXDESKTOP_DB_APP_PASSWORD", "OMNIXDESKTOP_NOTIFY_SECRET")
               if not source.get(name)]
    if missing:
        raise ValueError(f"the supervisor must pass {', '.join(missing)}")
    env = _system(source, config)
    env.update(_common(config))
    data = config.data_dir
    service_url = {name: f"http://127.0.0.1:{config.port(name)}" for name in MODEL_SERVICES if name in config.service_ports}
    env.update({
        "OMNIX_AUTH_MODE": "local",
        "OMNIX_LOCAL_JOB_WORKER": "1",
        "OMNIX_AUTH_REGISTRATION": "invite",
        "OMNIX_AUTH_LAUNCHER_FIRST_PASSWORD": "1",
        "OMNIX_AUTH_DESKTOP_HANDOFF": "1",
        "OMNIX_PRODUCT_NAME": "Omnix",
        # The one origin the windows load from; nothing else may post.
        "OMNIX_ALLOWED_ORIGINS": config.origin,
        "OMNIX_DATABASE_URL": _database_url(DB_APP, source["OMNIXDESKTOP_DB_APP_PASSWORD"], config.pg_port),
        "OMNIX_JOB_WORKER_METRICS_PORT": str(config.metrics_port),
        "OMNIX_DESKTOP_WEB_DIST": str(config.web_dist),
        # The model services run in their runtime packs; the gateway has no Torch and must never load a model.
        "OMNIX_GATEWAY_TTS_HTTP": "1",
        "OMNIX_TTS_URL": service_url.get("tts", ""),
        "OMNIX_STT_URL": service_url.get("stt", ""),
        "OMNIX_IMAGE_ENABLED": "1" if "image" in service_url else "0",
        "OMNIX_IMAGE_URL": service_url.get("image", ""),
        "OMNIX_AUDIO_ENABLED": "0",
        # Desktop notifications go to the shell's loopback listener (S-6).
        "OMNIX_TRADING_DESKTOP_NOTIFY_URL": f"http://127.0.0.1:{config.notify_port}/notify",
        "OMNIX_TRADING_DESKTOP_NOTIFY_SECRET": source["OMNIXDESKTOP_NOTIFY_SECRET"],
        # Trading is research only here: no scheduled import of the research handoff (AGENTS.md "Trading").
        "OMNIX_TRADING_PROSPECTIVE_GAP_HANDOFF_IMPORT": "0",
        # Agents: never unsandboxed, no default repository (the user picks a workspace per run), and this
        # install's own sandbox names and gateway port (DT-3.5).
        "OMNIX_AGENT_ALLOW_UNSANDBOXED": "false",
        "OMNIX_AGENT_DOCKER_IMAGE": SANDBOX_IMAGE,
        "OMNIX_AGENT_SANDBOX_NETWORK": SANDBOX_NETWORK,
        "OMNIX_AGENT_RELAY_CONTAINER": SANDBOX_RELAY,
        "OMNIX_AGENT_BROKER_URL": f"{config.origin}/api/agent-runs",
        "OMNIX_AGENT_MODEL_GATEWAY_URL": f"{config.origin}/api/agent-model/v1",
        "OMNIX_AGENT_LOG_DIR": str(data / "logs" / "agent"),
    })
    if config.features:
        env["OMNIX_FEATURES"] = config.features
    if owner:
        env["OMNIX_MIGRATION_DATABASE_URL"] = _database_url(DB_OWNER, source["OMNIXDESKTOP_DB_OWNER_PASSWORD"],
                                                            config.pg_port)
    google_secret = source.get("OMNIXDESKTOP_GOOGLE_CLIENT_SECRET")
    if config.google_client_id and google_secret:
        # All three or none (auth/settings.py); the redirect is the usual callback on the persisted port.
        env["OMNIX_GOOGLE_CLIENT_ID"] = config.google_client_id
        env["OMNIX_GOOGLE_CLIENT_SECRET"] = google_secret
        env["OMNIX_GOOGLE_REDIRECT_URI"] = f"{config.origin}/api/auth/google/callback"
    return env


def service_environment(config: LaunchConfig, service: str, *, service_token: str, site_dirs: list[Path],
                        model_dir: Path | None = None, inherited: Mapping[str, str] | None = None) -> dict[str, str]:
    """A model service's environment: only what it needs to start, authenticate and reach its permits."""
    source = dict(os.environ if inherited is None else inherited)
    if not source.get("OMNIXDESKTOP_DB_APP_PASSWORD"):
        raise ValueError("the supervisor must pass OMNIXDESKTOP_DB_APP_PASSWORD")
    if not service_token:
        raise ValueError("a model service needs the service token")
    env = _system(source, config)
    env.update(_common(config))
    # A service only reads bytecode: its packs' was compiled at install (packs._compile_bytecode), the app's and the
    # standard library's at staging. A service compiling on its first run stopped accepting connections on Windows.
    env.pop("PYTHONPYCACHEPREFIX", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    port = str(config.port(service))
    env.update({
        "OMNIX_SERVICE_TOKEN": service_token,
        "OMNIX_DATABASE_URL": _database_url(DB_APP, source["OMNIXDESKTOP_DB_APP_PASSWORD"], config.pg_port),
        "OMNIX_ALLOWED_ORIGINS": config.origin,
        # A busy port is reported, never cleared by killing its owner (it may be a developer Omnix's).
        "OMNIX_LAUNCHER_KILL_PORT": "0",
        # Models load only from the verified, pinned files in the packs folder.
        "HF_HUB_OFFLINE": "1",
        "OMNIX_DESKTOP_SITE_DIRS": os.pathsep.join(str(path) for path in site_dirs),
    })
    if service == "stt":
        env["OMNIX_STT_PORT"] = port
    elif service == "tts":
        env["OMNIX_TTS_PORT"] = port
        if model_dir is not None:
            env["OMNIX_TTS_MODEL_DIR"] = str(model_dir)
            env["OMNIX_QWEN3_TTS_MODEL_DIR"] = str(model_dir)
        if sys.platform == "darwin":
            env["OMNIX_TTS_DEVICE"] = "mps"
    elif service == "image":
        # FLUX loads when the image view asks for it, after a memory check (OMNIX_MODEL_LOAD_COMMIT_BYTES).
        env.update({"OMNIX_IMAGE_PORT": port, "OMNIX_IMAGE_ENABLED": "1", "OMNIX_IMAGE_SERVICE_MODE": "1",
                    "OMNIX_IMAGE_URL": ""})
    else:
        raise ValueError(f"unknown model service {service!r}")
    return env


def apply_environment(env: Mapping[str, str]) -> None:
    """Replace this process's environment with ``env`` (children inherit it)."""
    for name in list(os.environ):
        if name not in env:
            del os.environ[name]
    os.environ.update(env)


def owner_database_url(config: LaunchConfig, inherited: Mapping[str, str] | None = None) -> str:
    source = os.environ if inherited is None else inherited
    return _database_url(DB_OWNER, source["OMNIXDESKTOP_DB_OWNER_PASSWORD"], config.pg_port)


__all__ = [
    "DB_APP", "DB_NAME", "DB_OWNER", "DROPPED_PREFIXES", "LaunchConfig", "MODEL_SERVICES", "SECRET_VARIABLES",
    "SYSTEM_ALLOWLIST", "apply_environment", "child_environment", "owner_database_url", "service_environment",
]
