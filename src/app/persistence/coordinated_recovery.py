from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .blob_store import LocalBlobStore


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class CoordinatedRecoveryError(RuntimeError):
    pass


class CoordinatedRecoveryRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def create_generation(
        self,
        *,
        software_revision: str,
        schema_version: str,
        blob_root: str | Path,
        retention_days: int = 30,
        rpo_seconds: int = 86_400,
        rto_seconds: int = 3_600,
        encryption_required: bool = True,
    ) -> str:
        generation_id = f"backup:{uuid.uuid4().hex}"
        self.connection.execute(
            """
            INSERT INTO omnix_backup_generations (
                id, software_revision, schema_version, blob_root,
                retention_until, rpo_seconds, rto_seconds, encryption_required
            ) VALUES (
                %s, %s, %s, %s,
                CURRENT_TIMESTAMP + (%s * INTERVAL '1 day'), %s, %s, %s
            )
            """,
            (
                generation_id,
                software_revision,
                schema_version,
                str(Path(blob_root)),
                max(1, int(retention_days)),
                max(0, int(rpo_seconds)),
                max(0, int(rto_seconds)),
                bool(encryption_required),
            ),
        )
        return generation_id

    def capture_manifest(self, generation_id: str, *, deletion_grace_days: int = 31) -> dict[str, Any]:
        status = self.connection.execute(
            "SELECT status FROM omnix_backup_generations WHERE id = %s FOR UPDATE",
            (generation_id,),
        ).fetchone()
        if status is None or str(status[0]) != "preparing":
            raise CoordinatedRecoveryError("backup generation is not preparing")
        rows = self.connection.execute(
            """
            SELECT id, workspace_id, storage_provider, storage_key,
                   checksum_sha256, byte_size, lifecycle_status
              FROM omnix_assets
             WHERE lifecycle_status NOT IN ('deleted', 'purged')
             ORDER BY workspace_id, id
            """
        ).fetchall()
        manifest = [
            {
                "asset_id": str(row[0]),
                "workspace_id": str(row[1]),
                "storage_provider": str(row[2]),
                "storage_key": str(row[3]),
                "checksum_sha256": str(row[4]),
                "byte_size": int(row[5]),
                "lifecycle_status": str(row[6]),
            }
            for row in rows
        ]
        for item in manifest:
            self.connection.execute(
                """
                INSERT INTO omnix_backup_blob_manifest (
                    generation_id, asset_id, workspace_id, storage_provider,
                    storage_key, checksum_sha256, byte_size, lifecycle_status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    generation_id,
                    item["asset_id"],
                    item["workspace_id"],
                    item["storage_provider"],
                    item["storage_key"],
                    item["checksum_sha256"],
                    item["byte_size"],
                    item["lifecycle_status"],
                ),
            )
        manifest_hash = hashlib.sha256(_canonical(manifest).encode("utf-8")).hexdigest()
        total_bytes = sum(item["byte_size"] for item in manifest)
        self.connection.execute(
            """
            UPDATE omnix_backup_generations
               SET status = 'manifested', manifest_hash = %s,
                   asset_count = %s, total_blob_bytes = %s,
                   manifested_at = CURRENT_TIMESTAMP
             WHERE id = %s
            """,
            (manifest_hash, len(manifest), total_bytes, generation_id),
        )
        self.connection.execute(
            """
            UPDATE omnix_assets
               SET deletion_not_before = GREATEST(
                   COALESCE(deletion_not_before, CURRENT_TIMESTAMP),
                   CURRENT_TIMESTAMP + (%s * INTERVAL '1 day')
               )
             WHERE id IN (
                 SELECT asset_id FROM omnix_backup_blob_manifest WHERE generation_id = %s
             )
            """,
            (max(1, int(deletion_grace_days)), generation_id),
        )
        return {
            "generation_id": generation_id,
            "manifest_hash": manifest_hash,
            "asset_count": len(manifest),
            "total_blob_bytes": total_bytes,
        }

    def record_database_backup(self, generation_id: str, reference: str) -> None:
        cursor = self.connection.execute(
            """
            UPDATE omnix_backup_generations
               SET status = 'database_backed_up', database_backup_reference = %s
             WHERE id = %s AND status = 'manifested'
            """,
            (reference, generation_id),
        )
        if cursor.rowcount != 1:
            raise CoordinatedRecoveryError("manifest must be captured before database backup")

    def verify_blobs(self, generation_id: str, blob_store: LocalBlobStore) -> dict[str, Any]:
        generation = self.connection.execute(
            "SELECT status, manifest_hash FROM omnix_backup_generations WHERE id = %s FOR UPDATE",
            (generation_id,),
        ).fetchone()
        if generation is None or str(generation[0]) != "database_backed_up":
            raise CoordinatedRecoveryError("database backup must be recorded before verification")
        rows = self.connection.execute(
            """
            SELECT asset_id, storage_key, checksum_sha256, byte_size
              FROM omnix_backup_blob_manifest
             WHERE generation_id = %s
             ORDER BY workspace_id, asset_id
            """,
            (generation_id,),
        ).fetchall()
        missing: list[str] = []
        mismatched: list[str] = []
        for row in rows:
            asset_id, storage_key, checksum, byte_size = str(row[0]), str(row[1]), str(row[2]), int(row[3])
            error: str | None = None
            try:
                content = blob_store.read_bytes(storage_key, expected_checksum=checksum)
                if len(content) != byte_size:
                    error = f"size mismatch: expected {byte_size}, got {len(content)}"
                    mismatched.append(asset_id)
            except FileNotFoundError:
                error = "missing"
                missing.append(asset_id)
            except Exception as exc:
                error = str(exc)[:1000]
                mismatched.append(asset_id)
            self.connection.execute(
                """
                UPDATE omnix_backup_blob_manifest
                   SET verified = %s, verification_error = %s
                 WHERE generation_id = %s AND asset_id = %s
                """,
                (error is None, error, generation_id, asset_id),
            )
        ok = not missing and not mismatched
        self.connection.execute(
            """
            UPDATE omnix_backup_generations
               SET status = %s, verified_at = CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE NULL END,
                   failure = CASE WHEN %s THEN NULL ELSE %s::jsonb END
             WHERE id = %s
            """,
            (
                "verified" if ok else "failed",
                ok,
                ok,
                _canonical({"missing": missing, "mismatched": mismatched}),
                generation_id,
            ),
        )
        return {"ok": ok, "missing": missing, "mismatched": mismatched, "checked": len(rows)}
