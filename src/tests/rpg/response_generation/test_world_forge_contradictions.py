from app.rpg.session.genesis.world_forge_contract import CampaignTopicNode
from app.rpg.session.genesis.world_forge_contradictions import (
    audit_presentation_contradictions,
)
from app.rpg.session.genesis.world_forge_fact_pipeline import (
    compile_structured_entity_facts,
)
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg.session.genesis.world_forge_presentation import (
    render_fact_derived_presentations,
)


def test_explicit_wrong_reference_in_prose_is_reported_and_quarantined() -> None:
    node = CampaignTopicNode(
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
            ],
        },
    )
    places = GeneratedTopic(
        topic_id="places",
        entities=(
            {"id": "place:right", "kind": "place", "name": "Right Harbor"},
            {"id": "place:wrong", "kind": "place", "name": "Wrong Harbor"},
        ),
    )
    topic = GeneratedTopic(
        topic_id="actors",
        entities=(
            {
                "id": "actor:ada",
                "kind": "actor",
                "name": "Ada",
                "location_id": "place:right",
                "goal": "Restore the eastern beacon before the storm surge.",
                "description": "Ada is permanently stationed at place:wrong.",
            },
        ),
        documents=(
            {
                "document_id": "document:ada",
                "topic_id": "actors",
                "title": "Ada Biography",
                "full_text": "Ada reports every night to place:wrong.",
                "summary_500": "Ada reports to place:wrong.",
                "summary_120": "Ada reports to place:wrong.",
                "entities": ["actor:ada"],
                "visibility": "game_master_canon",
            },
        ),
        provenance={"generator": "structured_world_forge_provider_v1"},
    )
    compiled = compile_structured_entity_facts(
        node,
        topic,
        {"places": places},
    )
    report = audit_presentation_contradictions(node, compiled)
    assert report.passed is False
    assert len(report.contradictions) == 2
    assert all(
        item.canonical_reference_ids == ("place:right",)
        for item in report.contradictions
    )
    assert all(
        item.conflicting_reference_ids == ("place:wrong",)
        for item in report.contradictions
    )

    rendered = render_fact_derived_presentations(node, compiled)
    stored_report = rendered.provenance["presentation_contradiction_report"]
    assert stored_report["passed"] is False
    assert "description" not in rendered.entities[0]
    assert rendered.documents[0]["authority"] == "presentation_only"
    assert rendered.documents[0]["presentation_contradictions"]
