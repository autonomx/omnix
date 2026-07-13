from __future__ import annotations

import hashlib

import pytest

from app.persistence.blob_store import LocalBlobStore
from app.persistence.coordinated_recovery import (
    CoordinatedRecoveryError,
    CoordinatedRecoveryRepository,
)


class _Result:
    def __init__(self, row=None, rows=None, *, rowcount: int = 1) -> None:
        self._row = row
        self._rows = list(rows or [])
        self.rowcount = rowcount

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class _RecoveryConnection:
    def __init__(self, *, live_root, content: bytes = b"recovery-content") -> None:
        self.live_root = str(live_root)
        self.content = content
        self.generation_id: str | None = None
        self.status = "preparing"
        self.manifest_hash: str | None = None
        self.asset_count = 0
        self.total_blob_bytes = 0
        self.manifest: list[tuple] = []

    def execute(self, sql: str, parameters=None):
        normalized = " ".join(sql.split())
        parameters = tuple(parameters or ())
        if normalized.startswith("INSERT INTO omnix_backup_generations"):
            self.generation_id = str(parameters[0])
            self.live_root = str(parameters[3])
            return _Result()
        if normalized.startswith("SELECT status FROM omnix_backup_generations"):
            return _Result((self.status,))
        if normalized.startswith("SELECT id, workspace_id, storage_provider"):
            checksum = hashlib.sha256(self.content).hexdigest()
            return _Result(
                rows=[
                    (
                        "asset:test",
                        "workspace:test",
                        "local-filesystem",
                        "assets/test.bin",
                        checksum,
                        len(self.content),
                        "active",
                    )
                ]
            )
        if normalized.startswith("INSERT INTO omnix_backup_blob_manifest"):
            self.manifest.append(parameters)
            return _Result()
        if normalized.startswith("UPDATE omnix_backup_generations SET status = 'manifested'"):
            self.status = "manifested"
            self.manifest_hash = str(parameters[0])
            self.asset_count = int(parameters[1])
            self.total_blob_bytes = int(parameters[2])
            return _Result()
        if normalized.startswith("UPDATE omnix_assets"):
            return _Result()
        if normalized.startswith("SELECT status, blob_root FROM omnix_backup_generations"):
            return _Result((self.status, self.live_root))
        if normalized.startswith("SELECT asset_id, storage_key, checksum_sha256, byte_size"):
            return _Result(
                rows=[(row[1], row[4], row[5], row[6]) for row in self.manifest]
            )
        if normalized.startswith("UPDATE omnix_backup_generations SET metadata"):
            return _Result()
        if normalized.startswith("UPDATE omnix_backup_generations SET status = 'database_backed_up'"):
            if self.status != "manifested":
                return _Result(rowcount=0)
            self.status = "database_backed_up"
            return _Result(rowcount=1)
        if normalized.startswith("SELECT status, manifest_hash, blob_root"):
            return _Result(
                (
                    self.status,
                    self.manifest_hash,
                    self.live_root,
                    self.asset_count,
                    self.total_blob_bytes,
                )
            )
        if normalized.startswith("SELECT asset_id, workspace_id, storage_provider, storage_key"):
            return _Result(
                rows=[
                    (row[1], row[2], row[3], row[4], row[5], row[6], row[7])
                    for row in self.manifest
                ]
            )
        if normalized.startswith("UPDATE omnix_backup_blob_manifest"):
            return _Result()
        if normalized.startswith("UPDATE omnix_backup_generations SET status = %s"):
            self.status = str(parameters[0])
            return _Result()
        raise AssertionError(f"unexpected SQL: {normalized}")


def _prepared_recovery(tmp_path):
    live = LocalBlobStore(tmp_path / "live")
    content = b"recovery-content"
    live.put_bytes("assets/test.bin", content)
    connection = _RecoveryConnection(live_root=live.root, content=content)
    repository = CoordinatedRecoveryRepository(connection)
    generation_id = repository.create_generation(
        software_revision="test-head",
        schema_version="0016_data_lifecycle_capacity",
        blob_root=live.root,
        operator_note="provider-free test",
    )
    manifest = repository.capture_manifest(generation_id)
    return repository, connection, generation_id, live, manifest


def test_generation_manifest_copy_and_restored_verification(tmp_path) -> None:
    repository, connection, generation_id, live, manifest = _prepared_recovery(tmp_path)
    backup = LocalBlobStore(tmp_path / "backup")
    copied = repository.copy_manifested_blobs(
        generation_id,
        source=live,
        destination=backup,
    )
    repository.record_database_backup(generation_id, "backups/after-import.dump")
    restored = LocalBlobStore(tmp_path / "restored")
    restored.put_bytes("assets/test.bin", backup.read_bytes("assets/test.bin"))
    result = repository.verify_blobs(
        generation_id,
        restored,
        database_restore_verified=True,
        migrations_verified=True,
        smoke_checks_verified=True,
    )
    assert manifest["asset_count"] == 1
    assert copied["asset_count"] == 1
    assert result["ok"] is True
    assert result["manifest_matches"] is True
    assert connection.status == "verified"


def test_original_blob_root_cannot_be_used_as_restore_evidence(tmp_path) -> None:
    repository, _, generation_id, live, _ = _prepared_recovery(tmp_path)
    repository.record_database_backup(generation_id, "backups/test.dump")
    with pytest.raises(CoordinatedRecoveryError, match="restored BlobStore root"):
        repository.verify_blobs(
            generation_id,
            live,
            database_restore_verified=True,
            migrations_verified=True,
            smoke_checks_verified=True,
        )


def test_failed_database_restore_cannot_verify_generation(tmp_path) -> None:
    repository, _, generation_id, _, _ = _prepared_recovery(tmp_path)
    repository.record_database_backup(generation_id, "backups/test.dump")
    with pytest.raises(CoordinatedRecoveryError, match="PostgreSQL restore"):
        repository.verify_blobs(
            generation_id,
            LocalBlobStore(tmp_path / "restored"),
            database_restore_verified=False,
            migrations_verified=True,
            smoke_checks_verified=True,
        )


@pytest.mark.parametrize("failure", ["missing", "mismatched"])
def test_missing_and_mismatched_restored_blobs_fail(tmp_path, failure: str) -> None:
    repository, connection, generation_id, _, _ = _prepared_recovery(tmp_path)
    repository.record_database_backup(generation_id, "backups/test.dump")
    restored = LocalBlobStore(tmp_path / "restored")
    if failure == "mismatched":
        restored.put_bytes("assets/test.bin", b"wrong-content")
    result = repository.verify_blobs(
        generation_id,
        restored,
        database_restore_verified=True,
        migrations_verified=True,
        smoke_checks_verified=True,
    )
    assert result["ok"] is False
    assert result[failure] == ["asset:test"]
    assert connection.status == "failed"


def test_database_backup_reference_rejects_credentials(tmp_path) -> None:
    repository, _, generation_id, _, _ = _prepared_recovery(tmp_path)
    with pytest.raises(CoordinatedRecoveryError, match="credential"):
        repository.record_database_backup(
            generation_id,
            "postgresql://user:password@localhost/omnix",
        )
