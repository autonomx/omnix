"""Write ``play-sections.json`` into Aurelia's source bundle the way a world author does (W1, RQ-4.1).

First ``lore-additions.json`` (items and gear, characters, quest rewards) is written into the source world's lore.
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


def _merged(rows: list, additions: list, changes: dict) -> list:
    """``rows`` with each id's ``changes`` merged in and each addition not there yet appended (by id: run twice, it
    writes the same)."""
    rows = [{**row, **changes.get(row.get("id"), {})} for row in rows]
    known = {row.get("id") for row in rows}
    return [*rows, *(dict(row) for row in additions if row["id"] not in known)]


def _rewarded(quests: list, rewards: dict) -> list:
    return [{**quest, "rewards": [*quest.get("rewards", []),
                                  *(reward for reward in rewards.get(quest.get("id"), ()) if reward not in quest.get("rewards", []))]}
            for quest in quests]


def with_lore_additions(payload: dict, additions: dict) -> dict:
    """The source world with ``lore-additions.json`` written into its lore, as its author wrote the rest: items (with
    how gear is worn and fights), characters, and quest rewards, into each revision's canon and entity manifest, the
    releases' indexes and the topics the world editor shows. The import rehashes what changed."""
    items, characters = additions.get("items", []), additions.get("characters", [])
    item_changes, rewards = additions.get("item_changes", {}), additions.get("quest_rewards", {})
    for row in payload["world_revisions"]:
        document = row["document"]
        canon = document["canon"]
        canon["items"] = _merged(canon.get("items", []), items, item_changes)
        canon["characters"] = _merged(canon.get("characters", []), characters, {})
        canon["quests"] = _rewarded(canon.get("quests", []), rewards)
        manifest = document["entity_manifest"]
        for key, rows in (("items", items), ("characters", characters)):
            manifest[key] = [*manifest.get(key, []), *(row["id"] for row in rows if row["id"] not in manifest.get(key, []))]
    for row in payload["world_releases"]:
        indexes = row["document"].get("indexes") or {}
        ids = indexes.get("character_ids")
        if isinstance(ids, list):
            indexes["character_ids"] = [*ids, *(row["id"] for row in characters if row["id"] not in ids)]
        summary = (row["document"].get("certification") or {}).get("content_summary") or {}
        if "characters" in summary and isinstance(ids, list):
            summary["characters"] = len(indexes["character_ids"])
    for topic in payload["topics"]:
        content = topic["content"]
        if topic["topic_id"] == "economy":
            content["items"] = _merged(content.get("items", []), items, item_changes)
        elif topic["topic_id"] == "characters":
            content["characters"] = _merged(content.get("characters", []), characters, {})
        elif topic["topic_id"] == "quests":
            content["quests"] = _rewarded(content.get("quests", []), rewards)
    return payload


def source_world_json() -> dict:
    materialize = _materializer()
    with zipfile.ZipFile(io.BytesIO(materialize._source_bundle(HERE))) as source:
        return json.loads(source.read("world.json"))


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
    write_source(with_lore_additions(source_world_json(), additions))  # the lore first, as its author wrote it
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
