from __future__ import annotations

import json
import sqlite3

from scripts import restore_legacy_character_avatar_pack


def test_legacy_avatar_pack_extraction_preserves_version_and_asset_links(tmp_path) -> None:
    database = tmp_path / "characters.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE character_avatar_packs (
                character_id TEXT PRIMARY KEY,
                version INTEGER NOT NULL,
                render_mode TEXT NOT NULL,
                renderer TEXT NOT NULL,
                rig_asset_id TEXT,
                base_asset_id TEXT,
                mouth_frames_json TEXT NOT NULL,
                blink_frames_json TEXT NOT NULL,
                expression_frames_json TEXT NOT NULL,
                outfit_frames_json TEXT NOT NULL,
                background_asset_ids_json TEXT NOT NULL,
                active_outfit TEXT,
                active_background TEXT,
                mouth_anchor_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO character_avatar_packs VALUES (
                'maya', 2, 'viseme', 'sprite', NULL, 'image:base',
                ?, ?, ?, '{}', '{}', NULL, NULL, '{}',
                '2026-07-01T00:00:00+00:00', '2026-07-02T00:00:00+00:00'
            )
            """,
            (
                json.dumps({"closed": "image:base", "A": "image:a"}),
                json.dumps({"closed": "image:blink"}),
                json.dumps({"happy": "image:happy"}),
            ),
        )

    pack = restore_legacy_character_avatar_pack._legacy_pack(database, "maya")

    assert pack.version == 2
    assert pack.render_mode == "viseme"
    assert pack.base_asset_id == "image:base"
    assert restore_legacy_character_avatar_pack._asset_ids(pack) == [
        "image:a",
        "image:base",
        "image:blink",
        "image:happy",
    ]
