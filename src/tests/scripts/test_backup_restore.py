"""Backup manifest checks and restore safety (WP-10.7)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))
backup_omnix = importlib.import_module("backup_omnix")
spec = importlib.util.spec_from_file_location("restore_rehearsal", SCRIPTS / "restore_rehearsal.py")
rehearsal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rehearsal)


@pytest.mark.parametrize("url", [
    "postgresql://omnix:omnix@127.0.0.1:5432/omnix",
    "postgresql://omnix:omnix@db.example.test:5432/production",
])
def test_the_rehearsal_refuses_a_database_that_is_not_disposable(url) -> None:
    with pytest.raises(SystemExit, match="refusing to restore"):
        rehearsal.require_disposable(url)


def test_disposable_names_are_accepted() -> None:
    for name in ("omnix_restore_rehearsal", "omnix_test", "omnix_bench"):
        rehearsal.require_disposable(f"postgresql://omnix@127.0.0.1/{name}")


def _backup(tmp_path: Path) -> tuple[Path, dict]:
    blobs = tmp_path / "blobs"
    (blobs / "ab").mkdir(parents=True)
    for index in range(3):
        (blobs / "ab" / f"blob{index}").write_bytes(bytes([index]) * 100)
    output = tmp_path / "backup"
    output.mkdir()
    (output / "database.dump").write_bytes(b"dump")
    manifest = {"blobs": backup_omnix.archive_blobs(blobs, output / "blobs.tar.gz")}
    manifest["files"] = {path.name: {"sha256": backup_omnix.sha256_file(path)} for path in output.iterdir()}
    return output, manifest


def test_a_tampered_backup_file_is_detected(tmp_path: Path) -> None:
    output, manifest = _backup(tmp_path)
    rehearsal.verify_files(output, manifest)

    (output / "database.dump").write_bytes(b"changed")

    with pytest.raises(RuntimeError, match="does not match its manifest checksum: database.dump"):
        rehearsal.verify_files(output, manifest)


def test_blobs_are_restored_and_their_sample_checked(tmp_path: Path) -> None:
    output, manifest = _backup(tmp_path)

    restored = rehearsal.restore_blobs(output, manifest, tmp_path / "restored")

    assert restored == {"files": 3, "sample_checked": 3}
    manifest["blobs"]["sample"]["ab/blob0"] = "0" * 64
    with pytest.raises(RuntimeError, match="blob restore mismatch"):
        rehearsal.restore_blobs(output, manifest, tmp_path / "restored-again")


def test_the_s3_backend_is_not_copied(tmp_path: Path) -> None:
    assert "skipped" in rehearsal.restore_blobs(tmp_path, {"blobs": {"backend": "s3"}}, tmp_path / "unused")


def test_the_manifest_is_json_with_checksums(tmp_path: Path) -> None:
    output, manifest = _backup(tmp_path)

    assert json.loads(json.dumps(manifest))["blobs"]["files"] == 3
    assert set(manifest["files"]) == {"database.dump", "blobs.tar.gz"}
