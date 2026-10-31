"""Write ``play-sections.json`` into Aurelia's source bundle the way a world author does (W1, RQ-4.1).

First ``lore-additions.json`` (the game master's palette and the maps of places that had none) is written into the
source world. Its people, items, gear and quest rewards are the bundle's own topics, as the world editor lists, edits
and adds them, and a publication carries what the editor changed into the canon (``genesis/worlds/topic_entries``).
Then the world library's own lifecycle does the rest, so every hash and binding is the library's: the current bundle is
imported into a disposable database, the sections are saved as the author's draft (``save_play_sections``) and
published (``publish_play_sections``: a new world revision and release, each opening repaired onto it), and the world
is exported (``export_world_bundle``). Its ``world.json`` replaces the source bundle's, so the source keeps its
placeholder assets and manifest, and ``materialize.py`` still adds the artwork. Then the source parts, the
materializer's checksum and the README's bundle hash are rewritten.

    OMNIX_DATABASE_URL=postgresql://...@127.0.0.1:16432/<disposable db> \\
        python resources/examples/rpg/world-bundles/aurelia-echoes-beyond-the-gate/author_play_sections.py \\
        --allow-database <disposable db>
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import sys
import zipfile
import zlib

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
# The run rewrites materialize.py's checksum in place (the same length): a bytecode copy cached earlier in the run
# can pass for it and check the old one.
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "src"))
PART_CHARS = 5000
# What the scratch import adds to the world's metadata, and the editor's working draft (the published revision's canon
# holds the sections): the source bundle keeps none of it.
IMPORT_KEYS = ("world_bundle_import", "world_adoption", "community_catalog", "play_sections")


def _materializer():
    spec = importlib.util.spec_from_file_location("aurelia_materialize", HERE / "materialize.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _json(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def with_lore_additions(payload: dict, additions: dict) -> dict:
    """The source world with ``lore-additions.json``'s game-master palette (what each area holds and favours, EV-10) in
    each revision's canon."""
    if additions.get("gm_guide"):
        for row in payload["world_revisions"]:
            row["document"]["canon"]["gm_guide"] = additions["gm_guide"]
    return payload


def source_world_json() -> dict:
    materialize = _materializer()
    with zipfile.ZipFile(io.BytesIO(materialize._source_bundle(HERE))) as source:
        return json.loads(source.read("world.json"))


def with_maps(payload: dict, maps: list) -> dict:
    """The source world with ``lore-additions.json``'s maps (EV-8), as the world editor's map tools would leave them:
    each a square-grid map of a place the world had left deferred, a definition for every world revision, its
    blueprint, its binding in every release, and the place's ``map_id``. Run twice, it writes the same."""
    from app.apps.rpg.genesis.worlds.contracts import canonical_content_hash
    from app.apps.rpg.genesis.worlds.map_blueprint_authoring import MapBlueprintDocument
    from app.apps.rpg.world.map_grid_contracts import GridMapDefinition, with_grid_definition_hashes

    world_id = payload["world"]["id"] if "id" in payload["world"] else _materializer().WORLD_ID
    palette = [{"code": ".", "terrain_id": "grass", "walkable": True, "blocks_sight": False, "movement_cost": 10},
               {"code": "r", "terrain_id": "road", "walkable": True, "blocks_sight": False, "movement_cost": 7},
               {"code": "f", "terrain_id": "forest", "walkable": True, "blocks_sight": True, "movement_cost": 15},
               {"code": "w", "terrain_id": "water", "walkable": False, "blocks_sight": False, "movement_cost": 99},
               {"code": "#", "terrain_id": "wall", "walkable": False, "blocks_sight": True, "movement_cost": 99}]
    for spec in maps:
        map_id, location_id = spec["map_id"], spec["location_id"]
        blueprint = MapBlueprintDocument.model_validate({
            "map_id": map_id, "location_id": location_id, "level": spec["level"], "navigation_kind": "square_grid",
            "size_profile": spec["size_profile"], "required_spawn_point_ids": [row["spawn_point_id"] for row in spec["spawn_points"]],
            "required_zone_ids": [row["zone_id"] for row in spec["zones"]], "directives": spec["directives"],
            "metadata": {"description": spec["description"]}})
        blueprint_json = blueprint.model_dump(mode="json")
        blueprint_hash = canonical_content_hash(blueprint_json)
        blueprint_semantic = canonical_content_hash(blueprint.semantic_interface())
        payload["map_blueprints"] = [row for row in payload["map_blueprints"] if row["map_id"] != map_id] + [{
            "blueprint_revision": 1, "content_hash": blueprint_hash, "created_at": "2026-10-30T00:00:00+00:00",
            "document": blueprint_json, "findings": [], "map_id": map_id, "semantic_interface_hash": blueprint_semantic,
            "status": "ready"}]
        payload["map_definitions"] = [row for row in payload["map_definitions"] if row["map_id"] != map_id]
        definitions = {}
        for revision in payload["world_revisions"]:
            number = int(revision["revision"])
            definition = with_grid_definition_hashes(GridMapDefinition.model_validate({
                "map_id": map_id, "level": spec["level"], "definition_revision": number, "world_id": world_id,
                "world_revision": number, "width": len(spec["terrain_rows"][0]), "height": len(spec["terrain_rows"]),
                "terrain_palette": palette, "terrain_rows": spec["terrain_rows"], "portals": [],
                "spawn_points": spec["spawn_points"], "zones": spec["zones"],
                "metadata": {"location_id": location_id, "description": spec["description"],
                             "presentation_fallback": "semantic_grid_placeholder", "art_optional": True}}))
            document = definition.model_dump(mode="json")
            definitions[number] = definition
            payload["map_definitions"].append({
                "created_at": "2026-10-30T00:00:00+00:00", "definition_hash": definition.definition_hash,
                "definition_revision": number, "document": document, "map_id": map_id,
                "semantic_interface_hash": definition.semantic_interface_hash, "world_revision": number})
            body = revision["document"]
            for row in body["topology"]["locations"]:
                if isinstance(row, dict) and row.get("id") == location_id:
                    row["map_id"] = map_id
                    row.pop("deferred", None)
            body["blueprint_requirements"] = [row for row in body.get("blueprint_requirements") or ()
                                              if row.get("map_id") != map_id] + [{
                **blueprint_json, "blueprint_hash": blueprint_hash, "blueprint_revision": 1,
                "semantic_interface_hash": blueprint_semantic, "simulation_readiness": "certified",
                "presentation_readiness": "placeholder"}]
        for release in payload["world_releases"]:
            definition = definitions[int(release["world_revision"])]
            body = release["document"]
            body["map_bindings"] = [row for row in body.get("map_bindings") or () if row.get("map_id") != map_id] + [{
                "blueprint_revision": 1, "definition_hash": definition.definition_hash,
                "definition_revision": definition.definition_revision, "map_id": map_id,
                "presentation_readiness": "placeholder", "semantic_interface_hash": definition.semantic_interface_hash,
                "simulation_readiness": "certified"}]
    return payload


def published_world_json(sections: dict) -> dict:
    from app.apps.rpg.genesis.worlds.play_section_authoring import (
        publish_play_sections,
        read_play_sections,
        save_play_sections,
    )
    from app.apps.rpg.genesis.worlds.world_bundle_export import export_world_bundle
    from app.apps.rpg.genesis.worlds.world_adoption import adopt_shared_world
    from app.apps.rpg.genesis.worlds.world_bundle_import import import_world_bundle
    from tests.rehearsal.rpg import worlds

    materialize = _materializer()
    world_id = materialize.WORLD_ID
    imported = import_world_bundle(worlds.world_bundle("aurelia"), target_world_id=world_id)
    adopt_shared_world(world_id, bundle_sha256=imported["bundle_sha256"])  # a shared world is adopted to be edited
    current = read_play_sections(world_id)
    saved = save_play_sections(world_id, expected_content_hash=current["content_hash"], document=sections)
    if saved.get("findings"):
        raise SystemExit(f"the sections name what Aurelia lacks: {saved['findings']}")
    published = publish_play_sections(world_id)
    if published.get("findings"):
        raise SystemExit(f"publication findings: {published['findings']}")
    exported = export_world_bundle(world_id)
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        payload = json.loads(archive.read("world.json"))
    metadata = payload["world"].get("metadata") or {}
    for key in IMPORT_KEYS:
        metadata.pop(key, None)
    return payload


def write_source(payload: dict) -> str:
    """The source bundle with this ``world.json``: its parts rewritten; returns the new source checksum."""
    materialize = _materializer()
    with zipfile.ZipFile(io.BytesIO(materialize._source_bundle(HERE))) as source:
        members = {info.filename: source.read(info.filename) for info in source.infolist()}
    world = _json(payload)
    manifest = json.loads(members["manifest.json"])
    manifest["data_sha256"] = hashlib.sha256(world).hexdigest()
    members["manifest.json"], members["world.json"] = _json(manifest), world
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in ["manifest.json", "world.json", *sorted(name for name in members if name.startswith("assets/"))]:
            info = zipfile.ZipInfo(path, date_time=materialize.FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, members[path], compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    content = output.getvalue()
    encoded = base64.b64encode(zlib.compress(content, 9)).decode("ascii")
    parts = HERE / "bundle-parts"
    for old in parts.glob("*.b64"):
        old.unlink()
    for index in range(0, len(encoded), PART_CHARS):
        (parts / f"{index // PART_CHARS:02d}.b64").write_text(encoded[index:index + PART_CHARS] + "\n", encoding="ascii")
    digest = hashlib.sha256(content).hexdigest()
    script = (HERE / "materialize.py").read_text(encoding="utf-8")
    script = re.sub(r'SOURCE_BUNDLE_SHA256 = "[0-9a-f]{64}"', f'SOURCE_BUNDLE_SHA256 = "{digest}"', script)
    (HERE / "materialize.py").write_text(script, encoding="utf-8", newline="\n")
    return digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--allow-database", default="", help="a disposable database whose name lacks 'test'/'bench'")
    args = parser.parse_args(argv)
    from tests.rehearsal.rpg import worlds

    worlds.require_disposable_database(args.allow_database)
    worlds.bootstrap()
    additions = json.loads((HERE / "lore-additions.json").read_text(encoding="utf-8"))
    # The lore first, as its author wrote it, and the maps of the places it had left without one (EV-8).
    write_source(with_maps(with_lore_additions(source_world_json(), additions), additions.get("maps") or []))
    sections = json.loads((HERE / "play-sections.json").read_text(encoding="utf-8"))
    payload = published_world_json(sections)
    source = write_source(payload)
    bundle = _materializer().materialize_bundle(HERE)
    bundle_digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
    readme = (HERE / "README.md").read_text(encoding="utf-8")
    readme = re.sub(r"Bundle SHA-256: `[0-9a-f]{64}`", f"Bundle SHA-256: `{bundle_digest}`", readme)
    (HERE / "README.md").write_text(readme, encoding="utf-8", newline="\n")
    revisions = [row["revision"] for row in payload["world_revisions"]]
    print(json.dumps({"source_sha256": source, "bundle_sha256": bundle_digest, "world_revisions": revisions}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
