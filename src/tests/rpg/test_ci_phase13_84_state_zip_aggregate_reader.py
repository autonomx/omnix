from __future__ import annotations

import json
from pathlib import Path

from tests.rpg import interactive_cli_state_zip_aggregate_verify as aggregate_verify
from tests.rpg import interactive_cli_state_zip_verify as verify_cli


def _aggregate_payload(*, ok: bool = True) -> dict[str, object]:
    return {
        "aggregate_format_version": verify_cli.STATE_ZIP_VERIFY_AGGREGATE_VERSION,
        "ok": ok,
        "summary_count": 1,
        "valid_summary_count": 1,
        "invalid_summary_count": 0,
        "passed": 1 if ok else 0,
        "failed": 0 if ok else 1,
        "entries": [],
    }


def _write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def test_phase13_84_aggregate_schema_accepts_valid_payload() -> None:
    assert aggregate_verify.validate_state_zip_verification_aggregate_payload(_aggregate_payload()) == {
        "ok": True,
        "aggregate_format_version": verify_cli.STATE_ZIP_VERIFY_AGGREGATE_VERSION,
    }


def test_phase13_84_aggregate_schema_rejects_missing_keys() -> None:
    assert aggregate_verify.validate_state_zip_verification_aggregate_payload({"ok": True}) == {
        "ok": False,
        "error": "aggregate_required_keys_missing",
        "missing_keys": ["aggregate_format_version"],
    }


def test_phase13_84_aggregate_schema_rejects_wrong_version() -> None:
    assert aggregate_verify.validate_state_zip_verification_aggregate_payload(
        {"aggregate_format_version": "old", "ok": True}
    ) == {
        "ok": False,
        "error": "aggregate_format_version_mismatch",
        "expected": verify_cli.STATE_ZIP_VERIFY_AGGREGATE_VERSION,
        "actual": "old",
    }


def test_phase13_84_aggregate_schema_requires_bool_ok() -> None:
    assert aggregate_verify.validate_state_zip_verification_aggregate_payload(
        {"aggregate_format_version": verify_cli.STATE_ZIP_VERIFY_AGGREGATE_VERSION, "ok": "true"}
    ) == {
        "ok": False,
        "error": "aggregate_ok_not_bool",
        "actual_type": "str",
    }


def test_phase13_84_reads_valid_aggregate_payload(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "state-zip-aggregate.json", _aggregate_payload())

    result = aggregate_verify.read_state_zip_verification_aggregate(path)

    assert result["ok"] is True
    assert result["path"] == str(path)
    assert result["aggregate"]["aggregate_format_version"] == verify_cli.STATE_ZIP_VERIFY_AGGREGATE_VERSION
    assert result["aggregate"]["ok"] is True


def test_phase13_84_reader_reports_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.json"

    assert aggregate_verify.read_state_zip_verification_aggregate(path) == {
        "ok": False,
        "error": "aggregate_file_missing",
        "path": str(path),
    }


def test_phase13_84_reader_reports_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")

    result = aggregate_verify.read_state_zip_verification_aggregate(path)

    assert result["ok"] is False
    assert result["error"] == "aggregate_json_invalid"
    assert result["path"] == str(path)
    assert "message" in result


def test_phase13_84_reader_reports_non_object_payload(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "list.json", [])

    assert aggregate_verify.read_state_zip_verification_aggregate(path) == {
        "ok": False,
        "error": "aggregate_payload_not_object",
        "path": str(path),
        "actual_type": "list",
    }


def test_phase13_84_reader_reports_schema_error(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "bad-schema.json", {"ok": True})

    assert aggregate_verify.read_state_zip_verification_aggregate(path) == {
        "ok": False,
        "error": "aggregate_required_keys_missing",
        "path": str(path),
        "validation": {
            "ok": False,
            "error": "aggregate_required_keys_missing",
            "missing_keys": ["aggregate_format_version"],
        },
    }
