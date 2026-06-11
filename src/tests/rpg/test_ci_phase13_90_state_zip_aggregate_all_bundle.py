from __future__ import annotations

import json
import zipfile
from pathlib import Path

from tests.rpg import interactive_cli_state_zip_aggregate_bundle as all_bundle
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


def test_phase13_90_all_bundle_writes_and_verifies_round_trip(tmp_path: Path) -> None:
    aggregate_path = _write_json(tmp_path / "state-zip-aggregate.json", _aggregate_payload())
    bundle_path = tmp_path / "nested" / "state-zip-aggregate-all-bundle.zip"

    write_result = all_bundle.write_state_zip_aggregate_all_bundle(
        aggregate_path=aggregate_path,
        bundle_zip_path=bundle_path,
    )

    assert write_result["ok"] is True
    assert write_result["bundle_path"] == str(bundle_path)
    assert write_result["manifest"] == {
        "format_version": all_bundle.STATE_ZIP_AGGREGATE_ALL_BUNDLE_VERSION,
        "aggregate_entry": all_bundle.STATE_ZIP_AGGREGATE_ALL_BUNDLE_AGGREGATE,
        "status_marker_entry": all_bundle.STATE_ZIP_AGGREGATE_ALL_BUNDLE_MARKER,
        "bundle_summary_entry": all_bundle.STATE_ZIP_AGGREGATE_ALL_BUNDLE_SUMMARY,
        "aggregate_format_version": verify_cli.STATE_ZIP_VERIFY_AGGREGATE_VERSION,
        "aggregate_ok": True,
        "summary_count": 1,
        "failed": 0,
        "status_marker": "[INTERACTIVE_CLI_STATE_ZIP_AGGREGATE_READ] ok=true aggregate_ok=true summary_count=1 failed=0 error=none",
        "bundle_summary_ok": True,
        "entries": [
            all_bundle.STATE_ZIP_AGGREGATE_ALL_BUNDLE_MANIFEST,
            all_bundle.STATE_ZIP_AGGREGATE_ALL_BUNDLE_AGGREGATE,
            all_bundle.STATE_ZIP_AGGREGATE_ALL_BUNDLE_MARKER,
            all_bundle.STATE_ZIP_AGGREGATE_ALL_BUNDLE_SUMMARY,
        ],
    }

    verify_result = all_bundle.verify_state_zip_aggregate_all_bundle(bundle_path)

    assert verify_result["ok"] is True
    assert verify_result["path"] == str(bundle_path)
    assert verify_result["aggregate"]["ok"] is True
    assert verify_result["marker_result"] == {
        "ok": True,
        "read_ok": True,
        "aggregate_ok": True,
        "summary_count": 1,
        "failed": 0,
        "read_error": "none",
    }
    assert verify_result["bundle_summary"]["ok"] is True


def test_phase13_90_all_bundle_rejects_missing_entries(tmp_path: Path) -> None:
    bundle_path = tmp_path / "broken.zip"
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(all_bundle.STATE_ZIP_AGGREGATE_ALL_BUNDLE_MANIFEST, "{}")

    assert all_bundle.verify_state_zip_aggregate_all_bundle(bundle_path) == {
        "ok": False,
        "error": "aggregate_all_bundle_entries_missing",
        "path": str(bundle_path),
        "missing_entries": [
            all_bundle.STATE_ZIP_AGGREGATE_ALL_BUNDLE_AGGREGATE,
            all_bundle.STATE_ZIP_AGGREGATE_ALL_BUNDLE_SUMMARY,
            all_bundle.STATE_ZIP_AGGREGATE_ALL_BUNDLE_MARKER,
        ],
    }


def test_phase13_90_all_bundle_rejects_bad_aggregate_payload(tmp_path: Path) -> None:
    bundle_path = tmp_path / "bad-aggregate.zip"
    marker = "[INTERACTIVE_CLI_STATE_ZIP_AGGREGATE_READ] ok=true aggregate_ok=true summary_count=1 failed=0 error=none"
    bundle_summary = {"ok": True}
    manifest = all_bundle.build_state_zip_aggregate_all_bundle_manifest(
        aggregate_payload={"aggregate_format_version": "old", "ok": True},
        status_marker=marker,
        bundle_summary=bundle_summary,
    )
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(all_bundle.STATE_ZIP_AGGREGATE_ALL_BUNDLE_MANIFEST, json.dumps(manifest))
        archive.writestr(
            all_bundle.STATE_ZIP_AGGREGATE_ALL_BUNDLE_AGGREGATE,
            json.dumps({"aggregate_format_version": "old", "ok": True}),
        )
        archive.writestr(all_bundle.STATE_ZIP_AGGREGATE_ALL_BUNDLE_MARKER, marker)
        archive.writestr(all_bundle.STATE_ZIP_AGGREGATE_ALL_BUNDLE_SUMMARY, json.dumps(bundle_summary))

    result = all_bundle.verify_state_zip_aggregate_all_bundle(bundle_path)

    assert result["ok"] is False
    assert result["error"] == "aggregate_all_bundle_aggregate_invalid"
    assert result["validation"]["error"] == "aggregate_format_version_mismatch"


def test_phase13_90_all_bundle_rejects_manifest_mismatch(tmp_path: Path) -> None:
    aggregate_path = _write_json(tmp_path / "state-zip-aggregate.json", _aggregate_payload())
    bundle_path = tmp_path / "state-zip-aggregate-all-bundle.zip"
    assert all_bundle.write_state_zip_aggregate_all_bundle(
        aggregate_path=aggregate_path,
        bundle_zip_path=bundle_path,
    )["ok"] is True

    with zipfile.ZipFile(bundle_path, "a", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            all_bundle.STATE_ZIP_AGGREGATE_ALL_BUNDLE_MANIFEST,
            json.dumps({"format_version": all_bundle.STATE_ZIP_AGGREGATE_ALL_BUNDLE_VERSION, "tampered": True}),
        )

    result = all_bundle.verify_state_zip_aggregate_all_bundle(bundle_path)

    assert result["ok"] is False
    assert result["error"] in {"aggregate_all_bundle_manifest_mismatch", "aggregate_all_bundle_manifest_invalid"}


def test_phase13_90_all_bundle_write_reports_aggregate_read_failure(tmp_path: Path) -> None:
    result = all_bundle.write_state_zip_aggregate_all_bundle(
        aggregate_path=tmp_path / "missing-aggregate.json",
        bundle_zip_path=tmp_path / "bundle.zip",
    )

    assert result["ok"] is False
    assert result["error"] == "aggregate_read_failed"
    assert result["read_result"]["error"] == "aggregate_file_missing"


def test_phase13_90_all_bundle_write_reports_marker_mismatch(tmp_path: Path) -> None:
    aggregate_path = _write_json(tmp_path / "state-zip-aggregate.json", _aggregate_payload(ok=False))
    bad_marker = "[INTERACTIVE_CLI_STATE_ZIP_AGGREGATE_READ] ok=true aggregate_ok=true summary_count=1 failed=0 error=none"

    result = all_bundle.write_state_zip_aggregate_all_bundle(
        aggregate_path=aggregate_path,
        bundle_zip_path=tmp_path / "bundle.zip",
        status_marker=bad_marker,
    )

    assert result["ok"] is False
    assert result["error"] == "aggregate_bundle_verification_failed"
    assert result["bundle_summary"]["error"] == "aggregate_read_marker_mismatch"


def test_phase13_91_all_bundle_write_cli_creates_bundle(tmp_path: Path, capsys) -> None:
    aggregate_path = _write_json(tmp_path / "state-zip-aggregate.json", _aggregate_payload())
    bundle_path = tmp_path / "cli" / "state-zip-aggregate-all-bundle.zip"

    assert all_bundle.main(["write", str(aggregate_path), str(bundle_path)]) == 0

    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert payload["ok"] is True
    assert payload["bundle_path"] == str(bundle_path)
    assert all_bundle.verify_state_zip_aggregate_all_bundle(bundle_path)["ok"] is True


def test_phase13_91_all_bundle_verify_cli_accepts_valid_bundle(tmp_path: Path, capsys) -> None:
    aggregate_path = _write_json(tmp_path / "state-zip-aggregate.json", _aggregate_payload())
    bundle_path = tmp_path / "state-zip-aggregate-all-bundle.zip"
    assert all_bundle.write_state_zip_aggregate_all_bundle(
        aggregate_path=aggregate_path,
        bundle_zip_path=bundle_path,
    )["ok"] is True

    assert all_bundle.main(["verify", str(bundle_path)]) == 0

    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert payload["ok"] is True
    assert payload["aggregate"]["ok"] is True


def test_phase13_91_all_bundle_cli_returns_one_for_invalid_inputs(tmp_path: Path, capsys) -> None:
    missing_aggregate = tmp_path / "missing-aggregate.json"
    bundle_path = tmp_path / "state-zip-aggregate-all-bundle.zip"

    assert all_bundle.main(["write", str(missing_aggregate), str(bundle_path)]) == 1
    write_output = capsys.readouterr()
    assert json.loads(write_output.out)["error"] == "aggregate_read_failed"

    assert all_bundle.main(["verify", str(tmp_path / "missing-bundle.zip")]) == 1
    verify_output = capsys.readouterr()
    assert json.loads(verify_output.out)["error"] == "aggregate_all_bundle_missing"


def test_phase13_91_all_bundle_write_cli_uses_supplied_marker(tmp_path: Path, capsys) -> None:
    aggregate_path = _write_json(tmp_path / "state-zip-aggregate.json", _aggregate_payload())
    bundle_path = tmp_path / "state-zip-aggregate-all-bundle.zip"
    marker = "[INTERACTIVE_CLI_STATE_ZIP_AGGREGATE_READ] ok=true aggregate_ok=true summary_count=1 failed=0 error=none"

    assert all_bundle.main(["write", str(aggregate_path), str(bundle_path), "--status-marker", marker]) == 0

    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert payload["manifest"]["status_marker"] == marker
