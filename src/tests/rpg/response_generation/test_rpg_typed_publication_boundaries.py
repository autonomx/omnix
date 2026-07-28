from __future__ import annotations

import pytest

from app.rpg.narrative_engine.world_forge import (
    WorldForgeProposal,
    validate_world_forge_proposal_for_publication,
)
from app.rpg.session.genesis.world_forge_generation import (
    GeneratedTopic,
    validate_generated_topic_for_publication,
)


def test_generated_topic_rejects_non_object_rows_instead_of_dropping_them() -> None:
    with pytest.raises(ValueError, match=r"entities\[0\]_must_be_object"):
        GeneratedTopic.from_dict(
            {
                "topic_id": "npcs",
                "documents": [],
                "entities": ["not-an-object"],
                "facts": [],
                "relationships": [],
                "knowledge_rules": [],
                "story_threads": [],
                "provenance": {},
            }
        )


def test_generated_topic_publication_requires_expected_identity() -> None:
    topic = GeneratedTopic(topic_id="realm")

    with pytest.raises(ValueError, match="topic_id_mismatch"):
        validate_generated_topic_for_publication(
            topic,
            expected_topic_id="regions",
        )


def test_generated_topic_publication_returns_validation_receipt() -> None:
    topic = GeneratedTopic(
        topic_id="realm",
        provenance={"structured_contract": "rpg.world_forge.topic.v3"},
    )

    validated = validate_generated_topic_for_publication(
        topic,
        expected_topic_id="realm",
    )

    assert validated.topic.topic_id == "realm"
    assert validated.receipt.schema_version == "rpg_generated_topic_domain_v2"
    assert validated.receipt.source_contract == "rpg.world_forge.topic.v3"


def test_world_forge_proposal_rejects_non_object_rows() -> None:
    with pytest.raises(ValueError, match=r"facts\[0\]_must_be_object"):
        WorldForgeProposal.from_dict(
            {
                "proposal_id": "proposal:test",
                "campaign_id": "campaign:test",
                "base_bible_revision": 1,
                "entities": [],
                "facts": [42],
                "relationships": [],
                "retrieval_cards": [],
                "provenance": {},
            }
        )


def test_world_forge_proposal_rejects_coerced_revision() -> None:
    with pytest.raises(ValueError, match="base_bible_revision_must_be_integer"):
        WorldForgeProposal.from_dict(
            {
                "proposal_id": "proposal:test",
                "campaign_id": "campaign:test",
                "base_bible_revision": "1",
            }
        )


def test_world_forge_proposal_publication_returns_validation_receipt() -> None:
    proposal = WorldForgeProposal(
        proposal_id="proposal:test",
        campaign_id="campaign:test",
        base_bible_revision=1,
    )

    validated = validate_world_forge_proposal_for_publication(proposal)

    assert validated.proposal.proposal_id == "proposal:test"
    assert validated.receipt.schema_version == "rpg_world_forge_proposal_domain_v2"
    assert validated.receipt.proposal_hash == proposal.proposal_hash
