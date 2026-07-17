from __future__ import annotations

import base64
import hashlib
import zlib
from pathlib import Path

from app.rpg.worlds.world_bundle import parse_world_bundle_archive

BUNDLE_SHA256 = "9582c2ee7aecfb1d0890210bcd198baedfe4d1ef4ddfbadd6b5086a35f6eb944"
SAMPLE_DIR = (
    Path(__file__).resolve().parents[4]
    / "examples"
    / "rpg"
    / "world-bundles"
    / "aurelia-echoes-beyond-the-gate"
)


def _bundle_bytes() -> bytes:
    parts = sorted((SAMPLE_DIR / "bundle-parts").glob("*.b64"))
    assert len(parts) == 9
    return zlib.decompress(
        base64.b64decode(
            "".join(part.read_text(encoding="ascii").strip() for part in parts),
            validate=True,
        )
    )


def test_aurelia_sample_world_bundle_is_import_ready() -> None:
    content = _bundle_bytes()
    assert hashlib.sha256(content).hexdigest() == BUNDLE_SHA256

    parsed = parse_world_bundle_archive(content)
    payload = parsed.payload
    revision = payload.world_revisions[0]["document"]
    manifest = revision["entity_manifest"]
    quest_topic = next(row for row in payload.topics if row["topic_id"] == "quests")

    assert parsed.manifest.source_world_id == "world:aurelia-echoes-beyond-the-gate"
    assert payload.world["title"] == "Aurelia: Echoes Beyond the Gate"
    assert len(parsed.manifest.assets) == 10
    assert len(payload.topics) == 11
    assert len(payload.topic_history) == 11
    assert len(payload.map_blueprints) == 5
    assert len(payload.map_definitions) == 5
    assert len(payload.scenario_revisions) == 3
    assert len(manifest["characters"]) == 10
    assert len(manifest["factions"]) == 6
    assert len(revision["adventure_seeds"]) == 5
    assert len(quest_topic["content"]["quests"]) == 6

    map_ids = {row["map_id"] for row in payload.map_definitions}
    assert map_ids == {
        "map:starfall-grove",
        "map:starfall-village",
        "map:wayfarers-guild",
        "map:skybridge-pass",
        "map:moonroot-ruins",
    }
    assert all(row["status"] == "ready" for row in payload.map_blueprints)
    assert payload.world_releases[0]["document"]["certification"]["launch_ready"] is True
    assert all(
        row["document"]["compatible_release"] == 1
        for row in payload.scenario_revisions
    )
