from __future__ import annotations

import hashlib
import json
from pathlib import Path


_FRAGMENT = (
    Path(__file__).resolve().parent
    / "autoplay_llm_campaign_parts"
    / "zz_bundle_y_release_candidate_artifact_index.pyfrag"
)


def _load_bundle_y_namespace():
    namespace = {"__name__": "_bundle_y_release_candidate_artifact_index_test"}
    exec(compile(_FRAGMENT.read_text(encoding="utf-8"), str(_FRAGMENT), "exec"), namespace, namespace)
    return namespace


def _write_archive_ready_files(tmp_path: Path):
    payloads = {
        "one-thousand-turn-release-candidate-handoff-manifest.json": {"ok": True, "release_candidate_handoff_ready": True},
        "one-thousand-turn-release-candidate-handoff-dashboard-summary.json": {"ok": True, "status_label": "Handoff Ready"},
        "one-thousand-turn-release-candidate-runbook-summary.json": {"ok": True, "runbook_ready": True},
    }
    for name, payload in payloads.items():
        (tmp_path / name).write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    (tmp_path / "one-thousand-turn-release-candidate-runbook.md").write_text(
        "# 1000-Turn Release Candidate Runbook\n",
        encoding="utf-8",
    )
    (tmp_path / "autoplay-campaign-report.html").write_text("<html>report</html>", encoding="utf-8")
    (tmp_path / "autoplay-campaign-results.zip").write_bytes(b"PK\x03\x04fake")


def test_bundle_y_file_entry_records_presence_size_and_sha256(tmp_path):
    namespace = _load_bundle_y_namespace()
    target = tmp_path / "one-thousand-turn-release-candidate-runbook.md"
    target.write_text("hello runbook", encoding="utf-8")

    entry = namespace["_bundle_y_file_entry"](tmp_path, target.name)

    assert entry["file"] == target.name
    assert entry["present"] is True
    assert entry["size_bytes"] == len("hello runbook".encode("utf-8"))
    assert entry["sha256"] == hashlib.sha256(b"hello runbook").hexdigest()
    assert entry["required_for_archive"] is True


def test_bundle_y_artifact_index_ready_when_required_and_product_artifacts_exist(tmp_path):
    namespace = _load_bundle_y_namespace()
    _write_archive_ready_files(tmp_path)

    index = namespace["_bundle_y_build_artifact_index"](tmp_path)

    assert index["format_version"] == "bundle_y_release_candidate_artifact_index_v1"
    assert index["source"] == "bundle_y_release_candidate_artifact_index"
    assert index["ok"] is True
    assert index["advisory_only"] is True
    assert index["archive_index_ready"] is True
    assert index["advisory_failures"] == []
    assert index["checks"]["runbook_summary_ready"] is True
    assert index["checks"]["required_archive_artifacts_present"] is True
    assert index["checks"]["at_least_one_product_artifact_present"] is True
    assert index["checks"]["archive_digest_available"] is True
    assert index["metrics"]["missing_required_archive_file_count"] == 0
    assert index["archive_digest_sha256"]
    tracked = {entry["file"]: entry for entry in index["tracked_files"]}
    assert tracked["one-thousand-turn-release-candidate-runbook.md"]["present"] is True
    assert tracked["autoplay-campaign-results.zip"]["present"] is True
    assert index["recommended_next_step"] == "archive_release_candidate_artifact_index"


def test_bundle_y_artifact_index_reports_missing_required_and_product_artifacts(tmp_path):
    namespace = _load_bundle_y_namespace()
    (tmp_path / "one-thousand-turn-release-candidate-runbook-summary.json").write_text(
        json.dumps({"ok": False, "runbook_ready": False}),
        encoding="utf-8",
    )

    index = namespace["_bundle_y_build_artifact_index"](tmp_path)

    assert index["ok"] is False
    assert index["archive_index_ready"] is False
    assert "runbook_summary_ready" in index["advisory_failures"]
    assert "required_archive_artifacts_present" in index["advisory_failures"]
    assert "at_least_one_product_artifact_present" in index["advisory_failures"]
    assert index["metrics"]["missing_required_archive_file_count"] > 0
    assert "one-thousand-turn-release-candidate-runbook.md" in index["missing_required_archive_artifacts"]
    assert index["recommended_next_step"] == "complete_release_candidate_archive_artifacts"


def test_bundle_y_writes_index_when_tracked_artifacts_are_exported(tmp_path):
    namespace = _load_bundle_y_namespace()
    original_write_text = namespace["_BUNDLE_Y_ORIGINAL_PATH_WRITE_TEXT"]
    try:
        _write_archive_ready_files(tmp_path)

        index_path = tmp_path / "one-thousand-turn-release-candidate-artifact-index.json"
        assert index_path.exists()
        index = json.loads(index_path.read_text(encoding="utf-8"))
        assert index["ok"] is True
        assert index["archive_index_ready"] is True
        assert index["archive_digest_sha256"]
        assert index["metrics"]["present_tracked_file_count"] >= 4
        assert index["recommended_next_step"] == "archive_release_candidate_artifact_index"
    finally:
        Path.write_text = original_write_text
