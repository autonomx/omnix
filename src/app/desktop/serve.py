"""The one Python entry point the desktop supervisor calls for the gateway and database tools (roadmap §4.2).

    python -m app.desktop.serve serve       --config launch.json   # the gateway, its job worker and schedulers
    python -m app.desktop.serve migrate     --config launch.json   # release migrations, as the owner role
    python -m app.desktop.serve status      --config launch.json   # the migration report (JSON), as the owner role
    python -m app.desktop.serve login-code  --config launch.json   # first run only: the owner's one-time sign-in code
    python -m app.desktop.serve backup PATH --config launch.json   # pg_dump custom format, as the owner role
    python -m app.desktop.serve restore PATH --config launch.json  # then the runtime role's grants are re-applied
    python -m app.desktop.serve grants      --config launch.json   # re-apply the runtime role's grants
    python -m app.desktop.serve embeddings  --config launch.json   # fetch the pinned memory embedding model
    python -m app.desktop.serve env         --config launch.json   # the child environment, secrets redacted

Each command first replaces this process's environment with ``app.desktop.env.child_environment``, so the gateway,
the job worker it starts and the database tools all run with exactly that environment.
"""
from __future__ import annotations

import argparse
import json
import runpy
import sys
from pathlib import Path

from app.desktop.env import DB_APP, LaunchConfig, apply_environment, child_environment

SRC = Path(__file__).resolve().parents[2]
ROOT = SRC.parent
SCRIPTS = ROOT / "scripts"
_REDACT = ("PASSWORD", "SECRET", "TOKEN", "DATABASE_URL")


def _prepare(config_path: Path, *, owner: bool = True) -> LaunchConfig:
    config = LaunchConfig.load(config_path)
    env = child_environment(config, owner=owner)
    # Under the bundled interpreter the ._pth file sets the import roots and ignores PYTHONPATH; a development
    # interpreter needs it for the job worker, which starts with the same executable.
    env["PYTHONPATH"] = f"{SRC}{';' if sys.platform == 'win32' else ':'}{SCRIPTS}"
    apply_environment(env)
    for folder in (config.data_dir / "resources", config.data_dir / "secrets", config.data_dir / "models", config.packs):
        folder.mkdir(parents=True, exist_ok=True)
    for path in (str(SRC), str(SCRIPTS)):
        if path not in sys.path:
            sys.path.insert(0, path)
    return config


def gateway_command(config: LaunchConfig, python: str) -> list[str]:
    return [
        python, str(SCRIPTS / "run_omnix_gateway.py"),
        "--managed-stdin", "--api-replicas", "0",
        "--host", "127.0.0.1", "--port", str(config.http_port),
        "--app", "app.desktop.desktop_app:app",
    ]


def _serve(config: LaunchConfig) -> int:
    sys.argv = gateway_command(config, sys.executable)[1:]
    try:
        runpy.run_path(str(SCRIPTS / "run_omnix_gateway.py"), run_name="__main__")
    except SystemExit as exit_:
        return int(exit_.code or 0)
    return 0


def _persistence(argv: list[str]) -> int:
    from app.persistence.cli import main

    return main(argv)


def _grants() -> int:
    """The runtime role's grants; pg_dump --no-acl drops them, so a restore needs them again."""
    import psycopg

    from app.persistence.config import migration_database_settings

    with psycopg.connect(migration_database_settings().url, autocommit=True) as connection:
        connection.execute(f"GRANT USAGE ON SCHEMA public TO {DB_APP}")
        connection.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {DB_APP}")
        connection.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {DB_APP}")
        connection.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {DB_APP}")
        connection.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {DB_APP}")
    print(json.dumps({"grants": "applied", "role": DB_APP}))
    return 0


def _login_code() -> int:
    from app.security.auth import AuthMode, AuthService, resolve_auth_settings

    settings = resolve_auth_settings()
    if settings.mode is not AuthMode.LOCAL:
        raise SystemExit("login codes need OMNIX_AUTH_MODE=local")
    print(AuthService(settings).issue_login_code())
    return 0


def _embeddings() -> int:
    from app.platform.assistant_memory.v2.embeddings import download_model, model_installed

    if not model_installed():
        download_model()
    print(json.dumps({"embeddings": "installed"}))
    return 0


def _service_token() -> int:
    """The service token the gateway and model services share (created once in the protected store)."""
    from app.security.service_credentials import initialize_service_token

    print(initialize_service_token())
    return 0


def _show_env() -> int:
    import os

    shown = {name: ("***" if any(marker in name for marker in _REDACT) else value)
             for name, value in sorted(os.environ.items())}
    print(json.dumps(shown, indent=1))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.desktop.serve", description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["serve", "migrate", "status", "login-code", "backup", "restore", "grants",
                                            "embeddings", "service-token", "env"])
    parser.add_argument("path", nargs="?", type=Path, help="backup or restore file")
    parser.add_argument("--config", required=True, type=Path, help="the supervisor's launch config (JSON)")
    args = parser.parse_args(argv)
    # The gateway runs without the owner role's URL; the one-shot commands (migrate, backup, ...) need it.
    config = _prepare(args.config, owner=args.command not in {"serve", "embeddings", "service-token"})
    if args.command == "serve":
        return _serve(config)
    if args.command == "migrate":
        return _persistence(["migrate"])
    if args.command == "status":
        return _persistence(["status"])
    if args.command in {"backup", "restore"}:
        if args.path is None:
            parser.error(f"{args.command} needs a file")
        code = _persistence([args.command, str(args.path)] + (["--clean"] if args.command == "restore" else []))
        return _grants() if code == 0 and args.command == "restore" else code
    if args.command == "grants":
        return _grants()
    if args.command == "login-code":
        return _login_code()
    if args.command == "embeddings":
        return _embeddings()
    if args.command == "service-token":
        return _service_token()
    return _show_env()


if __name__ == "__main__":
    raise SystemExit(main())
