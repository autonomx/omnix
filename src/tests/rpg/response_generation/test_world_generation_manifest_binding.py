from __future__ import annotations

import pytest

from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg.worlds.generation_manifest_binding import (
    EntityManifestBindingError,
    bind_generated_topic_to_manifest,
    dependency_manifest_aliases,
)


def _slots() -> list[dict]:
    return [
        {
            "slot_id": "slot:actors:001",
            "topic_id": "actors",
            "ordinal": 1,
            "entity_id": "ent:actor:warden",
        },
        {
            "slot_id": "slot:actors:002",
            "topic_id": "actors",
            "ordinal": 2,
            "entity_id": "ent:actor:smuggler",
        },
    ]


def test_ordinal_binding_injects_ids_and_rewrites_all_exact_references() -> None:
    topic = GeneratedTopic(
        topic_id="actors",
        entities=(
            {"id": "provider:one", "name": "Warden", "rival_id": "provider:two"},
            {"id": "provider:two", "name": "Smuggler"},
        ),
        documents=(
            {
                "document_id": "doc:actors",
                "entities": ["provider:one", "provider:two"],
            },
        ),
        facts=(
            {
                "id": "fact:rivalry",
                "entity_refs": ["provider:one", "provider:two"],
            },
        ),
        relationships=(
            {
                "id": "rel:rivalry",
                "source_id": "provider:one",
                "target_id": "provider:two",
            },
        ),
        story_threads=(
            {"id": "thread:rivalry", "actor_ids": ["provider:one", "provider:two"]},
        ),
    )

    bound = bind_generated_topic_to_manifest(
        topic,
        _slots(),
        manifest_hash="sha256:manifest",
    )
    payload = bound.as_dict()

    assert [row["id"] for row in payload["entities"]] == [
        "ent:actor:warden",
        "ent:actor:smuggler",
    ]
    assert [row["manifest_slot_id"] for row in payload["entities"]] == [
        "slot:actors:001",
        "slot:actors:002",
    ]
    assert payload["entities"][0]["rival_id"] == "ent:actor:smuggler"
    assert payload["documents"][0]["entities"] == [
        "ent:actor:warden",
        "ent:actor:smuggler",
    ]
    assert payload["facts"][0]["entity_refs"] == [
        "ent:actor:warden",
        "ent:actor:smuggler",
    ]
    assert payload["relationships"][0]["source_id"] == "ent:actor:warden"
    assert payload["relationships"][0]["target_id"] == "ent:actor:smuggler"
    assert payload["story_threads"][0]["actor_ids"] == [
        "ent:actor:warden",
        "ent:actor:smuggler",
    ]
    binding = payload["provenance"]["entity_manifest_binding"]
    assert binding["binding_mode"] == "ordinal"
    assert binding["manifest_hash"] == "sha256:manifest"
    assert binding["rewritten_provider_ids"]["provider:one"] == "ent:actor:warden"
    assert binding["rewritten_provider_ids"]["provider:two"] == "ent:actor:smuggler"


def test_local_name_slug_aliases_are_rewritten() -> None:
    topic = GeneratedTopic(
        topic_id="actors",
        entities=(
            {"id": "provider:one", "name": "Market Road"},
            {"id": "provider:two", "name": "Whispering Woods"},
        ),
        documents=(
            {
                "document_id": "doc:aliases",
                "entities": ["market_road", "whispering_woods"],
            },
        ),
        facts=(
            {
                "id": "fact:aliases",
                "entity_refs": ["market_road", "whispering_woods"],
            },
        ),
    )

    bound = bind_generated_topic_to_manifest(topic, _slots())

    assert bound.documents[0]["entities"] == [
        "ent:actor:warden",
        "ent:actor:smuggler",
    ]
    assert bound.facts[0]["entity_refs"] == [
        "ent:actor:warden",
        "ent:actor:smuggler",
    ]


def test_dependency_provider_aliases_are_recovered_from_binding_provenance() -> None:
    dependency = GeneratedTopic(
        topic_id="realm",
        entities=({"id": "ent:realm:001", "name": "Eldervale"},),
        provenance={
            "entity_manifest_binding": {
                "rewritten_provider_ids": {
                    "realm_eldervale": "ent:realm:001",
                }
            }
        },
    )
    aliases = dependency_manifest_aliases({"realm": dependency})
    topic = GeneratedTopic(
        topic_id="actors",
        entities=(
            {"id": "provider:one", "name": "One", "realm_id": "realm_eldervale"},
            {"id": "provider:two", "name": "Two"},
        ),
        relationships=(
            {
                "id": "rel:realm",
                "source_id": "provider:one",
                "target_id": "realm_eldervale",
            },
        ),
    )

    bound = bind_generated_topic_to_manifest(
        topic,
        _slots(),
        reference_aliases=aliases,
    )

    assert bound.entities[0]["realm_id"] == "ent:realm:001"
    assert bound.relationships[0]["target_id"] == "ent:realm:001"


def test_slot_keyed_provider_output_is_reordered_to_manifest_order() -> None:
    topic = GeneratedTopic(
        topic_id="actors",
        entities=(
            {
                "id": "provider:smuggler",
                "manifest_slot_id": "slot:actors:002",
                "name": "Smuggler",
            },
            {
                "id": "provider:warden",
                "manifest_slot_id": "slot:actors:001",
                "name": "Warden",
            },
        ),
    )

    bound = bind_generated_topic_to_manifest(topic, _slots())

    assert [row["name"] for row in bound.entities] == ["Warden", "Smuggler"]
    assert [row["id"] for row in bound.entities] == [
        "ent:actor:warden",
        "ent:actor:smuggler",
    ]
    assert bound.provenance["entity_manifest_binding"]["binding_mode"] == "slot_id"


def test_already_canonical_entities_are_reordered_by_entity_id() -> None:
    topic = GeneratedTopic(
        topic_id="actors",
        entities=(
            {"id": "ent:actor:smuggler", "name": "Smuggler"},
            {"id": "ent:actor:warden", "name": "Warden"},
        ),
    )

    bound = bind_generated_topic_to_manifest(topic, _slots())

    assert [row["name"] for row in bound.entities] == ["Warden", "Smuggler"]
    assert bound.provenance["entity_manifest_binding"]["binding_mode"] == "entity_id"


@pytest.mark.parametrize("entity_count", [1, 3])
def test_missing_or_extra_provider_entities_are_rejected(entity_count: int) -> None:
    topic = GeneratedTopic(
        topic_id="actors",
        entities=tuple(
            {"id": f"provider:{index}", "name": f"Actor {index}"}
            for index in range(entity_count)
        ),
    )

    with pytest.raises(
        EntityManifestBindingError,
        match=f"expected=2:actual={entity_count}",
    ):
        bind_generated_topic_to_manifest(topic, _slots())


def test_duplicate_provider_ids_are_rejected() -> None:
    topic = GeneratedTopic(
        topic_id="actors",
        entities=(
            {"id": "provider:duplicate", "name": "One"},
            {"id": "provider:duplicate", "name": "Two"},
        ),
    )

    with pytest.raises(EntityManifestBindingError, match="provider_entity_id_duplicate"):
        bind_generated_topic_to_manifest(topic, _slots())
