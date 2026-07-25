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
