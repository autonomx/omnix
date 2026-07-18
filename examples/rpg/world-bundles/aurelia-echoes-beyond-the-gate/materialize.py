from __future__ import annotations

import argparse
import base64
import hashlib
import json
import zipfile
import zlib
from io import BytesIO
from pathlib import Path
from typing import Any

BUNDLE_FILENAME = "aurelia-echoes-beyond-the-gate.omnix-world.zip"
SOURCE_BUNDLE_SHA256 = "9582c2ee7aecfb1d0890210bcd198baedfe4d1ef4ddfbadd6b5086a35f6eb944"
BUNDLE_SHA256 = "7b4b4d2868af5b96070f3f40a6f27983576dfda50bb5c9d2972424db64e45eb6"
WORLD_ID = "world:aurelia-echoes-beyond-the-gate"
FIXED_ZIP_TIME = (2026, 7, 17, 9, 30, 0)
ARTWORK: dict[str, tuple[str, dict[str, str]]] = {
    "image-aurelia-cover": ("image:aurelia:cover", {"kind": "cover", "title": "Aurelia: Echoes Beyond the Gate cover art"}),
    "image-aurelia-arrival-grove": ("image:aurelia:arrival-grove", {"map_id": "map:aurelia:arrival-grove", "title": "Starfall Grove"}),
    "image-aurelia-liora-portrait": ("image:aurelia:liora-portrait", {"character_id": "npc:liora-fen", "title": "Liora Fen"}),
    "image-aurelia-malrec-portrait": ("image:aurelia:malrec-portrait", {"character_id": "npc:archon-malrec", "title": "Archon Malrec"}),
    "image-aurelia-moonroot-ruins": ("image:aurelia:moonroot-ruins", {"map_id": "map:aurelia:moonroot-ruins", "title": "Moonroot Ruins"}),
    "image-aurelia-seraphine-portrait": ("image:aurelia:seraphine-portrait", {"character_id": "npc:seraphine-valecourt", "title": "Seraphine Valecourt"}),
    "image-aurelia-skybridge-pass": ("image:aurelia:skybridge-pass", {"map_id": "map:aurelia:skybridge-pass", "title": "Skybridge Pass"}),
    "image-aurelia-starfall-village": ("image:aurelia:starfall-village", {"map_id": "map:aurelia:starfall-village", "title": "Starfall Village"}),
    "image-aurelia-vael-portrait": ("image:aurelia:vael-portrait", {"character_id": "npc:vael-ardyn", "title": "Vael Ardyn"}),
    "image-aurelia-wayfarer-guild": ("image:aurelia:wayfarer-guild", {"map_id": "map:aurelia:wayfarer-guild", "title": "Wayfarers' Guild Hall"}),
    "image-aurelia-world-map": ("image:aurelia:world-map", {"kind": "world_map", "title": "Map of Aurelia"}),
}


def _json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _source_bundle(source_dir: Path) -> bytes:
    parts = sorted((source_dir / "bundle-parts").glob("*.b64"))
    if not parts:
        raise FileNotFoundError("Aurelia source bundle parts are missing")
    encoded = "".join(part.read_text(encoding="ascii").strip() for part in parts)
    content = zlib.decompress(base64.b64decode(encoded, validate=True))
    digest = hashlib.sha256(content).hexdigest()
    if digest != SOURCE_BUNDLE_SHA256:
        raise ValueError(f"Aurelia source bundle checksum mismatch: {digest}")
    return content


def _webp_dimensions(content: bytes) -> tuple[int, int]:
    if len(content) < 30 or content[:4] != b"RIFF" or content[8:12] != b"WEBP":
        raise ValueError("Artwork is not a WebP image")
    kind = content[12:16]
    if kind == b"VP8X":
        return 1 + int.from_bytes(content[24:27], "little"), 1 + int.from_bytes(content[27:30], "little")
    if kind == b"VP8 ":
        marker = content.find(b"\x9d\x01\x2a", 20)
        if marker < 0:
            raise ValueError("Invalid VP8 WebP image")
        return int.from_bytes(content[marker + 3 : marker + 5], "little") & 0x3FFF, int.from_bytes(content[marker + 5 : marker + 7], "little") & 0x3FFF
    if kind == b"VP8L":
        bits = int.from_bytes(content[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    raise ValueError(f"Unsupported WebP encoding: {kind!r}")


def _build_bundle(source_dir: Path) -> bytes:
    with zipfile.ZipFile(BytesIO(_source_bundle(source_dir))) as source:
        payload = json.loads(source.read("world.json"))
        manifest = json.loads(source.read("manifest.json"))
    assets = {row["asset_id"]: row for row in manifest["assets"]}
    files: dict[str, bytes] = {}
    ids: list[str] = []
    for stem, (asset_id, labels) in ARTWORK.items():
        content = (source_dir / "artwork" / f"{stem}.webp").read_bytes()
        width, height = _webp_dimensions(content)
        metadata = dict(assets.get(asset_id, {}).get("metadata", {}))
        metadata.update(labels | {"height": height, "immutable": True, "visual_style": "production fantasy RPG artwork", "width": width, "world_id": WORLD_ID})
        path = f"assets/{stem}.webp"
        assets[asset_id] = {
            "archive_path": path, "asset_id": asset_id, "asset_type": "image",
            "byte_size": len(content), "checksum_sha256": hashlib.sha256(content).hexdigest(),
            "compat": {"contract": "image_generation_asset_v1", "source": "generated-production-artwork"},
            "metadata": metadata, "mime_type": "image/webp", "module": "sample-world", "source_job_id": None,
        }
        files[path] = content
        ids.append(asset_id)
    payload["world"].setdefault("metadata", {}).update({
        "artwork_asset_ids": ids,
        "cover_image_asset_id": "image:aurelia:cover",
        "thumbnail_asset_id": "image:aurelia:world-map",
    })
    world_bytes = _json(payload)
    manifest["assets"] = [assets[key] for key in sorted(assets)]
    manifest["data_sha256"] = hashlib.sha256(world_bytes).hexdigest()
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        entries = [("manifest.json", _json(manifest)), ("world.json", world_bytes), *sorted(files.items())]
        for path, content in entries:
            info = zipfile.ZipInfo(path, date_time=FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return output.getvalue()


def materialize_bundle(source_dir: Path, output: Path | None = None) -> Path:
    content = _build_bundle(source_dir)
    digest = hashlib.sha256(content).hexdigest()
    if digest != BUNDLE_SHA256:
        raise ValueError(f"Aurelia bundle checksum mismatch: {digest}")
    destination = output or source_dir.parent / BUNDLE_FILENAME
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize the Aurelia Omnix world bundle")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    print(materialize_bundle(Path(__file__).resolve().parent, args.output))


if __name__ == "__main__":
    main()
