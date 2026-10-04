import pytest

from app.rpg.session.genesis.world_forge_contract import (
    CampaignTopicGraph,
    CampaignTopicNode,
)
from app.rpg.session.genesis.world_forge_fact_pipeline import (
    StructuredFactValidationError,
)
from app.rpg.session.genesis.world_forge_generation import (
    GeneratedTopic,
    WorldForgeGenerationResult,
    WorldForgeJobRecord,
)
from app.rpg.session.genesis.world_forge_integrity import WorldForgeIntegrityError
from app.rpg.worlds.canon_repair import repair_generation_contracts


def _generation(*topics: GeneratedTopic) -> WorldForgeGenerationResult:
    return WorldForgeGenerationResult(
        topics=topics,
        jobs=tuple(
            WorldForgeJobRecord(topic.topic_id, "completed", (), "world_forge")
            for topic in topics
        ),
        failed_topic_ids=(),
        generation_order=tuple((topic.topic_id,) for topic in topics),
    )


def _profile_graph() -> CampaignTopicGraph:
    places = CampaignTopicNode(
        topic_id="places",
        title="Places",
        category="domain",
        metadata={
            "entity_kind": "place",
            "field_definitions": [
                {"field_id": "name", "value_type": "string", "required": True},
                {
                    "field_id": "current_pressure",
                    "value_type": "string",
                    "required": True,
                },
                {
                    "field_id": "observable_evidence",
                    "value_type": "structured_object",
                    "required": True,
                },
            ],
        },
    )
    actors = CampaignTopicNode(
        topic_id="actors",
        title="Actors",
        category="domain",
        dependencies=("places",),
        metadata={
            "entity_kind": "actor",
            "field_definitions": [
                {"field_id": "name", "value_type": "string", "required": True},
                {
                    "field_id": "location_id",
                    "value_type": "entity_ref",
                    "required": True,
                    "allowed_target_domains": ["places"],
                },
                {"field_id": "goal", "value_type": "string", "required": True},
                {
                    "field_id": "dependency",
                    "value_type": "string",
                    "required": True,
                },
                {
                    "field_id": "next_action",
                    "value_type": "string",
                    "required": True,
                },
                {
                    "field_id": "observable_evidence",
                    "value_type": "structured_object",
                    "required": True,
                },
            ],
        },
    )
    return CampaignTopicGraph(
        graph_version="rpg_profile_topic_graph_v1",
        campaign_template="test",
        depth="quick",
        nodes=(places, actors),
        metadata={},
    )


def _place_topic() -> GeneratedTopic:
    return GeneratedTopic(
        topic_id="places",
        entities=(
            {
                "id": "place:harbor",
                "kind": "place",
                "name": "Floodgate Harbor",
                "current_pressure": (
                    "A cracked tidal gate will flood the ferry workshops during the next "
                    "evening surge unless its ceramic seals are replaced."
                ),
                "observable_evidence": {
                    "sign": "Salt water pulses through fresh fractures beneath Pier Seven.",
                    "sound": "Warning bells ring whenever the tide reaches the red marker.",
                },
                "visibility": "public",
            },
        ),
        provenance={"generator": "world_library_manual_authoring"},
    )


def _actor_topic(*, location_id: object = "place:harbor") -> GeneratedTopic:
    return GeneratedTopic(
        topic_id="actors",
        entities=(
            {
                "id": "actor:ada",
                "kind": "actor",
                "name": "Ada Voss",
                "location_id": location_id,
                "goal": (
                    "Restore the tidal warning network before autumn storms isolate the "
                    "outer ferry settlements."
                ),
                "dependency": (
                    "Ada needs three ceramic relay housings controlled by the closed "
                    "municipal ferry workshop."
                ),
                "next_action": (
                    "At first light Ada tests the eastern beacon with a hand-cranked "
                    "signal lamp and records each failed relay."
                ),
                "observable_evidence": {
                    "workbench": "Salt-stained wiring diagrams cover the customs desk.",
                    "route": "Fresh orange cable runs toward the eastern beacon.",
                },
                "description": "Ada secretly commands an orbital fleet.",
                "visibility": "game_master_canon",
            },
        ),
        provenance={"generator": "world_library_manual_authoring"},
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
                "sensory_profile": (
                    "Flickering signs, synth music, hot circuitry, and crowded booths."
                ),
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
                "sensory_profile": (
                    "Flickering signs, synth music, hot circuitry, and crowded booths."
                ),
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

    assert any(
        issue.code == "unknown_geographic_parent" for issue in raised.value.issues
    )


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
                "backstory": (
                    "Ada survived the eastern evacuation and now carries messages "
                    "between isolated settlements."
                ),
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


def test_publication_rejects_manually_corrupted_profile_field_type() -> None:
    with pytest.raises(StructuredFactValidationError) as raised:
        repair_generation_contracts(
            _generation(_place_topic(), _actor_topic(location_id=17)),
            starting_location="place:harbor",
            topic_graph=_profile_graph(),
            generation_context={},
        )

    assert any(
        issue.code == "invalid_structured_field_type"
        and issue.entity_id == "actor:ada"
        and issue.field_id == "location_id"
        for issue in raised.value.issues
    )


def test_publication_rebuilds_profile_dossier_from_structured_fields() -> None:
    validated = repair_generation_contracts(
        _generation(_place_topic(), _actor_topic()),
        starting_location="place:harbor",
        topic_graph=_profile_graph(),
        generation_context={},
    )

    actor = validated.topics[1].entities[0]
    assert "description" not in actor
    assert actor["dossier_status"] == "complete"
    assert actor["dossier"]["generated_from_approved_facts"] is True
    assert actor["presentation_source_fact_ids"]
