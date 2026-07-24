import pytest

from app.rpg.session.genesis.world_forge_generation import (
    GeneratedTopic,
    WorldForgeGenerationResult,
    WorldForgeJobRecord,
)
from app.rpg.session.genesis.world_forge_integrity import WorldForgeIntegrityError
from app.rpg.worlds.canon_repair import repair_generation_contracts


def _generation(topic: GeneratedTopic) -> WorldForgeGenerationResult:
    return WorldForgeGenerationResult(
        topics=(topic,),
        jobs=(WorldForgeJobRecord(topic.topic_id, "completed", (), "world_forge"),),
        failed_topic_ids=(),
        generation_order=((topic.topic_id,),),
    )


def test_publication_normalizes_alias_fields_without_changing_meaning() -> None:
    topic = GeneratedTopic(
        topic_id="locations",
        documents=(
            {
                "document_id": "doc:glitch_bar",
                "title": "The Glitch Bar",
                "content": "A crowded neon bar where mercenaries exchange secrets and contracts.",
                "summary_120": "A neon mercenary bar.",
                "summary_500": "A crowded neon bar used by mercenaries and rival crews.",
                "visibility": "public",
                "entities": ["location:glitch_bar"],
            },
        ),
        entities=(
            {
                "entity_id": "location:glitch_bar",
                "kind": "location",
                "name": "The Glitch Bar",
                "region_id": "region:night_city",
                "sensory_profile": "Flickering signs, synth music, hot circuitry, and crowded booths.",
                "dossier_status": "complete",
                "visibility": "public",
            },
            {
                "id": "region:night_city",
                "kind": "region",
                "name": "Night City",
                "visibility": "public",
            },
        ),
        facts=(
            {
                "fact_id": "fact:glitch_bar_safehouse",
                "statement": "The back room is a neutral meeting place for rival crews.",
                "entity_refs": ["location:glitch_bar"],
                "authority": "generated_proposal",
                "approved_authority": "objective_canon",
                "visibility": "game_master_canon",
            },
        ),
        provenance={"generator": "test_provider"},
    )

    normalized = repair_generation_contracts(
        _generation(topic),
        starting_location="location:glitch_bar",
    )

    location = normalized.topics[0].entities[0]
    document = normalized.topics[0].documents[0]
    fact = normalized.topics[0].facts[0]
    assert location["id"] == "location:glitch_bar"
    assert document["full_text"].startswith("A crowded neon bar")
    assert fact["id"] == "fact:glitch_bar_safehouse"
    assert fact["content"].startswith("The back room")


def test_publication_does_not_reparent_invalid_location() -> None:
    topic = GeneratedTopic(
        topic_id="locations",
        entities=(
            {
                "id": "location:glitch_bar",
                "kind": "location",
                "name": "The Glitch Bar",
                "region_id": "region:missing",
                "sensory_profile": "Flickering signs, synth music, hot circuitry, and crowded booths.",
                "dossier_status": "complete",
                "visibility": "public",
            },
        ),
        provenance={"generator": "test_provider"},
    )

    with pytest.raises(WorldForgeIntegrityError) as raised:
        repair_generation_contracts(
            _generation(topic),
            starting_location="location:glitch_bar",
        )

    assert any(issue.code == "unknown_geographic_parent" for issue in raised.value.issues)


def test_publication_does_not_drop_dangling_relationship() -> None:
    topic = GeneratedTopic(
        topic_id="relationships",
        entities=(
            {
                "id": "npc:ada",
                "kind": "npc",
                "name": "Ada",
                "appearance": "A weathered courier in a patched radiation cloak.",
                "personality": "Alert, patient, and unwilling to trust easy promises.",
                "backstory": "Ada survived the eastern evacuation and now carries messages between isolated settlements.",
                "speech_style": "Measured and precise.",
                "goals": ["reopen the eastern route"],
                "motives": ["duty"],
                "faction_ids": [],
                "secrets": [],
                "known_facts": [],
                "mobility_status": "itinerant",
                "dossier_status": "complete",
                "visibility": "game_master_canon",
            },
        ),
        relationships=(
            {
                "id": "relationship:ada:missing",
                "source_id": "npc:ada",
                "target_id": "faction:missing",
                "kind": "opposes",
                "visibility": "game_master_canon",
            },
        ),
        provenance={"generator": "test_provider"},
    )

    with pytest.raises(WorldForgeIntegrityError) as raised:
        repair_generation_contracts(_generation(topic), starting_location="")

    assert any(
        issue.code == "dangling_relationship_endpoint" for issue in raised.value.issues
    )
