from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from app.persistence import cli
from app.persistence.config import DatabaseSettings


class _Database:
    def __init__(self, settings) -> None:
        self.settings = settings
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_cli_usage_errors_are_machine_readable_json(capsys) -> None:
    exit_code = cli.main(["cutover"])
    report = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert report["ok"] is False
    assert report["error"] == "CliUsageError"


def test_cli_exposes_authoritative_cutover_and_recovery_commands() -> None:
    parser = cli.build_parser()
    cutover = parser.parse_args(
        [
            "cutover",
            "activate-frozen",
            "--software-revision",
            "test-head",
            "--schema-version",
            "schema",
            "--operator-note",
            "restore rehearsed",
            "--legacy-import-run-id",
            "legacy-import:test",
            "--backup-generation-id",
            "backup:test",
        ]
    )
    recovery = parser.parse_args(
        [
            "recovery",
            "verify-blobs",
            "--backup-generation-id",
            "backup:test",
            "--blob-root",
            "restored-blobs",
            "--database-restore-verified",
            "--migrations-verified",
            "--smoke-checks-verified",
        ]
    )
    assert cutover.cutover_command == "activate-frozen"
    assert recovery.recovery_command == "verify-blobs"


def test_operator_output_redacts_secret_keys_and_credential_urls(capsys) -> None:
    cli._render(
        {
            "api_key": "should-not-appear",
            "message": "failed at postgresql://user:password@localhost/omnix",
        }
    )
    output = capsys.readouterr().out
    assert "should-not-appear" not in output
    assert "password" not in output
    assert "[REDACTED]" in output
    assert "postgresql://***:***@localhost/omnix" in output


def test_postgresql_tools_receive_password_via_environment_not_process_arguments() -> None:
    settings = DatabaseSettings(url="postgresql://user:p%40ss@localhost:5432/omnix")
    safe_url, environment = cli._tool_database_arguments(settings)
    assert "p%40ss" not in safe_url
    assert "p@ss" not in safe_url
    assert safe_url == "postgresql://user@localhost:5432/omnix"
    assert environment["PGPASSWORD"] == "p@ss"


def test_failed_restore_returns_nonzero_json(monkeypatch, tmp_path, capsys) -> None:
    backup = tmp_path / "broken.dump"
    backup.write_bytes(b"not-a-dump")
    settings = DatabaseSettings(url="postgresql://user:password@localhost/omnix")
    monkeypatch.setattr(cli, "database_settings", lambda: settings)
    monkeypatch.setattr(cli, "PostgresDatabase", _Database)
    monkeypatch.setattr(cli, "_require_tool", lambda name: name)
    monkeypatch.setattr(
        cli,
        "_run_tool",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("restore failed")),
    )
    exit_code = cli.main(["restore", str(backup), "--clean"])
    report = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert report == {
        "error": "RuntimeError",
        "message": "restore failed",
        "ok": False,
    }


def test_legacy_activate_command_cannot_bypass_state_machine(monkeypatch, capsys) -> None:
    script = Path(__file__).resolve().parents[3] / "scripts" / "import_legacy_persistence_bundle.py"
    spec = importlib.util.spec_from_file_location("legacy_import_cli_test", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(sys, "argv", [str(script), "activate", "legacy-import:test"])
    exit_code = module.main()
    report = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert report["error"] == "DeprecatedCutoverCommand"
