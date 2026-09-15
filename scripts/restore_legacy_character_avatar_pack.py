"""Restore one verified legacy Character avatar-pack linkage into PostgreSQL."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

from app.characters.avatar_models import CharacterAvatarPack


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy-character-db", type=Path, required=True)
    parser.add_argument("--character-id", required=True)
    parser.add_argument("--blob-root", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    return parser


def _legacy_pack(database_path: Path, character_id: str) -> CharacterAvatarPack:
    uri = database_path.resolve().as_uri() + "?mode=ro&immutable=1"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM character_avatar_packs WHERE character_id = ?",
            (character_id,),
        ).fetchone()
    if row is None:
        raise RuntimeError(f"legacy avatar pack not found: {character_id}")
    return CharacterAvatarPack(
        character_id=str(row["character_id"]),
        version=int(row["version"]),
        render_mode=str(row["render_mode"]),
        renderer=str(row["renderer"]),
        rig_asset_id=row["rig_asset_id"],
        base_asset_id=row["base_asset_id"],
        mouth_frames=json.loads(row["mouth_frames_json"]),
        blink_frames=json.loads(row["blink_frames_json"]),
        expression_frames=json.loads(row["expression_frames_json"]),
        outfit_frames=json.loads(row["outfit_frames_json"]),
        background_asset_ids=json.loads(row["background_asset_ids_json"]),
        active_outfit=row["active_outfit"],
        active_background=row["active_background"],
        mouth_anchor=json.loads(row["mouth_anchor_json"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _asset_ids(pack: CharacterAvatarPack) -> list[str]:
    values = [
        pack.rig_asset_id,
        pack.base_asset_id,
        *pack.mouth_frames.values(),
        *pack.blink_frames.values(),
        *pack.expression_frames.values(),
        *pack.outfit_frames.values(),
        *pack.background_asset_ids.values(),
    ]
    return sorted({str(value) for value in values if value})


def _verify_assets(repository: Any, blob_store: Any, pack: CharacterAvatarPack) -> dict[str, int]:
    asset_ids = _asset_ids(pack)
    placeholders = ", ".join(["%s"] * len(asset_ids))
    with repository.database.connection() as connection:
        rows = connection.execute(
            f"""
            SELECT id, storage_key, byte_size, checksum_sha256
              FROM omnix_assets
             WHERE workspace_id = %s AND lifecycle_status = 'active'
               AND id IN ({placeholders})
            """,
            (repository.context.workspace_id, *asset_ids),
        ).fetchall()
    records = {str(row[0]): row for row in rows}
    missing_metadata = sorted(set(asset_ids) - set(records))
    if missing_metadata:
        raise RuntimeError(
            f"avatar assets missing from PostgreSQL: {len(missing_metadata)}"
        )
    for asset_id in asset_ids:
        row = records[asset_id]
        content = blob_store.read_bytes(str(row[1]), expected_checksum=str(row[3]))
        if len(content) != int(row[2]):
            raise RuntimeError(f"avatar asset size mismatch: {asset_id}")
    return {"asset_references": len(asset_ids), "verified_blobs": len(asset_ids)}


def main() -> int:
    args = build_parser().parse_args()
    pack = _legacy_pack(args.legacy_character_db, args.character_id)

    from app.persistence.avatar_compat import PostgresCharacterAvatarRepositoryAdapter
    from app.persistence.blob_store import LocalBlobStore
    from app.persistence.startup import bootstrap_postgresql_runtime

    bootstrap_postgresql_runtime()
    repository = PostgresCharacterAvatarRepositoryAdapter()
    blob_store = LocalBlobStore(args.blob_root)
    verification = _verify_assets(repository, blob_store, pack)
    current = repository.get(pack.character_id)
    if current is not None and current != pack:
        raise RuntimeError(f"non-identical avatar pack already exists: {pack.character_id}")
    action = "already_present" if current == pack else "would_import"
    if args.apply and current is None:
        repository.import_pack(pack)
        action = "imported"
    report = {
        "ok": True,
        "applied": bool(args.apply),
        "action": action,
        "character_id": pack.character_id,
        "pack_version": pack.version,
        "render_mode": pack.render_mode,
        **verification,
    }
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
