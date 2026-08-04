from __future__ import annotations

import argparse
import base64
import hashlib
import json
import types
import zipfile
import zlib
from io import BytesIO
from pathlib import Path
from typing import Any

BUNDLE_FILENAME = "vesper-9-city-of-borrowed-minds.omnix-world.zip"
FIXED_TIME = (2026, 7, 29, 12, 0, 0)
EXPORTED_AT = "2026-07-29T19:00:00+00:00"
CATALOGUE_SHA256 = "b38e37a33cd446268e8dca360dcc45c233abb899099fade908a3e56530658015"
BUNDLE_SHA256 = "41b3a7f7bdd17d38253034d07b50962f640545b1e920e329116a779ca55c89be"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(value: Any) -> str:
    raw = value if isinstance(value, bytes) else _canonical(value)
    return hashlib.sha256(raw).hexdigest()


def _catalogue(source_dir: Path) -> types.ModuleType:
    parts = sorted((source_dir / "catalogue-parts").glob("*.b64"))
    if not parts:
        raise FileNotFoundError("Vesper-9 catalogue parts are missing")
    encoded = "".join(part.read_text(encoding="ascii").strip() for part in parts)
    source = zlib.decompress(base64.b64decode(encoded, validate=True))
    digest = hashlib.sha256(source).hexdigest()
    if digest != CATALOGUE_SHA256:
        raise ValueError(f"Vesper-9 catalogue checksum mismatch: {digest}")
    module = types.ModuleType("vesper9_catalogue")
    exec(compile(source, "vesper9_catalogue.py", "exec"), module.__dict__)
    return module


def _profile(catalogue: types.ModuleType) -> dict[str, Any]:
    domains: list[dict[str, Any]] = []
    for topic_id, spec in catalogue.SPECS.items():
        title, kind, deps, page_kind, card_variant, image_role, group, standard, semantic_roles = spec
        low, high = standard
        domains.append({
            "domain_id": topic_id,
            "title": title,
            "entity_kind": kind,
            "dependencies": list(deps),
            "generator_role": "world_forge",
            "required_before_launch": True,
            "visibility_default": "game_master_canon",
            "fields": [
                {"field_id": "name", "value_type": "string", "required": True, "semantic_role": "", "allowed_target_domains": [], "enum_values": [], "description": "Canonical display name."},
                {"field_id": "description", "value_type": "string", "required": True, "semantic_role": "", "allowed_target_domains": [], "enum_values": [], "description": "Multi-paragraph canonical lore."},
                {"field_id": "image_prompt", "value_type": "string", "required": False, "semantic_role": "", "allowed_target_domains": [], "enum_values": [], "description": "Prompt only; image assets are intentionally omitted."},
            ],
            "target_range": {
                "quick": [max(1, low // 2), max(1, low)],
                "standard": [low, high],
                "epic": [high, min(50, max(high + 2, high * 2))],
            },
            "semantic_roles": list(semantic_roles),
            "category": "domain",
            "generation_guidance": {
                "presentation": {
                    "page_kind": page_kind,
                    "card_variant": card_variant,
                    "image_role": image_role,
                    "group": group,
                },
                "instruction": "Preserve Vesper-9 canon, causal dependencies, lived-in detail, and image prompts without generating image assets.",
            },
        })
    profile: dict[str, Any] = {
        "profile_id": "cyberpunk:vesper-9",
        "version": 2,
        "display_name": "Cyberpunk — Vesper-9",
        "domains": domains,
        "aliases": ["cyberpunk", "corporate dystopia", "high tech low life", "vesper-9"],
        "parent_profile_ids": ["cyberpunk"],
        "modifier_ids": ["memory-economy", "drowned-megacity", "living-factions"],
        "genre_tags": ["cyberpunk", "corporations", "augmentation", "networks", "memory", "surveillance"],
        "launch_requirements": {
            "required_domain_ids": list(catalogue.SPECS),
            "required_semantic_roles": ["starting_context", "initial_actors", "initial_conflict"],
        },
        "runtime_capability_defaults": {"digital_spaces": True, "economy": True, "resource_simulation": True},
        "provenance": {"source": "sample_world_bundle", "standard_catalogue": list(catalogue.SPECS)},
        "scope": "world_local",
    }
    profile["content_hash"] = "sha256:" + _sha(profile)
    return profile


def _payload(source_dir: Path) -> dict[str, Any]:
    catalogue = _catalogue(source_dir)
    profile = _profile(catalogue)
    metadata = {
        "campaign_mode": "persistent_living_world",
        "world_depth": "standard",
        "image_generation": {"assets_included": False, "prompts_included": True},
        "genre_profile_binding": {
            "status": "approved",
            "requested_genre": "cyberpunk",
            "normalized_genre": "cyberpunk",
            "source": "sample_world_bundle",
            "generated": False,
            "profile_id": profile["profile_id"],
            "profile_version": profile["version"],
            "profile_hash": profile["content_hash"],
            "profile": profile,
            "profile_revision": 1,
            "approved_profile_hash": profile["content_hash"],
            "approved_at": EXPORTED_AT,
            "approved_by": "sample-world-author",
            "route": {"provider": "deterministic", "model": "", "source": "sample_world_bundle"},
            "review_findings": [],
            "error": {},
        },
        "canon_notes": [
            "Simulation state remains authoritative; lore supplies constraints, motives, evidence, and image prompts.",
            "NPCs have limited knowledge and may provide conflicting testimony.",
            "Technology always has a physical dependency, maintenance cost, legal owner, observable trace, or failure mode.",
        ],
    }
    world = {
        "id": catalogue.WORLD_ID,
        "title": catalogue.WORLD_TITLE,
        "description": catalogue.WORLD_DESCRIPTION,
        "status": "draft",
        "source_mode": "imported",
        "genre": "cyberpunk",
        "tone": "rebellious, tense, intimate, noir, and socially grounded",
        "seed": 2099,
        "draft_revision": 1,
        "metadata": metadata,
        "created_at": EXPORTED_AT,
        "updated_at": EXPORTED_AT,
    }
    topics: list[dict[str, Any]] = []
    for topic_id, spec in catalogue.SPECS.items():
        content = catalogue.build_topic_content(topic_id)
        dependencies = {dependency: "embedded-canon" for dependency in spec[2]}
        topics.append({
            "topic_id": topic_id,
            "draft_revision": 1,
            "source": "imported",
            "status": "ready",
            "content": content,
            "directives": {
                "lore_density": "rich_multi_paragraph",
                "image_policy": "prompt_only",
                "preserve_causal_links": True,
            },
            "dependency_hashes": dependencies,
            "input_hash": _sha({"topic_id": topic_id, "dependencies": dependencies}),
            "content_hash": _sha(content),
            "provenance": {
                "source": "vesper_9_sample_bundle",
                "authorship": "curated",
                "image_assets_included": False,
            },
            "updated_at": EXPORTED_AT,
        })
    return {
        "world": world,
        "topics": topics,
        "topic_history": [],
        "generation_runs": [],
        "map_blueprints": [],
        "world_revisions": [],
        "map_definitions": [],
        "world_releases": [],
        "scenarios": [],
        "scenario_revisions": [],
    }


def build_bundle(source_dir: Path) -> bytes:
    payload = _payload(source_dir)
    world_bytes = _canonical(payload)
    manifest = {
        "format": "omnix_rpg_world_bundle",
        "version": 1,
        "exported_at": EXPORTED_AT,
        "source_world_id": payload["world"]["id"],
        "data_path": "world.json",
        "data_sha256": hashlib.sha256(world_bytes).hexdigest(),
        "assets": [],
    }
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, content in (("manifest.json", _canonical(manifest)), ("world.json", world_bytes)):
            info = zipfile.ZipInfo(path, date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return output.getvalue()


def materialize_bundle(source_dir: Path, output: Path | None = None) -> Path:
    content = build_bundle(source_dir)
    digest = hashlib.sha256(content).hexdigest()
    if BUNDLE_SHA256 != "__BUNDLE_SHA256__" and digest != BUNDLE_SHA256:
        raise ValueError(f"Vesper-9 bundle checksum mismatch: {digest}")
    destination = output or source_dir.parent / BUNDLE_FILENAME
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize the Vesper-9 Omnix world bundle")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    source_dir = Path(__file__).resolve().parent
    destination = materialize_bundle(source_dir, args.output)
    print(destination)
    print(hashlib.sha256(destination.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
