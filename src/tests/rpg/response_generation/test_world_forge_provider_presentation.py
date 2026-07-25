from app.rpg.session.genesis.world_forge_contract import CampaignTopicNode
from app.rpg.session.genesis.world_forge_fact_pipeline import (
    compile_structured_entity_facts,
)
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg.session.genesis.world_forge_presentation import (
    render_fact_derived_presentations,
)


def _node() -> CampaignTopicNode:
    return CampaignTopicNode(
        topic_id="actors",
        title="Actors and NPCs",
        category="actors",
        visibility="game_master_canon",
        metadata={
            "entity_kind": "actor",
            "field_definitions": [
                {"field_id": "name", "value_type": "string", "required": True},
                {"field_id": "goal", "value_type": "string", "required": True},
                {
                    "field_id": "current_pressure",
                    "value_type": "string",
                    "required": True,
                },
            ],
        },
    )


def test_clean_provider_dossier_is_preserved_with_canonical_details() -> None:
    topic = GeneratedTopic(
        topic_id="actors",
        entities=(
            {
                "id": "actor:nyra_vek",
                "kind": "actor",
                "name": "Nyra Vek",
                "goal": "Expose the Helix Directorate's memory-auction ledger before it is erased.",
                "current_pressure": "A corporate extraction team will reach her safehouse before dawn.",
                "short_summary": (
                    "Nyra Vek is a former mnemonic auditor who now sells stolen memories "
                    "back to the people they were taken from."
                ),
                "dossier": {
                    "schema_version": "rpg_world_entity_dossier_v1",
                    "subtitle": "The auditor who remembers too much",
                    "quote": {
                        "text": "A memory can be evidence, a weapon, or a grave.",
                        "attribution": "Nyra Vek",
                    },
                    "quick_facts": [],
                    "sections": [
                        {
                            "id": "overview",
                            "title": "Overview",
                            "paragraphs": [
                                "Nyra once certified personality backups for the Helix Directorate. "
                                "She defected after discovering that the company was editing witnesses "
                                "and reselling the removed experiences as executive training data."
                            ],
                        },
                        {
                            "id": "backstory",
                            "title": "Backstory",
                            "paragraphs": [
                                "She operates from borrowed rooms above a night market, paying couriers "
                                "with fragments of harmless childhood recollections that cannot be traced."
                            ],
                        },
                    ],
                    "related_entity_ids": [],
                },
                "visibility": "game_master_canon",
            },
        ),
        provenance={"generator": "structured_world_forge_provider_v1"},
    )
    compiled = compile_structured_entity_facts(_node(), topic, {})
    rendered = render_fact_derived_presentations(_node(), compiled)

    entity = rendered.entities[0]
    sections = entity["dossier"]["sections"]
    rendered_text = " ".join(
        paragraph
        for section in sections
        for paragraph in section.get("paragraphs") or ()
    )

    assert entity["short_summary"] == topic.entities[0]["short_summary"]
    assert "mnemonic auditor" in rendered_text
    assert "borrowed rooms above a night market" in rendered_text
    assert any(section["id"].startswith("canonical-details") for section in sections)
    assert entity["dossier"]["provider_authored_presentation"] is True
    assert entity["dossier"]["generated_from_approved_facts"] is True
    assert rendered.provenance["provider_presentations_preserved"] is True
    assert rendered.provenance["provider_presentation_entity_ids"] == ["actor:nyra_vek"]
