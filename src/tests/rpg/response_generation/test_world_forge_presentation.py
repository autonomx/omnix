import pytest

from app.rpg.session.genesis.world_forge_contract import CampaignTopicNode
from app.rpg.session.genesis.world_forge_fact_pipeline import (
    StructuredFactValidationError,
    compile_structured_entity_facts,
)
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg.session.genesis.world_forge_integrity import WorldForgeIntegrityError
from app.rpg.session.genesis.world_forge_presentation import (
    render_fact_derived_presentations,
)


def _node() -> CampaignTopicNode:
    return CampaignTopicNode(
        topic_id="actors",
        title="Actors",
        category="domain",
        visibility="game_master_canon",
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
                {"field_id": "dependency", "value_type": "string", "required": True},
                {"field_id": "next_action", "value_type": "string", "required": True},
                {
                    "field_id": "observable_evidence",
                    "value_type": "structured_object",
                    "required": True,
                },
            ],
        },
    )


def _dependencies() -> dict[str, GeneratedTopic]:
    return {
        "places": GeneratedTopic(
            topic_id="places",
            entities=(
                {"id": "place:true_harbor", "kind": "place", "name": "True Harbor"},
            ),
        )
    }


def _provider_topic(*, contradictory: bool = False) -> GeneratedTopic:
    location_text = (
        "Ada works from place:false_moon_base and commands a battleship."
        if contradictory
        else "Ada works from the customs office overlooking the eastern beacon."
    )
    return GeneratedTopic(
        topic_id="actors",
        documents=(
            {
                "document_id": "document:ada",
                "title": "Ada Voss Biography",
                "full_text": "Ada maintains the tidal warning network from the old customs office.",
                "summary_120": "A harbor engineer under mounting pressure.",
                "summary_500": "Ada is racing to restore the warning network before the autumn storms.",
                "visibility": "game_master_canon",
                "entities": ["actor:ada"],
            },
        ),
        entities=(
            {
                "id": "actor:ada",
                "kind": "actor",
                "name": "Ada Voss",
                "location_id": "place:true_harbor",
                "goal": "Restore the harbor's tidal warning network before the autumn storms.",
                "dependency": "She needs three ceramic relay housings from the closed ferry workshop.",
                "next_action": "At first light she tests the eastern beacon with a hand-cranked signal lamp.",
                "observable_evidence": {
                    "workbench": "Salt-stained wiring diagrams cover the customs office table",
                    "route": "Fresh orange cable runs toward the eastern beacon",
                },
                "short_summary": (
                    "Ada Voss is the last engineer still maintaining True Harbor's tidal warning grid."
                ),
                "description": "A patient engineer with a reputation for repairing impossible systems.",
                "secret_untyped_claim": "Ada once sabotaged a corporate inspection drone.",
                "dossier": {
                    "schema_version": "rpg_world_entity_dossier_v1",
                    "quick_facts": [],
                    "sections": [
                        {
                            "id": "overview",
                            "title": "Overview",
                            "paragraphs": [location_text],
                        },
                        {
                            "id": "backstory",
                            "title": "Backstory",
                            "paragraphs": [
                                "She inherited the station from a retired signal keeper who taught her to read storms by sound."
                            ],
                        },
                    ],
                    "related_entity_ids": ["place:true_harbor"],
                },
                "visibility": "game_master_canon",
            },
        ),
        facts=(
            {
                "id": "fact:unverified_sabotage",
                "subject": "actor:ada",
                "content": "Ada once sabotaged a corporate inspection drone.",
                "authority": "generated_proposal",
                "approved_authority": "objective_canon",
                "entity_refs": ["actor:ada"],
            },
        ),
        provenance={"generator": "structured_world_forge_provider_v1"},
    )


def _compiled_topic(*, contradictory: bool = False) -> GeneratedTopic:
    return compile_structured_entity_facts(
        _node(),
        _provider_topic(contradictory=contradictory),
        _dependencies(),
    )


def test_contradictory_provider_prose_is_rejected_for_regeneration() -> None:
    with pytest.raises(WorldForgeIntegrityError) as raised:
        render_fact_derived_presentations(
            _node(),
            _compiled_topic(contradictory=True),
        )

    assert any(
        issue.code == "provider_presentation_contradiction"
        and issue.field == "entities"
        for issue in raised.value.issues
    )


def test_clean_dossier_preserves_provider_prose_and_structured_fields() -> None:
    rendered = render_fact_derived_presentations(_node(), _compiled_topic())
    entity = rendered.entities[0]
    dossier_text = " ".join(
        paragraph
        for section in entity["dossier"]["sections"]
        for paragraph in section.get("paragraphs") or ()
    )

    assert entity["location_id"] == "place:true_harbor"
    assert "customs office overlooking the eastern beacon" in dossier_text
    assert "Current Pressure:" not in dossier_text
    assert entity["dossier"]["provider_authored_presentation"] is True
    assert rendered.provenance["presentation_derived_from_structured_facts"] is False


def test_untyped_entity_claims_are_not_canonical_entity_fields() -> None:
    rendered = render_fact_derived_presentations(_node(), _compiled_topic())
    entity = rendered.entities[0]
    assert "secret_untyped_claim" not in entity
    assert "description" not in entity
    assert set(entity).issuperset(
        {"id", "kind", "name", "location_id", "goal", "dependency", "next_action"}
    )


def test_non_structured_facts_are_quarantined_as_proposals() -> None:
    rendered = render_fact_derived_presentations(_node(), _compiled_topic())
    assert all(
        fact["source"] == "profile_structured_fact_compiler_v1"
        for fact in rendered.facts
    )
    proposals = rendered.provenance["presentation_fact_proposals"]
    assert any(
        proposal["status"] == "non_canonical_fact_proposal"
        and proposal["value"]["id"] == "fact:unverified_sabotage"
        for proposal in proposals
    )
    assert rendered.provenance["discarded_noncanonical_fact_count"] == 1


def test_documents_are_explicitly_presentation_only() -> None:
    rendered = render_fact_derived_presentations(_node(), _compiled_topic())
    document = rendered.documents[0]
    assert document["authority"] == "presentation_only"
    assert document["canonical_source_fact_ids"]


def test_missing_structured_source_facts_blocks_presentation() -> None:
    topic = _provider_topic()
    with pytest.raises(StructuredFactValidationError) as raised:
        render_fact_derived_presentations(_node(), topic)
    assert any(
        issue.code == "presentation_source_facts_missing"
        for issue in raised.value.issues
    )
