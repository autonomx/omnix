from __future__ import annotations

from app.rpg.worlds.authoring_service import (
    _world_token_usage,
    read_authoring_manifest,
    read_authoring_section,
)
from app.rpg.worlds.authoring_presentations import (
    COLLECTION_CATEGORIES,
    SYSTEM_SECTIONS,
    entity_card,
)


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
    monkeypatch.setattr(
        "app.rpg.worlds.authoring_service._image_section_status",
        lambda world_id, database=None: ("complete", 3),
    )

    manifest = read_authoring_manifest("world:aurelia")
    sections = {row["id"]: row for row in manifest["sections"]}

    assert sections["realm"]["page_kind"] == "document"
    assert sections["locations"]["label"] == "Areas"
    assert sections["locations"]["page_kind"] == "collection"
    assert sections["npcs"]["label"] == "Characters"
    assert sections["points_of_interest"]["page_kind"] == "collection"
    assert sections["classes"]["page_kind"] == "collection"
    assert sections["images"]["operational_status"] == "complete"
    assert sections["images"]["entity_count"] == 3
    assert "areas" not in sections
    assert "canon_compile" not in sections


def test_world_token_usage_prefers_provider_usage_and_marks_estimates() -> None:
    summary = _world_token_usage(
        (
            {
                "source": "ai",
                "provenance": {
                    "usage": {
                        "prompt_tokens": 120,
                        "completion_tokens": 30,
                        "total_tokens": 150,
                    }
                },
            },
            {
                "source": "ai",
                "provenance": {
                    "token_estimate": {
                        "prompt_tokens": 80,
                        "completion_tokens": 20,
                        "total_tokens": 100,
                    }
                },
            },
            {"source": "manual", "provenance": {}},
        )
    )

    assert summary == {
        "prompt_tokens": 200,
        "completion_tokens": 50,
        "total_tokens": 250,
        "provider_reported_topics": 1,
        "estimated_topics": 1,
        "unavailable_topics": 0,
        "topic_count": 2,
        "in_flight_topics": 0,
    }


def test_world_token_usage_includes_active_entity_batch_checkpoints() -> None:
    summary = _world_token_usage(
        (),
        active_job_progresses=(
            {
                "token_usage": {
                    "prompt_tokens": 90,
                    "completion_tokens": 45,
                    "total_tokens": 135,
                    "source": "estimated",
                }
            },
            {
                "token_usage": {
                    "prompt_tokens": 120,
                    "completion_tokens": 60,
                    "total_tokens": 180,
                    "source": "provider_reported",
                }
            },
        ),
    )

    assert summary == {
        "prompt_tokens": 210,
        "completion_tokens": 105,
        "total_tokens": 315,
        "provider_reported_topics": 1,
        "estimated_topics": 1,
        "unavailable_topics": 0,
        "topic_count": 0,
        "in_flight_topics": 2,
    }


def test_world_token_usage_does_not_mark_an_unreported_live_call_unavailable() -> None:
    summary = _world_token_usage((), active_job_progresses=({},))

    assert summary["in_flight_topics"] == 1
    assert summary["unavailable_topics"] == 0


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
    assert page["related_entities"][0]["title"] == "Aurelia"


def test_realm_card_uses_a_readable_dossier_label_when_source_canon_omits_a_name() -> None:
    card = entity_card(
        {
            "entity_id": "ent:realm:001",
            "dossier": {
                "quick_facts": [
                    {"label": "Readable label", "value": "The Post-War American Wasteland"},
                ],
            },
        },
        card_type="realm",
        kind="realm",
        index=0,
    )

    assert card["title"] == "The Post-War American Wasteland"


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


def test_every_collection_section_has_a_non_generic_card_schema() -> None:
    system_collections = {
        str(section["id"])
        for section in SYSTEM_SECTIONS
        if section["page_kind"] == "collection" and section["id"] != "images"
    }
    card_types = COLLECTION_CATEGORIES | system_collections
    sample = {
        "id": "entity:sample",
        "name": "Sample",
        "description": "A formatted sample card.",
        "visibility": "public",
        "status": "ready",
        "dossier_status": "complete",
        "realm_id": "realm:aurelia",
        "region_id": "region:central_reach",
        "region_ids": ["region:central_reach"],
        "location_id": "location:market",
        "location_ids": ["location:market"],
        "faction_ids": ["faction:wardens"],
        "institution_ids": ["institution:wayfinders"],
        "class_ids": ["class:ward_runner"],
        "actor_ids": ["npc:bran"],
        "initial_npc_ids": ["npc:bran"],
        "threat_ids": ["monster:glass_hound"],
        "quest_ids": ["quest:glass_well"],
        "opening_seed_ids": ["quest:glass_well"],
        "giver_id": "npc:bran",
        "starting_location_id": "location:market",
        "mobility_status": "itinerant",
        "speech_style": "plainspoken",
        "lifespan": "roughly one century",
        "threat_level": "dangerous",
        "item_type": "relic",
        "rarity": "rare",
        "value": 250,
        "school": "warding",
        "tier": 2,
        "range": "near",
        "release": 1,
        "world_revision": 2,
        "revision": 2,
        "content_hash": "sha256:sample",
        "map_id": "map:market",
        "blueprint_revision": 1,
        "world_id": "world:aurelia",
        "hooks": ["A hook"],
        "goals": ["A goal"],
        "motives": ["Duty"],
        "homelands": ["Central Reach"],
        "cultures": ["Market folk"],
        "traits": ["A trait"],
        "languages": ["Common"],
        "capabilities": ["A capability"],
        "progression": ["Initiate"],
        "equipment": ["A tool"],
        "values": ["Duty"],
        "habitats": ["Old roads"],
        "abilities": ["A signature move"],
        "weaknesses": ["A weakness"],
        "effects": ["A bounded effect"],
        "origin_ids": ["faction:wardens"],
        "costs": ["Focus"],
        "prerequisites": ["Training"],
        "benefits": ["A benefit"],
        "limitations": ["A limitation"],
        "objectives": ["Investigate"],
        "rewards": ["Reputation"],
        "complications": ["A rival intervenes"],
        "outcomes": ["The district changes"],
        "beats": ["Hook", "Climax"],
        "starting_resources": [{"resource": "currency", "amount": 25}],
    }

    for index, card_type in enumerate(sorted(card_types)):
        card = entity_card(
            sample,
            card_type=card_type,
            kind=card_type.rstrip("s"),
            index=index,
        )
        presentation = card["presentation"]
        assert presentation["variant"] == card_type
        assert presentation["eyebrow"]
        assert (
            presentation["badges"]
            or presentation["highlights"]
            or presentation["groups"]
        ), card_type
