from __future__ import annotations

from app.rpg.session.genesis.world_forge_profile_generation import STANDARD_DOMAIN_IDS
from app.rpg.worlds.authoring_service import read_authoring_manifest


def _empty_cyberpunk_detail() -> dict[str, object]:
    return {
        "world": {
            "id": "world:cyberpunk-2099",
            "title": "Cyberpunk 2099",
            "description": "A neon corporate dystopia.",
            "genre": "cyberpunk",
            "tone": "neon noir",
            "draft_revision": 1,
            "metadata": {"campaign_template": "cyberpunk"},
        },
        "topics": [],
        "map_blueprints": [],
        "revisions": [],
        "releases": [],
        "scenarios": [],
        "scenario_revisions": {},
        "generation_runs": [],
    }


def test_empty_cyberpunk_world_uses_standard_profile_sections_before_generation(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.rpg.worlds.authoring_service.read_world_detail",
        lambda world_id, database=None: _empty_cyberpunk_detail(),
    )
    monkeypatch.setattr(
        "app.rpg.worlds.authoring_service._image_section_status",
        lambda world_id, database=None: ("empty", 0),
    )

    manifest = read_authoring_manifest("world:cyberpunk-2099")
    sections = {str(section["id"]): section for section in manifest["sections"]}

    assert set(STANDARD_DOMAIN_IDS).issubset(sections)
    assert sections["actors"]["page_kind"] == "collection"
    assert sections["actors"]["supports_images"] is True
    assert sections["places"]["page_kind"] == "collection"
    assert sections["groups"]["page_kind"] == "collection"
    assert sections["setting_rules"]["page_kind"] == "document"
    assert {"spells", "pantheon", "hero_system"}.isdisjoint(sections)
    assert manifest["generation"] == {}


def test_profile_manifest_placeholder_does_not_hide_imported_topics(monkeypatch) -> None:
    detail = _empty_cyberpunk_detail()
    detail["topics"] = [
        {
            "topic_id": "regions",
            "status": "ready",
            "content": {
                "entities": [
                    {"id": "region:rainline", "name": "Rainline", "kind": "region"}
                ]
            },
            "provenance": {},
        },
        {
            "topic_id": "groups",
            "status": "ready",
            "content": {
                "entities": [
                    {"id": "group:helix", "name": "Helix", "kind": "group"}
                ]
            },
            "provenance": {},
        },
    ]
    detail["generation_runs"] = [
        {
            "run_id": "profile-manifest:world:cyberpunk-2099",
            "status": "failed",
            "graph": {
                "nodes": [
                    {
                        "topic_id": "profile_resolution",
                        "title": "Genre Profile",
                        "category": "bootstrap",
                    }
                ]
            },
            "progress": {"active_topic_ids": [], "failed_topic_ids": []},
        }
    ]
    monkeypatch.setattr(
        "app.rpg.worlds.authoring_service.read_world_detail",
        lambda world_id, database=None: detail,
    )
    monkeypatch.setattr(
        "app.rpg.worlds.authoring_service._image_section_status",
        lambda world_id, database=None: ("empty", 0),
    )

    manifest = read_authoring_manifest("world:cyberpunk-2099")
    sections = {str(section["id"]): section for section in manifest["sections"]}

    assert sections["regions"]["operational_status"] == "complete"
    assert sections["regions"]["entity_count"] == 1
    assert sections["groups"]["operational_status"] == "complete"
    assert sections["groups"]["entity_count"] == 1
