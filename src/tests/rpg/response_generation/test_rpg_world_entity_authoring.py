from __future__ import annotations

import pytest

from app.apps.rpg.genesis.forge.world_forge_generation import GeneratedTopic
from app.apps.rpg.genesis.worlds.entity_authoring import (
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


def test_a_bundles_entries_are_edited_and_added_in_the_lists_it_keeps_them_in() -> None:
    """EV-6: a world written by hand or installed from a bundle keeps its people in ``characters`` and its things in
    ``items``, not in ``entities``; the editor lists them there, and edits and adds them there."""
    from app.apps.rpg.genesis.worlds.entity_authoring import entry_list_for

    content = {"title": "People", "characters": [{"id": "npc:liora", "name": "Liora"}, {"id": "npc:orik", "name": "Orik"}],
               "relationship_hooks": ["an old debt"]}
    edited = replace_entity_content(content, "npc:orik", {"id": "npc:orik", "name": "Orik Stonewake"})
    assert edited["characters"] == [{"id": "npc:liora", "name": "Liora"}, {"id": "npc:orik", "name": "Orik Stonewake"}]
    assert "entities" not in edited and edited["relationship_hooks"] == ["an old debt"]
    assert entry_list_for(content) == "characters"  # the one list the topic keeps
    assert entry_list_for({"title": "Empty"}) == "entities"
    assert entry_list_for(content, "items") == "items"
    with pytest.raises(ValueError):
        entry_list_for(content, "secrets")
    with pytest.raises(KeyError):
        replace_entity_content(content, "npc:nobody", {"id": "npc:nobody"})


def test_republishing_a_hand_written_world_carries_its_editors_entries_into_canon() -> None:
    """EV-6: a world with nothing to recompile from was republished as its canon stood, so what its editor changed or
    added never reached play. Each entry goes into the canon list of its name, by id: the editor's fields over the
    canon's (its other fields kept), a new one added with its id in the manifest and the release's index."""
    from app.apps.rpg.genesis.worlds.topic_entries import holds_topic_entries, with_topic_entries

    canon = {"characters": [{"id": "npc:liora", "name": "Liora", "voice": "warm"}], "items": [{"id": "item:rope"}]}
    topics = [{"topic_id": "characters", "status": "ready", "content": {"characters": [
                  {"id": "npc:liora", "name": "Liora Fen"},
                  {"id": "npc:hollis", "name": "Hollis", "authoring_status": "stale", "stale_reason": {}}]}},
              {"topic_id": "bestiary", "status": "ready", "content": {"creatures": [{"id": "creature:wolf"}]}},
              {"topic_id": "draft", "status": "failed", "content": {"items": [{"id": "item:lost"}]}}]
    assert not holds_topic_entries(canon, topics)
    merged, manifest, indexes = with_topic_entries(canon, {"characters": ["npc:liora"]},
                                                   {"character_ids": ["npc:liora"]}, topics)
    assert merged["characters"] == [{"id": "npc:liora", "name": "Liora Fen", "voice": "warm"},
                                    {"id": "npc:hollis", "name": "Hollis"}]  # the editor's own marks left behind
    assert merged["items"] == [{"id": "item:rope"}] and "creatures" not in merged  # no canon list, no failed topic
    assert manifest == {"characters": ["npc:liora", "npc:hollis"]} and indexes == {
        "character_ids": ["npc:liora", "npc:hollis"]}
    assert holds_topic_entries(merged, topics)  # published once, it is reused


def test_a_republished_revision_is_reused_only_while_the_editor_holds_its_entries() -> None:
    """Review: the reuse check compared the stored canon, which play sections rewrite, and only for republished
    revisions. A republished revision records the entries it was made from; one made before that is checked by its
    canon; a stale topic's entries are still the author's; an added entry may name only what the world holds."""
    from app.apps.rpg.genesis.worlds.topic_entries import carries_entries, entries_hash, unresolved

    topics = [{"topic_id": "characters", "status": "stale", "content": {"characters": [
        {"id": "npc:liora", "name": "Liora Fen", "location_id": "location:grove"}]}}]
    recorded = {"canon": {"characters": [{"id": "npc:liora", "name": "Liora (rewritten by play sections)"}]},
                "provenance": {"topic_entries": entries_hash(topics)}}
    assert carries_entries(recorded, topics)  # by what it recorded, whatever its canon now says
    edited = [{**topics[0], "content": {"characters": [{"id": "npc:liora", "name": "Liora"}]}}]
    assert not carries_entries(recorded, edited)
    installed = {"canon": {"characters": [{"id": "npc:liora", "name": "Liora Fen", "location_id": "location:grove"}]},
                 "provenance": {}}
    assert carries_entries(installed, topics) and not carries_entries(installed, edited)  # by its canon
    canon, manifest = {"characters": [{"id": "npc:liora", "name": "Liora"}]}, {"locations": ["location:grove"]}
    assert unresolved(canon, manifest, topics) == []
    lost = [{"topic_id": "characters", "status": "ready", "content": {"characters": [
        {"id": "npc:new", "name": "New", "location_id": "location:nowhere"}]}}]
    assert unresolved(canon, manifest, lost) == [
        "npc:new:world_entity_dangling_reference:location_id:location:nowhere"]


def test_an_edit_keeps_what_in_a_list_is_not_an_entry() -> None:
    content = {"characters": [{"id": "npc:orik", "name": "Orik"}, "npc:liora"]}
    edited = replace_entity_content(content, "npc:orik", {"id": "npc:orik", "name": "Orik Stonewake"})
    assert edited["characters"] == [{"id": "npc:orik", "name": "Orik Stonewake"}, "npc:liora"]
