from __future__ import annotations

import json
import zipfile
from pathlib import Path

from tests.rpg import interactive_cli_state_zip_verify as verify_cli
from tests.rpg.interactive_cli_campaign_state import (
    MANIFEST_FILENAME,
    STATEFUL_INTERACTIVE_CLI_VERSION,
    ZIP_CHECKPOINT_DIRNAME,
)
from app.rpg.interactive_cli_state_checkpoint import create_interactive_cli_state_checkpoint, serialize_interactive_cli_state_checkpoint


def _write_valid_zip(path: Path) -> None:
    bundle = {
        "format_version": "interactive_cli_state_bundle_v1",
        "states": {
            "memory": {"facts": {"trail_name": "Ash Lantern"}},
        },
    }
    checkpoint = create_interactive_cli_state_checkpoint(bundle, turn_index=1)
    manifest = {
        "format_version": STATEFUL_INTERACTIVE_CLI_VERSION,
        "checkpoint_dir": "unused",
        "checkpoint_count": 1,
        "checkpoints": ["turn-0001-interactive-cli-state-checkpoint.json"],
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(MANIFEST_FILENAME, json.dumps(manifest, sort_keys=True))
        archive.writestr(
            f"{ZIP_CHECKPOINT_DIRNAME}/turn-0001-interactive-cli-state-checkpoint.json",
            serialize_interactive_cli_state_checkpoint(checkpoint),
        )


def test_phase13_75_verifier_cli_returns_zero_for_valid_zip(tmp_path: Path, capsys) -> None:
    zip_path = tmp_path / "interactive-campaign-results.zip"
    _write_valid_zip(zip_path)

    assert verify_cli.main([str(zip_path)]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["checkpoint_count"] == 1
    assert payload["restored_turns"] == [1]


def test_phase13_75_verifier_cli_returns_one_for_missing_zip(tmp_path: Path, capsys) -> None:
    assert verify_cli.main([str(tmp_path / "missing.zip")]) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"] == "zip_missing"


def test_phase13_75_verifier_cli_returns_one_for_invalid_zip(tmp_path: Path, capsys) -> None:
    invalid_zip = tmp_path / "invalid.zip"
    invalid_zip.write_text("not a zip", encoding="utf-8")

    assert verify_cli.main([str(invalid_zip)]) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"] == "zip_invalid"


def test_phase13_76_verifier_cli_writes_summary_json_for_valid_zip(tmp_path: Path, capsys) -> None:
    zip_path = tmp_path / "interactive-campaign-results.zip"
    summary_path = tmp_path / "nested" / "state-zip-verification-summary.json"
    _write_valid_zip(zip_path)

    assert verify_cli.main([str(zip_path), "--summary-path", str(summary_path)]) == 0

    stdout_payload = json.loads(capsys.readouterr().out)
    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert stdout_payload["ok"] is True
    assert summary_payload["summary_format_version"] == verify_cli.STATE_ZIP_VERIFY_SUMMARY_VERSION
    assert summary_payload["ok"] is True
    assert summary_payload["checkpoint_count"] == 1
    assert summary_payload["restored_turns"] == [1]


def test_phase13_76_verifier_cli_writes_summary_json_for_invalid_zip(tmp_path: Path, capsys) -> None:
    summary_path = tmp_path / "state-zip-verification-summary.json"

    assert verify_cli.main([str(tmp_path / "missing.zip"), "--summary-path", str(summary_path)]) == 1

    stdout_payload = json.loads(capsys.readouterr().out)
    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert stdout_payload["error"] == "zip_missing"
    assert summary_payload["summary_format_version"] == verify_cli.STATE_ZIP_VERIFY_SUMMARY_VERSION
    assert summary_payload["ok"] is False
    assert summary_payload["error"] == "zip_missing"


def test_phase13_76_summary_writer_creates_parent_dirs(tmp_path: Path) -> None:
    path = verify_cli.write_state_zip_verification_summary(
        result={"ok": True, "checkpoint_count": 0},
        summary_path=tmp_path / "a" / "b" / "summary.json",
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == {
        "summary_format_version": verify_cli.STATE_ZIP_VERIFY_SUMMARY_VERSION,
        "checkpoint_count": 0,
        "ok": True,
    }
