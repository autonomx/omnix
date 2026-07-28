import pytest

from app.rpg.session.genesis.world_forge_contract import CampaignTopicNode
from app.rpg.session.genesis.world_forge_contradictions import (
    audit_presentation_contradictions,
)
from app.rpg.session.genesis.world_forge_fact_pipeline import (
    compile_structured_entity_facts,
)
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg.session.genesis.world_forge_integrity import WorldForgeIntegrityError
from app.rpg.session.genesis.world_forge_presentation import (
    render_fact_derived_presentations,
)


def test_explicit_wrong_reference_in_prose_is_reported_and_retried() -> None:
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
                "short_summary": "Ada maintains the eastern beacon before each storm surge.",
                "description": "Ada is permanently stationed at place:wrong.",
                "dossier": {
                    "schema_version": "rpg_world_entity_dossier_v1",
                    "sections": [
                        {
                            "id": "overview",
                            "title": "Overview",
                            "paragraphs": ["Ada reports every night to place:wrong."],
                        }
                    ],
                },
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
    assert len(report.contradictions) == 3
    assert all(
        item.canonical_reference_ids == ("place:right",)
        for item in report.contradictions
    )
    assert all(
        item.conflicting_reference_ids == ("place:wrong",)
        for item in report.contradictions
    )

    with pytest.raises(WorldForgeIntegrityError) as raised:
        render_fact_derived_presentations(node, compiled)

    contradiction_issues = [
        issue
        for issue in raised.value.issues
        if issue.code == "provider_presentation_contradiction"
    ]
    assert len(contradiction_issues) == 3
    assert all(issue.field == "entities" for issue in contradiction_issues)
