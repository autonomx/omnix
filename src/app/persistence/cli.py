from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from .config import database_settings
from .database import PostgresDatabase
from .migrations import apply_migrations, migration_status


def _render(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, default=str))


def _require_tool(name: str) -> str:
    resolved = shutil.which(name)
    if not resolved:
        raise RuntimeError(f"required PostgreSQL tool is not installed: {name}")
    return resolved


def _run_tool(arguments: list[str]) -> None:
    completed = subprocess.run(arguments, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"PostgreSQL tool failed with exit code {completed.returncode}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Omnix PostgreSQL operations")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("health", help="Check PostgreSQL connectivity")
    subparsers.add_parser("migrate", help="Apply pending migrations")
    subparsers.add_parser("status", help="Show migration state")
    subparsers.add_parser("verify", help="Require healthy PostgreSQL and zero migration drift")

    backup = subparsers.add_parser("backup", help="Create a pg_dump custom-format backup")
    backup.add_argument("output", type=Path)

    restore = subparsers.add_parser("restore", help="Restore a custom-format backup")
    restore.add_argument("input", type=Path)
    restore.add_argument("--clean", action="store_true", help="Drop restored objects first")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    settings = database_settings()
    database = PostgresDatabase(settings)
    try:
        if args.command == "health":
            report = database.health()
            _render(report)
            return 0 if report.get("ok") is True else 1
        if args.command == "migrate":
            report = apply_migrations(database)
            _render(report)
            return 0 if report.get("ok") is True else 1
        if args.command == "status":
            report = migration_status(database)
            _render(report)
            return 0 if report.get("ok") is True else 1
        if args.command == "verify":
            health = database.health()
            if health.get("ok") is not True:
                _render({"ok": False, "health": health})
                return 1
            status = migration_status(database)
            ok = status.get("ok") is True and status.get("pending") == []
            _render({"ok": ok, "health": health, "migrations": status})
            return 0 if ok else 1
        if args.command == "backup":
            args.output.parent.mkdir(parents=True, exist_ok=True)
            _run_tool(
                [
                    _require_tool("pg_dump"),
                    "--format=custom",
                    "--no-owner",
                    "--no-acl",
                    f"--file={args.output}",
                    f"--dbname={settings.url}",
                ]
            )
            _render({"ok": True, "backup": str(args.output.resolve())})
            return 0
        if args.command == "restore":
            if not args.input.is_file():
                raise RuntimeError(f"backup does not exist: {args.input}")
            arguments = [
                _require_tool("pg_restore"),
                "--no-owner",
                "--no-acl",
                f"--dbname={settings.url}",
            ]
            if args.clean:
                arguments.extend(["--clean", "--if-exists"])
            arguments.append(str(args.input))
            _run_tool(arguments)
            _render({"ok": True, "restored": str(args.input.resolve())})
            return 0
        raise RuntimeError(f"unsupported command: {args.command}")
    except Exception as exc:
        _render({"ok": False, "error": exc.__class__.__name__, "message": str(exc)})
        return 1
    finally:
        database.close()


if __name__ == "__main__":
    raise SystemExit(main())
