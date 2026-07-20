from __future__ import annotations

from app.rpg.worlds.authoring_service import (
    read_authoring_manifest,
    read_authoring_section,
)
from app.rpg.worlds.authoring_presentations import entity_card


def _detail() -> dict[str, object]:
    return {
        "world": {
            "id": "world:aurelia",
            "title": "Aurelia",
            "description": "A living fantasy world.",
            "genre": "fantasy",
            "tone": "heroic",
            "draft_revision": 2,
            "metadata": {},
        },
        "topics": [
            {
                "topic_id": "realm",
                "status": "ready",
                "content": {
                    "entities": [
                        {
                            "id": "realm:aurelia",
                            "name": "Aurelia",
                            "kind": "realm",
                        }
                    ],
                    "documents": [
                        {
                            "title": "Realm Overview",
                            "full_text": "Aurelia is a realm of old roads and living magic.",
                            "entities": ["realm:aurelia"],
                        }
                    ],
                    "facts": [],
                },
                "provenance": {},
            },
            {
                "topic_id": "locations",
                "status": "ready",
                "content": {
                    "entities": [
                        {
                            "id": "location:market",
                            "name": "Moon Market",
                            "kind": "location",
                            "region_id": "region:central_reach",
                            "sensory_profile": "Lantern smoke and rain-dark stone.",
                            "dossier_status": "complete",
                        }
                    ],
                    "documents": [],
                    "facts": [],
                },
                "provenance": {},
            },
            {
                "topic_id": "npcs",
                "status": "ready",
                "content": {"entities": [], "documents": [], "facts": []},
                "provenance": {},
            },
            {
                "topic_id": "points_of_interest",
                "status": "ready",
                "content": {
                    "entities": [
                        {
                            "id": "poi:glass_well",
                            "name": "The Glass Well",
                            "kind": "point_of_interest",
                            "location_id": "location:market",
                            "region_id": "region:central_reach",
                            "purpose": "A public well that reflects possible futures.",
                            "sensory_profile": "Cold light trembles below the water.",
                            "hooks": ["A reflection asks for help", "A rival arrives first"],
                        }
                    ],
                    "documents": [],
                    "facts": [],
                },
                "provenance": {},
            },
            {
                "topic_id": "classes",
                "status": "ready",
                "content": {
                    "entities": [
                        {
                            "id": "class:ward_runner",
                            "name": "Ward Runner",
                            "kind": "class",
                            "capabilities": ["Cross active wards", "Redirect one spell"],
                            "progression": ["Initiate", "Runner", "Pathfinder"],
                            "equipment": ["Ward key", "Travel cloak"],
                            "institution_ids": ["institution:wayfinders"],
                        }
                    ],
                    "documents": [],
                    "facts": [],
                },
                "provenance": {},
            },
        ],
        "map_blueprints": [],
        "revisions": [],
        "releases": [],
        "scenarios": [],
        "scenario_revisions": {},
        "generation_runs": [
            {
                "run_id": "run:1",
                "status": "review",
                "graph": {
                    "nodes": [
                        {"topic_id": "realm", "title": "Realm Overview", "category": "lore", "dependencies": []},
                        {"topic_id": "locations", "title": "Major Locations", "category": "locations", "dependencies": ["realm"]},
                        {"topic_id": "npcs", "title": "Central NPC Cast", "category": "npcs", "dependencies": ["locations"]},
                        {"topic_id": "points_of_interest", "title": "Points of Interest", "category": "points_of_interest", "dependencies": ["locations"]},
                        {"topic_id": "classes", "title": "Classes and Disciplines", "category": "classes", "dependencies": ["realm"]},
                        {"topic_id": "canon_compile", "title": "Canon Compilation", "category": "compiler", "dependencies": ["realm"]},
                    ]
                },
                "progress": {"active_topic_ids": [], "failed_topic_ids": []},
            }
        ],
    }


def test_manifest_uses_user_facing_sections_and_hides_pipeline_nodes(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.rpg.worlds.authoring_service.read_world_detail",
        lambda world_id, database=None: _detail(),
    )

    manifest = read_authoring_manifest("world:aurelia")
    sections = {row["id"]: row for row in manifest["sections"]}

    assert sections["realm"]["page_kind"] == "document"
    assert sections["locations"]["label"] == "Areas"
    assert sections["locations"]["page_kind"] == "collection"
    assert sections["npcs"]["label"] == "Characters"
    assert sections["points_of_interest"]["page_kind"] == "collection"
    assert sections["classes"]["page_kind"] == "collection"
    assert "areas" not in sections
    assert "canon_compile" not in sections


def test_lore_with_entities_stays_a_document_page(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.rpg.worlds.authoring_service.read_world_detail",
        lambda world_id, database=None: _detail(),
    )

    page = read_authoring_section("world:aurelia", "realm")

    assert page["page_kind"] == "document"
    assert page["title"] == "Realm Overview"
    assert page["body"][0]["kind"] == "section"
    assert "living magic" in page["body"][0]["body"]


def test_points_of_interest_and_classes_have_typed_card_presentations(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.rpg.worlds.authoring_service.read_world_detail",
        lambda world_id, database=None: _detail(),
    )

    poi_page = read_authoring_section("world:aurelia", "points_of_interest")
    class_page = read_authoring_section("world:aurelia", "classes")
    poi = poi_page["entities"][0]
    character_class = class_page["entities"][0]

    assert poi["card_type"] == "points_of_interest"
    assert poi["presentation"]["eyebrow"] == "Point of Interest"
    assert {row["label"] for row in poi["presentation"]["highlights"]} == {
        "Location",
        "Region",
    }
    assert poi["presentation"]["groups"][0] == {
        "label": "Hooks",
        "items": ["A reflection asks for help", "A rival arrives first"],
        "style": "list",
    }

    assert character_class["card_type"] == "classes"
    assert character_class["presentation"]["eyebrow"] == "Class / Discipline"
    groups = {row["label"]: row for row in character_class["presentation"]["groups"]}
    assert groups["Capabilities"]["style"] == "list"
    assert groups["Progression"]["items"] == ["Initiate", "Runner", "Pathfinder"]
    assert groups["Equipment"]["style"] == "chips"


def test_system_collection_cards_receive_typed_presentations() -> None:
    card = entity_card(
        {
            "map_id": "map:market",
            "blueprint_revision": 3,
            "status": "ready",
            "document": {"title": "Moon Market Map"},
        },
        card_type="map_blueprints",
        kind="map_blueprint",
        index=0,
    )

    assert card["title"] == "Moon Market Map"
    assert card["presentation"]["badges"] == ["ready"]
    assert card["presentation"]["highlights"] == [
        {"label": "Map", "value": "map:market"},
        {"label": "Revision", "value": 3},
    ]
