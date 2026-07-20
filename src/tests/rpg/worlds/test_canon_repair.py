from app.rpg.session.genesis.canon_audit import audit_generated_canon
from app.rpg.session.genesis.canon_relationships import compile_cross_domain_relationships
from app.rpg.session.genesis.world_forge_generation import (
    GeneratedTopic,
    WorldForgeGenerationResult,
    WorldForgeJobRecord,
)
from app.rpg.session.genesis.world_forge_quality import apply_world_forge_quality_audit
from app.rpg.worlds.canon_repair import repair_generation_contracts


def test_repair_normalizes_live_provider_aliases_into_launch_quality_canon() -> None:
    topic = GeneratedTopic(
        topic_id="locations",
        documents=(
            {
                "document_id": "doc:glitch_bar",
                "title": "The Glitch Bar",
                "content": "A crowded neon bar where mercenaries exchange secrets and contracts.",
            },
        ),
        entities=(
            {
                "entity_id": "loc:glitch_bar",
                "type": "venue",
                "name": "The Glitch Bar",
                "description": "A crowded neon bar filled with flickering signs and synth music.",
            },
        ),
        facts=(
            {
                "fact_id": "fact:glitch_bar_safehouse",
                "statement": "The back room is a neutral meeting place for rival crews.",
                "entity_refs": ["loc:glitch_bar"],
            },
        ),
        provenance={"generator": "test_provider"},
    )
    generation = WorldForgeGenerationResult(
        topics=(topic,),
        jobs=(WorldForgeJobRecord("locations", "completed", (), "world_forge"),),
        failed_topic_ids=(),
        generation_order=(("locations",),),
    )

    repaired = repair_generation_contracts(
        generation,
        starting_location="loc:glitch_bar",
    )
    relationships = compile_cross_domain_relationships(repaired.topics)
    audit = apply_world_forge_quality_audit(
        repaired.topics,
        audit_generated_canon(
            repaired.topics,
            compiled_relationships=relationships,
        ),
    )

    location = next(
        row
        for row in repaired.topics[0].entities
        if row["id"] == "loc:glitch_bar"
    )
    document = repaired.topics[0].documents[0]
    fact = repaired.topics[0].facts[0]
    assert audit.passed, [issue.as_dict() for issue in audit.issues]
    assert location["kind"] == "location"
    assert location["dossier_status"] == "complete"
    assert document["summary_120"]
    assert document["summary_500"]
    assert fact["id"] == "fact:glitch_bar_safehouse"
    assert fact["authority"] == "generated_proposal"
