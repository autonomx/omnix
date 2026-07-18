from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
from types import ModuleType

from app.rpg.worlds.world_bundle import parse_world_bundle_archive

BUNDLE_SHA256 = "7b4b4d2868af5b96070f3f40a6f27983576dfda50bb5c9d2972424db64e45eb6"
SAMPLE_DIR = (
    Path(__file__).resolve().parents[4]
    / "examples"
    / "rpg"
    / "world-bundles"
    / "aurelia-echoes-beyond-the-gate"
)
EXPECTED_ASSET_IDS = {
    "image:aurelia:arrival-grove",
    "image:aurelia:cover",
    "image:aurelia:liora-portrait",
    "image:aurelia:malrec-portrait",
    "image:aurelia:moonroot-ruins",
    "image:aurelia:seraphine-portrait",
    "image:aurelia:skybridge-pass",
    "image:aurelia:starfall-village",
    "image:aurelia:vael-portrait",
    "image:aurelia:wayfarer-guild",
    "image:aurelia:world-map",
}


def _materializer() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "aurelia_world_bundle_materializer",
        SAMPLE_DIR / "materialize.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_aurelia_sample_world_bundle_is_import_ready(tmp_path: Path) -> None:
    output = tmp_path / "aurelia.omnix-world.zip"
    materializer = _materializer()
    assert materializer.materialize_bundle(SAMPLE_DIR, output) == output
    content = output.read_bytes()
    assert hashlib.sha256(content).hexdigest() == BUNDLE_SHA256

    parsed = parse_world_bundle_archive(content)
    payload = parsed.payload
    revision = payload.world_revisions[0]["document"]
    manifest = revision["entity_manifest"]
    quest_topic = next(row for row in payload.topics if row["topic_id"] == "quests")
    assets = {asset.asset_id: asset for asset in parsed.manifest.assets}

    assert parsed.manifest.source_world_id == "world:aurelia-echoes-beyond-the-gate"
    assert payload.world["title"] == "Aurelia: Echoes Beyond the Gate"
    assert payload.world["metadata"]["cover_image_asset_id"] == "image:aurelia:cover"
    assert payload.world["metadata"]["thumbnail_asset_id"] == "image:aurelia:world-map"
    assert set(payload.world["metadata"]["artwork_asset_ids"]) == EXPECTED_ASSET_IDS
    assert set(assets) == EXPECTED_ASSET_IDS
    assert all(asset.mime_type == "image/webp" for asset in assets.values())
    assert all(asset.archive_path.endswith(".webp") for asset in assets.values())
    assert all(asset.byte_size >= 2_000 for asset in assets.values())
    assert assets["image:aurelia:cover"].byte_size >= 10_000
    assert assets["image:aurelia:world-map"].byte_size >= 6_000
    assert all(
        len(parsed.asset_bytes[asset_id]) == asset.byte_size
        for asset_id, asset in assets.items()
    )

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
        "map:aurelia:arrival-grove",
        "map:aurelia:starfall-village",
        "map:aurelia:wayfarer-guild",
        "map:aurelia:skybridge-pass",
        "map:aurelia:moonroot-ruins",
    }
    assert all(row["status"] == "ready" for row in payload.map_blueprints)
    assert payload.world_releases[0]["document"]["certification"]["launch_ready"] is True
    assert all(
        row["document"]["compatible_release"] == 1
        for row in payload.scenario_revisions
    )
