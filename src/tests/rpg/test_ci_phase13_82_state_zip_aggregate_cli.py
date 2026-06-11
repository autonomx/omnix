from __future__ import annotations

import json
from pathlib import Path

from tests.rpg import interactive_cli_state_zip_verify as verify_cli


def _summary(*, ok: bool, checkpoint_count: int = 0, restored_turns: list[int] | None = None, error: str | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "summary_format_version": verify_cli.STATE_ZIP_VERIFY_SUMMARY_VERSION,
        "ok": ok,
        "checkpoint_count": checkpoint_count,
        "restored_turns": list(restored_turns or []),
    }
    if error:
        payload["error"] = error
    return payload


def _write_summary(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def test_phase13_82_reads_and_aggregates_summary_files(tmp_path: Path) -> None:
    first = _write_summary(tmp_path / "first.json", _summary(ok=True, checkpoint_count=1, restored_turns=[1]))
    second = _write_summary(tmp_path / "second.json", _summary(ok=True, checkpoint_count=2, restored_turns=[1, 2]))

    aggregate = verify_cli.aggregate_state_zip_verification_summary_files([first, second])

    assert aggregate["ok"] is True
    assert aggregate["summary_count"] == 2
    assert aggregate["total_checkpoint_count"] == 3
    assert aggregate["total_restored_turn_count"] == 3


def test_phase13_82_aggregate_cli_writes_output_and_returns_zero(tmp_path: Path, capsys) -> None:
    first = _write_summary(tmp_path / "first.json", _summary(ok=True, checkpoint_count=1, restored_turns=[1]))
    second = _write_summary(tmp_path / "second.json", _summary(ok=True, checkpoint_count=1, restored_turns=[1]))
    aggregate_path = tmp_path / "nested" / "aggregate.json"

    exit_code = verify_cli.main(
        [
            "--aggregate-summary",
            str(first),
            "--aggregate-summary",
            str(second),
            "--aggregate-path",
            str(aggregate_path),
        ]
    )

    output = capsys.readouterr()
    stdout_payload = json.loads(output.out)
    persisted_payload = json.loads(aggregate_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert stdout_payload == persisted_payload
    assert stdout_payload["ok"] is True
    assert stdout_payload["passed"] == 2


def test_phase13_82_aggregate_cli_returns_one_for_failed_summary(tmp_path: Path, capsys) -> None:
    failed = _write_summary(tmp_path / "failed.json", _summary(ok=False, error="zip_missing"))

    exit_code = verify_cli.main(["--aggregate-summary", str(failed)])

    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert exit_code == 1
    assert payload["ok"] is False
    assert payload["failed"] == 1
    assert payload["entries"][0]["error"] == "zip_missing"


def test_phase13_82_aggregate_cli_returns_one_for_schema_error(tmp_path: Path, capsys) -> None:
    bad = _write_summary(tmp_path / "bad.json", {"ok": True})

    exit_code = verify_cli.main(["--aggregate-summary", str(bad)])

    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert exit_code == 1
    assert payload["invalid_summary_count"] == 1
    assert payload["entries"][0]["error"] == "summary_required_keys_missing"


def test_phase13_82_verify_cli_requires_zip_path_without_aggregate_mode() -> None:
    try:
        verify_cli.main([])
    except SystemExit as exc:
        assert str(exc) == "zip_path is required unless --aggregate-summary is provided"
    else:
        raise AssertionError("expected SystemExit")


def test_phase13_83_aggregate_status_marker_round_trips_success() -> None:
    marker = verify_cli.render_state_zip_verification_aggregate_status_marker(
        {
            "ok": True,
            "summary_count": 2,
            "passed": 2,
            "failed": 0,
            "invalid_summary_count": 0,
        }
    )

    assert marker == "[INTERACTIVE_CLI_STATE_ZIP_AGGREGATE] ok=true summary_count=2 passed=2 failed=0 invalid_summary_count=0"
    assert verify_cli.parse_state_zip_verification_aggregate_status_marker(marker) == {
        "ok": True,
        "aggregate_ok": True,
        "summary_count": 2,
        "passed": 2,
        "failed": 0,
        "invalid_summary_count": 0,
    }


def test_phase13_83_aggregate_status_marker_round_trips_failure() -> None:
    marker = verify_cli.render_state_zip_verification_aggregate_status_marker(
        {
            "ok": False,
            "summary_count": 2,
            "passed": 1,
            "failed": 1,
            "invalid_summary_count": 0,
        }
    )

    assert marker == "[INTERACTIVE_CLI_STATE_ZIP_AGGREGATE] ok=false summary_count=2 passed=1 failed=1 invalid_summary_count=0"
    assert verify_cli.parse_state_zip_verification_aggregate_status_marker(marker) == {
        "ok": True,
        "aggregate_ok": False,
        "summary_count": 2,
        "passed": 1,
        "failed": 1,
        "invalid_summary_count": 0,
    }


def test_phase13_83_aggregate_cli_emits_status_marker_to_stderr(tmp_path: Path, capsys) -> None:
    first = _write_summary(tmp_path / "first.json", _summary(ok=True, checkpoint_count=1, restored_turns=[1]))

    exit_code = verify_cli.main(["--aggregate-summary", str(first)])

    output = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(output.out)["ok"] is True
    assert output.err.strip() == "[INTERACTIVE_CLI_STATE_ZIP_AGGREGATE] ok=true summary_count=1 passed=1 failed=0 invalid_summary_count=0"


def test_phase13_83_aggregate_status_marker_rejects_malformed_values() -> None:
    wrong_prefix = "[OTHER] ok=true summary_count=1 passed=1 failed=0 invalid_summary_count=0"
    missing_key = "[INTERACTIVE_CLI_STATE_ZIP_AGGREGATE] ok=true summary_count=1 passed=1 failed=0"
    invalid_ok = "[INTERACTIVE_CLI_STATE_ZIP_AGGREGATE] ok=yes summary_count=1 passed=1 failed=0 invalid_summary_count=0"
    invalid_count = "[INTERACTIVE_CLI_STATE_ZIP_AGGREGATE] ok=true summary_count=x passed=1 failed=0 invalid_summary_count=0"
    negative_count = "[INTERACTIVE_CLI_STATE_ZIP_AGGREGATE] ok=true summary_count=1 passed=-1 failed=0 invalid_summary_count=0"

    assert verify_cli.parse_state_zip_verification_aggregate_status_marker(wrong_prefix)["error"] == "aggregate_status_marker_prefix_mismatch"
    assert verify_cli.parse_state_zip_verification_aggregate_status_marker(missing_key)["error"] == "aggregate_status_marker_required_keys_missing"
    assert verify_cli.parse_state_zip_verification_aggregate_status_marker(invalid_ok)["error"] == "aggregate_status_marker_ok_invalid"
    assert verify_cli.parse_state_zip_verification_aggregate_status_marker(invalid_count)["error"] == "aggregate_status_marker_count_invalid"
    assert verify_cli.parse_state_zip_verification_aggregate_status_marker(negative_count)["error"] == "aggregate_status_marker_count_negative"
