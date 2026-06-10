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

    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert payload["ok"] is True
    assert payload["checkpoint_count"] == 1
    assert payload["restored_turns"] == [1]


def test_phase13_75_verifier_cli_returns_one_for_missing_zip(tmp_path: Path, capsys) -> None:
    assert verify_cli.main([str(tmp_path / "missing.zip")]) == 1

    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert payload["ok"] is False
    assert payload["error"] == "zip_missing"


def test_phase13_75_verifier_cli_returns_one_for_invalid_zip(tmp_path: Path, capsys) -> None:
    invalid_zip = tmp_path / "invalid.zip"
    invalid_zip.write_text("not a zip", encoding="utf-8")

    assert verify_cli.main([str(invalid_zip)]) == 1

    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert payload["ok"] is False
    assert payload["error"] == "zip_invalid"


def test_phase13_76_verifier_cli_writes_summary_json_for_valid_zip(tmp_path: Path, capsys) -> None:
    zip_path = tmp_path / "interactive-campaign-results.zip"
    summary_path = tmp_path / "nested" / "state-zip-verification-summary.json"
    _write_valid_zip(zip_path)

    assert verify_cli.main([str(zip_path), "--summary-path", str(summary_path)]) == 0

    output = capsys.readouterr()
    stdout_payload = json.loads(output.out)
    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert stdout_payload["ok"] is True
    assert summary_payload["summary_format_version"] == verify_cli.STATE_ZIP_VERIFY_SUMMARY_VERSION
    assert summary_payload["ok"] is True
    assert summary_payload["checkpoint_count"] == 1
    assert summary_payload["restored_turns"] == [1]


def test_phase13_76_verifier_cli_writes_summary_json_for_invalid_zip(tmp_path: Path, capsys) -> None:
    summary_path = tmp_path / "state-zip-verification-summary.json"

    assert verify_cli.main([str(tmp_path / "missing.zip"), "--summary-path", str(summary_path)]) == 1

    output = capsys.readouterr()
    stdout_payload = json.loads(output.out)
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


def test_phase13_77_summary_schema_accepts_valid_payload() -> None:
    validation = verify_cli.validate_state_zip_verification_summary_payload(
        {
            "summary_format_version": verify_cli.STATE_ZIP_VERIFY_SUMMARY_VERSION,
            "ok": True,
            "checkpoint_count": 1,
        }
    )

    assert validation == {
        "ok": True,
        "summary_format_version": verify_cli.STATE_ZIP_VERIFY_SUMMARY_VERSION,
    }


def test_phase13_77_summary_schema_rejects_missing_required_keys() -> None:
    validation = verify_cli.validate_state_zip_verification_summary_payload({"checkpoint_count": 1})

    assert validation == {
        "ok": False,
        "error": "summary_required_keys_missing",
        "missing_keys": ["ok", "summary_format_version"],
    }


def test_phase13_77_summary_schema_rejects_wrong_version() -> None:
    validation = verify_cli.validate_state_zip_verification_summary_payload(
        {"summary_format_version": "old", "ok": True}
    )

    assert validation == {
        "ok": False,
        "error": "summary_format_version_mismatch",
        "expected": verify_cli.STATE_ZIP_VERIFY_SUMMARY_VERSION,
        "actual": "old",
    }


def test_phase13_77_summary_schema_requires_bool_ok() -> None:
    validation = verify_cli.validate_state_zip_verification_summary_payload(
        {"summary_format_version": verify_cli.STATE_ZIP_VERIFY_SUMMARY_VERSION, "ok": "true"}
    )

    assert validation == {
        "ok": False,
        "error": "summary_ok_not_bool",
        "actual_type": "str",
    }


def test_phase13_78_status_marker_reports_success_counts() -> None:
    marker = verify_cli.render_state_zip_verification_status_marker(
        {"ok": True, "checkpoint_count": 2, "restored_turns": [1, 2]}
    )

    assert marker == "[INTERACTIVE_CLI_STATE_ZIP_VERIFY] ok=true checkpoint_count=2 restored_turn_count=2 error=none"


def test_phase13_78_status_marker_reports_failure_error() -> None:
    marker = verify_cli.render_state_zip_verification_status_marker(
        {"ok": False, "error": "zip_missing"}
    )

    assert marker == "[INTERACTIVE_CLI_STATE_ZIP_VERIFY] ok=false checkpoint_count=0 restored_turn_count=0 error=zip_missing"


def test_phase13_78_verifier_cli_emits_status_marker_to_stderr(tmp_path: Path, capsys) -> None:
    zip_path = tmp_path / "interactive-campaign-results.zip"
    _write_valid_zip(zip_path)

    assert verify_cli.main([str(zip_path)]) == 0

    output = capsys.readouterr()
    assert json.loads(output.out)["ok"] is True
    assert output.err.strip() == "[INTERACTIVE_CLI_STATE_ZIP_VERIFY] ok=true checkpoint_count=1 restored_turn_count=1 error=none"


def test_phase13_79_status_marker_parser_round_trips_success_marker() -> None:
    marker = verify_cli.render_state_zip_verification_status_marker(
        {"ok": True, "checkpoint_count": 2, "restored_turns": [1, 2]}
    )

    assert verify_cli.parse_state_zip_verification_status_marker(marker) == {
        "ok": True,
        "verification_ok": True,
        "checkpoint_count": 2,
        "restored_turn_count": 2,
        "verification_error": "none",
    }


def test_phase13_79_status_marker_parser_round_trips_failure_marker() -> None:
    marker = verify_cli.render_state_zip_verification_status_marker(
        {"ok": False, "error": "zip_missing"}
    )

    assert verify_cli.parse_state_zip_verification_status_marker(marker) == {
        "ok": True,
        "verification_ok": False,
        "checkpoint_count": 0,
        "restored_turn_count": 0,
        "verification_error": "zip_missing",
    }


def test_phase13_79_status_marker_parser_rejects_wrong_prefix() -> None:
    assert verify_cli.parse_state_zip_verification_status_marker("[OTHER] ok=true") == {
        "ok": False,
        "error": "status_marker_prefix_mismatch",
    }


def test_phase13_79_status_marker_parser_rejects_missing_required_keys() -> None:
    marker = "[INTERACTIVE_CLI_STATE_ZIP_VERIFY] ok=true checkpoint_count=1 error=none"

    assert verify_cli.parse_state_zip_verification_status_marker(marker) == {
        "ok": False,
        "error": "status_marker_required_keys_missing",
        "missing_keys": ["restored_turn_count"],
    }


def test_phase13_79_status_marker_parser_rejects_invalid_values() -> None:
    bad_ok = "[INTERACTIVE_CLI_STATE_ZIP_VERIFY] ok=yes checkpoint_count=1 restored_turn_count=1 error=none"
    bad_count = "[INTERACTIVE_CLI_STATE_ZIP_VERIFY] ok=true checkpoint_count=x restored_turn_count=1 error=none"
    negative_count = "[INTERACTIVE_CLI_STATE_ZIP_VERIFY] ok=true checkpoint_count=-1 restored_turn_count=1 error=none"

    assert verify_cli.parse_state_zip_verification_status_marker(bad_ok)["error"] == "status_marker_ok_invalid"
    assert verify_cli.parse_state_zip_verification_status_marker(bad_count)["error"] == "status_marker_count_invalid"
    assert verify_cli.parse_state_zip_verification_status_marker(negative_count)["error"] == "status_marker_count_negative"


def test_phase13_80_summary_aggregate_counts_all_successes() -> None:
    aggregate = verify_cli.aggregate_state_zip_verification_summaries(
        [
            {
                "summary_format_version": verify_cli.STATE_ZIP_VERIFY_SUMMARY_VERSION,
                "ok": True,
                "checkpoint_count": 1,
                "restored_turns": [1],
            },
            {
                "summary_format_version": verify_cli.STATE_ZIP_VERIFY_SUMMARY_VERSION,
                "ok": True,
                "checkpoint_count": 2,
                "restored_turns": [1, 2],
            },
        ]
    )

    assert aggregate == {
        "aggregate_format_version": verify_cli.STATE_ZIP_VERIFY_AGGREGATE_VERSION,
        "ok": True,
        "summary_count": 2,
        "valid_summary_count": 2,
        "invalid_summary_count": 0,
        "passed": 2,
        "failed": 0,
        "total_checkpoint_count": 3,
        "total_restored_turn_count": 3,
        "entries": [
            {
                "index": 0,
                "schema_ok": True,
                "verification_ok": True,
                "checkpoint_count": 1,
                "restored_turn_count": 1,
                "error": "none",
            },
            {
                "index": 1,
                "schema_ok": True,
                "verification_ok": True,
                "checkpoint_count": 2,
                "restored_turn_count": 2,
                "error": "none",
            },
        ],
    }


def test_phase13_80_summary_aggregate_preserves_verification_failures() -> None:
    aggregate = verify_cli.aggregate_state_zip_verification_summaries(
        [
            {
                "summary_format_version": verify_cli.STATE_ZIP_VERIFY_SUMMARY_VERSION,
                "ok": False,
                "error": "zip_missing",
            }
        ]
    )

    assert aggregate["ok"] is False
    assert aggregate["passed"] == 0
    assert aggregate["failed"] == 1
    assert aggregate["entries"] == [
        {
            "index": 0,
            "schema_ok": True,
            "verification_ok": False,
            "checkpoint_count": 0,
            "restored_turn_count": 0,
            "error": "zip_missing",
        }
    ]


def test_phase13_80_summary_aggregate_preserves_schema_errors() -> None:
    aggregate = verify_cli.aggregate_state_zip_verification_summaries([{"ok": True}])

    assert aggregate["ok"] is False
    assert aggregate["valid_summary_count"] == 0
    assert aggregate["invalid_summary_count"] == 1
    assert aggregate["failed"] == 1
    assert aggregate["entries"] == [
        {
            "index": 0,
            "schema_ok": False,
            "verification_ok": False,
            "error": "summary_required_keys_missing",
            "validation": {
                "ok": False,
                "error": "summary_required_keys_missing",
                "missing_keys": ["summary_format_version"],
            },
        }
    ]


def test_phase13_81_aggregate_writer_persists_deterministic_json(tmp_path: Path) -> None:
    aggregate = verify_cli.aggregate_state_zip_verification_summaries(
        [
            {
                "summary_format_version": verify_cli.STATE_ZIP_VERIFY_SUMMARY_VERSION,
                "ok": True,
                "checkpoint_count": 1,
                "restored_turns": [1],
            }
        ]
    )

    path = verify_cli.write_state_zip_verification_aggregate(
        aggregate=aggregate,
        aggregate_path=tmp_path / "nested" / "state-zip-aggregate.json",
    )

    assert path == tmp_path / "nested" / "state-zip-aggregate.json"
    assert json.loads(path.read_text(encoding="utf-8")) == aggregate


def test_phase13_81_aggregate_writer_rejects_bad_version(tmp_path: Path) -> None:
    try:
        verify_cli.write_state_zip_verification_aggregate(
            aggregate={"aggregate_format_version": "old", "ok": True},
            aggregate_path=tmp_path / "aggregate.json",
        )
    except ValueError as exc:
        assert str(exc) == "aggregate_format_version_mismatch"
    else:
        raise AssertionError("expected ValueError")


def test_phase13_81_aggregate_writer_requires_bool_ok(tmp_path: Path) -> None:
    try:
        verify_cli.write_state_zip_verification_aggregate(
            aggregate={"aggregate_format_version": verify_cli.STATE_ZIP_VERIFY_AGGREGATE_VERSION, "ok": "true"},
            aggregate_path=tmp_path / "aggregate.json",
        )
    except ValueError as exc:
        assert str(exc) == "aggregate_ok_not_bool"
    else:
        raise AssertionError("expected ValueError")
