from __future__ import annotations

import pytest

from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg.worlds.entity_authoring import (
    replace_entity_content,
    validate_entity_references,
)


def test_entity_replacement_preserves_siblings_and_unrelated_records() -> None:
    content = {
        "topic_id": "npcs",
        "entities": [
            {"id": "npc:bran", "name": "Bran", "kind": "npc"},
            {"id": "npc:elara", "name": "Elara", "kind": "npc"},
        ],
        "facts": [
            {"id": "fact:bran", "entity_refs": ["npc:bran"]},
            {"id": "fact:elara", "entity_refs": ["npc:elara"]},
        ],
    }

    replaced = replace_entity_content(
        content,
        "npc:bran",
        {"id": "npc:bran", "name": "Bran", "kind": "npc", "goals": ["protect the inn"]},
    )

    assert [row["id"] for row in replaced["entities"]] == ["npc:bran", "npc:elara"]
    assert replaced["entities"][0]["goals"] == ["protect the inn"]
    assert replaced["entities"][1] == content["entities"][1]
    assert replaced["facts"] == content["facts"]


def test_entity_regeneration_rewrites_identity_and_only_replaces_owned_records() -> None:
    content = {
        "topic_id": "npcs",
        "entities": [
            {"id": "npc:bran", "name": "Bran", "kind": "npc"},
            {"id": "npc:elara", "name": "Elara", "kind": "npc"},
        ],
        "documents": [
            {"document_id": "lore:bran", "entities": ["npc:bran"]},
            {"document_id": "lore:elara", "entities": ["npc:elara"]},
        ],
        "facts": [
            {"id": "fact:bran", "entity_refs": ["npc:bran"]},
            {"id": "fact:elara", "entity_refs": ["npc:elara"]},
        ],
    }
    generated = GeneratedTopic(
        topic_id="npcs",
        entities=({"id": "npc:generated", "name": "Generated", "kind": "npc"},),
        documents=({"document_id": "lore:generated", "entities": ["npc:generated"]},),
        facts=({"id": "fact:generated", "subject": "npc:generated", "entity_refs": ["npc:generated"]},),
    )

    replaced = replace_entity_content(
        content,
        "npc:bran",
        {"id": "npc:bran", "name": "Bran", "kind": "npc", "personality": "steadfast"},
        generated=generated,
    )

    assert [row["id"] for row in replaced["entities"]] == ["npc:bran", "npc:elara"]
    assert {row["document_id"] for row in replaced["documents"]} == {"lore:generated", "lore:elara"}
    generated_fact = next(row for row in replaced["facts"] if row["id"] == "fact:generated")
    assert generated_fact["subject"] == "npc:bran"
    assert generated_fact["entity_refs"] == ["npc:bran"]
    assert any(row["id"] == "fact:elara" for row in replaced["facts"])


def test_entity_reference_validation_rejects_unknown_canon_ids() -> None:
    validate_entity_references(
        {"id": "quest:road", "giver_id": "npc:bran", "location_ids": ["location:market"]},
        {"quest:road", "npc:bran", "location:market"},
    )

    with pytest.raises(ValueError, match="world_entity_dangling_reference:giver_id:npc:missing"):
        validate_entity_references(
            {"id": "quest:road", "giver_id": "npc:missing"},
            {"quest:road", "npc:bran"},
        )
