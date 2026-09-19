"""Immutable render cache lookup with metadata and blob attestation."""
from __future__ import annotations

from typing import Any

from app.persistence.blob_store import BlobIntegrityError, LocalBlobStore
from app.persistence.tenant import TenantContext


def valid_render_blob(render: dict[str, Any], asset: dict[str, Any], blobs: LocalBlobStore) -> bool:
    if render["audio_asset_id"] != asset["id"]:
        return False
    if asset["module"] != "audiobook" or asset["lifecycle_status"] != "active":
        return False
    if asset["checksum_sha256"] != render["audio_checksum"]:
        return False
    if asset["storage_provider"] != blobs.provider:
        return False
    try:
        content = blobs.read_bytes(
            asset["storage_key"], expected_checksum=render["audio_checksum"],
        )
    except (FileNotFoundError, BlobIntegrityError, OSError):
        return False
    return bool(content)


def find_valid_render(
    connection: Any, context: TenantContext, blobs: LocalBlobStore, render_key: str,
) -> dict[str, Any] | None:
    rows = connection.execute(
        """
        SELECT r.id, r.audio_asset_id, r.audio_checksum, r.duration_seconds,
               r.sample_rate, a.id, a.module, a.lifecycle_status,
               a.checksum_sha256, a.storage_provider, a.storage_key
          FROM omnix_audiobook_renders AS r
          JOIN omnix_assets AS a ON a.id = r.audio_asset_id AND a.workspace_id = r.workspace_id
         WHERE r.workspace_id = %s AND r.render_key = %s AND r.status = 'completed'
         ORDER BY r.created_at DESC, r.id DESC
        """, (context.workspace_id, render_key),
    ).fetchall()
    for row in rows:
        render = {"id": str(row[0]), "audio_asset_id": str(row[1]),
                  "audio_checksum": str(row[2]), "duration_seconds": float(row[3]),
                  "sample_rate": int(row[4]), "render_key": render_key}
        asset = {"id": str(row[5]), "module": str(row[6]),
                 "lifecycle_status": str(row[7]), "checksum_sha256": str(row[8]),
                 "storage_provider": str(row[9]), "storage_key": str(row[10])}
        if valid_render_blob(render, asset, blobs):
            return render
    return None
