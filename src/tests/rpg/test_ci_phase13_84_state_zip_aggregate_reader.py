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


def test_phase13_85_aggregate_read_cli_returns_zero_for_valid_payload(tmp_path: Path, capsys) -> None:
    path = _write_json(tmp_path / "state-zip-aggregate.json", _aggregate_payload())

    assert aggregate_verify.main([str(path)]) == 0

    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert payload["ok"] is True
    assert payload["path"] == str(path)
    assert payload["aggregate"]["ok"] is True


def test_phase13_85_aggregate_read_cli_returns_one_for_missing_file(tmp_path: Path, capsys) -> None:
    path = tmp_path / "missing-aggregate.json"

    assert aggregate_verify.main([str(path)]) == 1

    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert payload == {
        "ok": False,
        "error": "aggregate_file_missing",
        "path": str(path),
    }


def test_phase13_85_aggregate_read_cli_returns_one_for_schema_error(tmp_path: Path, capsys) -> None:
    path = _write_json(tmp_path / "bad-schema.json", {"aggregate_format_version": "old", "ok": True})

    assert aggregate_verify.main([str(path)]) == 1

    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert payload["ok"] is False
    assert payload["error"] == "aggregate_format_version_mismatch"
    assert payload["validation"]["expected"] == verify_cli.STATE_ZIP_VERIFY_AGGREGATE_VERSION


def test_phase13_86_aggregate_read_status_marker_reports_success() -> None:
    marker = aggregate_verify.render_state_zip_verification_aggregate_read_status_marker(
        {"ok": True, "aggregate": {"ok": True, "summary_count": 2, "failed": 0}}
    )

    assert marker == "[INTERACTIVE_CLI_STATE_ZIP_AGGREGATE_READ] ok=true aggregate_ok=true summary_count=2 failed=0 error=none"
    assert aggregate_verify.parse_state_zip_verification_aggregate_read_status_marker(marker) == {
        "ok": True,
        "read_ok": True,
        "aggregate_ok": True,
        "summary_count": 2,
        "failed": 0,
        "read_error": "none",
    }


def test_phase13_86_aggregate_read_status_marker_reports_read_failure() -> None:
    marker = aggregate_verify.render_state_zip_verification_aggregate_read_status_marker(
        {"ok": False, "error": "aggregate_file_missing"}
    )

    assert marker == "[INTERACTIVE_CLI_STATE_ZIP_AGGREGATE_READ] ok=false aggregate_ok=false summary_count=0 failed=0 error=aggregate_file_missing"
    assert aggregate_verify.parse_state_zip_verification_aggregate_read_status_marker(marker) == {
        "ok": True,
        "read_ok": False,
        "aggregate_ok": False,
        "summary_count": 0,
        "failed": 0,
        "read_error": "aggregate_file_missing",
    }


def test_phase13_86_aggregate_read_cli_emits_status_marker_to_stderr(tmp_path: Path, capsys) -> None:
    path = _write_json(tmp_path / "state-zip-aggregate.json", _aggregate_payload())

    assert aggregate_verify.main([str(path)]) == 0

    output = capsys.readouterr()
    assert json.loads(output.out)["ok"] is True
    assert output.err.strip() == "[INTERACTIVE_CLI_STATE_ZIP_AGGREGATE_READ] ok=true aggregate_ok=true summary_count=1 failed=0 error=none"


def test_phase13_86_aggregate_read_status_marker_rejects_malformed_values() -> None:
    assert aggregate_verify.parse_state_zip_verification_aggregate_read_status_marker("[OTHER] ok=true") == {
        "ok": False,
        "error": "aggregate_read_marker_prefix_mismatch",
    }
    missing = "[INTERACTIVE_CLI_STATE_ZIP_AGGREGATE_READ] ok=true aggregate_ok=true summary_count=1 error=none"
    bad_bool = "[INTERACTIVE_CLI_STATE_ZIP_AGGREGATE_READ] ok=yes aggregate_ok=true summary_count=1 failed=0 error=none"
    bad_count = "[INTERACTIVE_CLI_STATE_ZIP_AGGREGATE_READ] ok=true aggregate_ok=true summary_count=x failed=0 error=none"
    negative_count = "[INTERACTIVE_CLI_STATE_ZIP_AGGREGATE_READ] ok=true aggregate_ok=true summary_count=1 failed=-1 error=none"

    assert aggregate_verify.parse_state_zip_verification_aggregate_read_status_marker(missing)["error"] == "aggregate_read_marker_required_keys_missing"
    assert aggregate_verify.parse_state_zip_verification_aggregate_read_status_marker(bad_bool)["error"] == "aggregate_read_marker_bool_invalid"
    assert aggregate_verify.parse_state_zip_verification_aggregate_read_status_marker(bad_count)["error"] == "aggregate_read_marker_count_invalid"
    assert aggregate_verify.parse_state_zip_verification_aggregate_read_status_marker(negative_count)["error"] == "aggregate_read_marker_count_negative"


def test_phase13_87_aggregate_read_artifact_bundle_accepts_matching_marker(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "state-zip-aggregate.json", _aggregate_payload())
    read_result = aggregate_verify.read_state_zip_verification_aggregate(path)
    marker = aggregate_verify.render_state_zip_verification_aggregate_read_status_marker(read_result)

    result = aggregate_verify.verify_state_zip_aggregate_read_artifact_bundle(
        aggregate_path=path,
        status_marker=marker,
    )

    assert result["ok"] is True
    assert result["marker_result"] == {
        "ok": True,
        "read_ok": True,
        "aggregate_ok": True,
        "summary_count": 1,
        "failed": 0,
        "read_error": "none",
    }


def test_phase13_87_aggregate_read_artifact_bundle_rejects_invalid_marker(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "state-zip-aggregate.json", _aggregate_payload())

    result = aggregate_verify.verify_state_zip_aggregate_read_artifact_bundle(
        aggregate_path=path,
        status_marker="[OTHER] ok=true",
    )

    assert result["ok"] is False
    assert result["error"] == "aggregate_read_marker_invalid"
    assert result["marker_result"]["error"] == "aggregate_read_marker_prefix_mismatch"


def test_phase13_87_aggregate_read_artifact_bundle_rejects_mismatched_marker(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "state-zip-aggregate.json", _aggregate_payload(ok=False))
    marker = "[INTERACTIVE_CLI_STATE_ZIP_AGGREGATE_READ] ok=true aggregate_ok=true summary_count=1 failed=0 error=none"

    result = aggregate_verify.verify_state_zip_aggregate_read_artifact_bundle(
        aggregate_path=path,
        status_marker=marker,
    )

    assert result["ok"] is False
    assert result["error"] == "aggregate_read_marker_mismatch"
    assert result["mismatches"] == {
        "aggregate_ok": {"expected": False, "actual": True},
        "failed": {"expected": 1, "actual": 0},
    }
