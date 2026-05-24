from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from app.rpg.session.artifact_manifest_digest import (
    DIGEST_FILE,
    build_artifact_manifest_digest,
    write_artifact_manifest_digest,
)


EMBEDDED = {
    "quality-gate-summary.json": {"ok": True},
    "survival-exit-criteria-summary.json": {"ok": True},
    "transcript-payload-budget-summary.json": {"ok": True},
    "long-run-dry-run-projection-summary.json": {"ok": True},
    "content-exhaustion-forecast-summary.json": {"ok": True},
    "npc-agency-schedule-summary.json": {"ok": True},
    "economy-resource-pressure-summary.json": {"ok": True},
    "readiness-report-projection-summary.json": {"ok": True},
}


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _manifest() -> dict:
    return {
        "format_version": "bundle_abcd_artifact_manifest_hard_finalized_v1",
        "source": "test_manifest",
        "ok": True,
        "hard_finalized": True,
        "final_write_after_all_wrappers": True,
        "embedded_artifacts": dict(EMBEDDED),
    }


def _seed_result_dir(root: Path) -> None:
    root.mkdir(parents=True)
    manifest = _manifest()
    _write_json(root / "artifact-manifest.json", manifest)
    _write_json(root / "autoplay-health.json", {"ok": True})
    _write_json(root / "summary.json", {"ok": True, "turns_executed": 20})
    _write_json(root / "hundred-turn-evaluation.json", {"ok": True})
    _write_json(root / "readiness-report-projection-summary.json", {"ok": True})
    zip_path = root.with_name(root.name[: -len("-unzipped")] + ".zip")
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("artifact-manifest.json", json.dumps(manifest, indent=2) + "\n")
        zf.writestr("autoplay-health.json", json.dumps({"ok": True}))
        zf.writestr("summary.json", json.dumps({"ok": True}))
        zf.writestr("hundred-turn-evaluation.json", json.dumps({"ok": True}))
        zf.writestr("readiness-report-projection-summary.json", json.dumps({"ok": True}))


def test_artifact_manifest_digest_reports_review_safe_manifest_proof(tmp_path) -> None:
    result_dir = tmp_path / "autoplay-campaign-results-unzipped"
    _seed_result_dir(result_dir)
    payload = (result_dir / "artifact-manifest.json").read_bytes()

    digest = build_artifact_manifest_digest(result_dir)

    assert digest["ok"] is True
    assert digest["manifest_exists"] is True
    assert digest["manifest_byte_size"] == len(payload)
    assert digest["manifest_sha256"] == hashlib.sha256(payload).hexdigest()
    assert digest["manifest_format_version"] == "bundle_abcd_artifact_manifest_hard_finalized_v1"
    assert digest["manifest_hard_finalized"] is True
    assert digest["embedded_artifact_count"] == len(EMBEDDED)
    assert digest["invariant_ok"] is True
    assert digest["zip_manifest_valid_count"] >= 1
    assert digest["zip_manifest_digests"][0]["ok"] is True


def test_write_artifact_manifest_digest_creates_small_review_artifact(tmp_path) -> None:
    result_dir = tmp_path / "autoplay-campaign-results-unzipped"
    _seed_result_dir(result_dir)

    result = write_artifact_manifest_digest(result_dir)

    assert result["applied"] is True
    assert result["ok"] is True
    path = result_dir / DIGEST_FILE
    assert path.exists()
    digest = json.loads(path.read_text(encoding="utf-8"))
    assert digest["ok"] is True
    assert digest["review_note"].startswith("Use this small digest")
    assert digest["embedded_artifact_names"] == sorted(EMBEDDED)


def test_artifact_manifest_digest_fails_when_manifest_is_empty(tmp_path) -> None:
    result_dir = tmp_path / "autoplay-campaign-results-unzipped"
    result_dir.mkdir(parents=True)
    (result_dir / "artifact-manifest.json").write_text("", encoding="utf-8")
    _write_json(result_dir / "autoplay-health.json", {"ok": True})
    _write_json(result_dir / "summary.json", {"ok": True})
    _write_json(result_dir / "hundred-turn-evaluation.json", {"ok": True})
    _write_json(result_dir / "readiness-report-projection-summary.json", {"ok": True})

    digest = build_artifact_manifest_digest(result_dir)

    assert digest["ok"] is False
    assert digest["manifest_byte_size"] == 0
    assert digest["embedded_artifact_count"] == 0
    assert digest["invariant_ok"] is False
