import pytest

from app.rpg.session.genesis.world_forge_contract import CampaignTopicNode
from app.rpg.session.genesis.world_forge_fact_pipeline import (
    StructuredFactValidationError,
    compile_structured_entity_facts,
)
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic


def _node() -> CampaignTopicNode:
    return CampaignTopicNode(
        topic_id="actors",
        title="Actors",
        category="domain",
        metadata={
            "entity_kind": "actor",
            "field_definitions": [
                {
                    "field_id": "name",
                    "value_type": "string",
                    "required": True,
                    "allowed_target_domains": [],
                },
                {
                    "field_id": "location_id",
                    "value_type": "entity_ref",
                    "required": True,
                    "allowed_target_domains": ["places"],
                },
                {
                    "field_id": "next_action",
                    "value_type": "string",
                    "required": True,
                    "allowed_target_domains": [],
                },
                {
                    "field_id": "reaction_conditions",
                    "value_type": "structured_object",
                    "required": True,
                    "allowed_target_domains": [],
                },
            ],
        },
    )


def _dependencies() -> dict[str, GeneratedTopic]:
    return {
        "places": GeneratedTopic(
            topic_id="places",
            entities=(
                {
                    "id": "place:harbor",
                    "name": "Harbor",
                    "kind": "place",
                },
            ),
        )
    }


def _topic(**overrides: object) -> GeneratedTopic:
    entity = {
        "id": "actor:ada",
        "kind": "actor",
        "name": "Ada Voss",
        "location_id": "place:harbor",
        "next_action": "Inspect the disabled ferry beacon before dawn.",
        "reaction_conditions": {
            "beacon_repaired": "Warn the harbor council",
            "beacon_destroyed": "Track the saboteur",
        },
        "visibility": "game_master_canon",
    }
    entity.update(overrides)
    return GeneratedTopic(
        topic_id="actors",
        entities=(entity,),
        provenance={"generator": "structured_world_forge_provider_v1"},
    )


def test_validated_fields_become_field_level_canon_proposals() -> None:
    compiled = compile_structured_entity_facts(_node(), _topic(), _dependencies())
    facts = {row["field_id"]: row for row in compiled.facts}

    assert facts["location_id"]["object"] == "place:harbor"
    assert facts["location_id"]["entity_refs"] == ["actor:ada", "place:harbor"]
    assert facts["next_action"]["authority"] == "generated_proposal"
    assert facts["next_action"]["approved_authority"] == "objective_canon"
    assert compiled.provenance["structured_facts_validated"] is True


def test_missing_required_field_fails_before_dossier_generation() -> None:
    with pytest.raises(StructuredFactValidationError) as raised:
        compile_structured_entity_facts(
            _node(),
            _topic(next_action=""),
            _dependencies(),
        )

    assert any(
        issue.code == "missing_required_structured_field"
        and issue.field_id == "next_action"
        for issue in raised.value.issues
    )


def test_wrong_field_type_fails() -> None:
    with pytest.raises(StructuredFactValidationError) as raised:
        compile_structured_entity_facts(
            _node(),
            _topic(reaction_conditions="whenever convenient"),
            _dependencies(),
        )

    assert any(
        issue.code == "invalid_structured_field_type"
        and issue.field_id == "reaction_conditions"
        for issue in raised.value.issues
    )


def test_typed_reference_must_resolve_in_allowed_domain() -> None:
    with pytest.raises(StructuredFactValidationError) as raised:
        compile_structured_entity_facts(
            _node(),
            _topic(location_id="place:missing"),
            _dependencies(),
        )

    issue = next(
        issue
        for issue in raised.value.issues
        if issue.code == "unresolved_typed_reference"
    )
    assert issue.field_id == "location_id"
    assert issue.supplied_value == "place:missing"


def test_profile_entity_kind_must_match() -> None:
    with pytest.raises(StructuredFactValidationError) as raised:
        compile_structured_entity_facts(
            _node(),
            _topic(kind="npc"),
            _dependencies(),
        )

    assert any(
        issue.code == "profile_entity_kind_mismatch"
        for issue in raised.value.issues
    )
