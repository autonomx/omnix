from app.rpg.session.genesis.world_forge_contract import CampaignTopicNode
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg.session.genesis.world_forge_lore_quality import (
    lore_quality_contract,
    provider_lore_quality_issues,
    require_provider_lore_quality,
)


def _node() -> CampaignTopicNode:
    return CampaignTopicNode(
        topic_id="actors",
        title="Actors and NPCs",
        category="actors",
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
            "lore_quality": {
                "minimum_words": 90,
                "minimum_paragraph_words": 12,
                "minimum_summary_words": 10,
                "required_sections": ["overview", "backstory", "goals"],
            },
        },
    )


def _good_topic() -> GeneratedTopic:
    return GeneratedTopic(
        topic_id="actors",
        entities=(
            {
                "id": "actor:nyra_vek",
                "kind": "actor",
                "name": "Nyra Vek",
                "goal": "Expose the Helix Directorate memory-auction ledger before the archive is erased.",
                "current_pressure": "A corporate extraction team will reach Nyra's night-market safehouse before dawn.",
                "short_summary": (
                    "Nyra Vek is a former mnemonic auditor who returns stolen memories to "
                    "the people the Helix Directorate erased."
                ),
                "dossier": {
                    "schema_version": "rpg_world_entity_dossier_v1",
                    "quick_facts": [],
                    "sections": [
                        {
                            "id": "overview",
                            "title": "Overview",
                            "paragraphs": [
                                "Nyra Vek once certified personality backups for the Helix Directorate, "
                                "where she discovered that executives were editing witnesses and selling "
                                "the removed experiences as training data for corporate negotiators."
                            ],
                        },
                        {
                            "id": "backstory",
                            "title": "Backstory",
                            "paragraphs": [
                                "She now works from a concealed room above the night market, exchanging "
                                "harmless childhood recollections for food, access codes, and couriers who "
                                "can move evidence without entering the Directorate's surveillance grid."
                            ],
                        },
                        {
                            "id": "goals",
                            "title": "Goals and Immediate Pressure",
                            "paragraphs": [
                                "Nyra intends to expose the Helix Directorate memory-auction ledger before "
                                "the archive is erased, but a corporate extraction team will reach her "
                                "night-market safehouse before dawn and force an immediate choice."
                            ],
                        },
                    ],
                    "related_entity_ids": [],
                },
            },
        ),
        provenance={"generator": "structured_world_forge_provider_v1"},
    )


def test_contract_is_explicitly_headed_and_paragraph_based() -> None:
    contract = lore_quality_contract(_node())
    assert contract["required_sections"] == ["overview", "backstory", "goals"]
    assert contract["minimum_words"] == 90
    assert any("titled sections" in rule for rule in contract["rules"])


def test_detailed_provider_lore_passes_without_rewriting() -> None:
    topic = _good_topic()
    assert provider_lore_quality_issues(_node(), topic) == ()
    assert require_provider_lore_quality(_node(), topic) is topic


def test_thin_generic_or_unheaded_lore_is_retryable() -> None:
    topic = GeneratedTopic(
        topic_id="actors",
        entities=(
            {
                "id": "actor:ash",
                "kind": "actor",
                "name": "Ash Actor",
                "goal": "Restore the Ash network before the next public assembly.",
                "current_pressure": "An Ash shortage will disrupt a named route during the next cycle.",
                "short_summary": "Ash actor.",
                "dossier": {
                    "schema_version": "rpg_world_entity_dossier_v1",
                    "sections": [
                        {
                            "id": "overview",
                            "title": "Overview",
                            "paragraphs": [
                                "Within the wider world, the concerns gathered under overview provide meaningful material for play."
                            ],
                        }
                    ],
                },
            },
        ),
        provenance={"generator": "structured_world_forge_provider_v1"},
    )

    codes = {
        issue.code for issue in provider_lore_quality_issues(_node(), topic)
    }
    assert "provider_lore_summary_too_short" in codes
    assert "provider_lore_required_sections_missing" in codes
    assert "provider_lore_paragraph_too_short" in codes
    assert "provider_lore_total_too_short" in codes
    assert "provider_lore_generic_or_deterministic_filler" in codes
    assert "provider_lore_field_not_explained" in codes


def test_field_label_fragments_are_not_accepted_as_paragraphs() -> None:
    topic = _good_topic()
    entity = dict(topic.entities[0])
    dossier = dict(entity["dossier"])
    sections = [dict(section) for section in dossier["sections"]]
    sections[2] = {
        **sections[2],
        "paragraphs": [
            "Goal: Expose the Helix Directorate memory-auction ledger before the archive is erased while the extraction team closes in."
        ],
    }
    dossier["sections"] = sections
    entity["dossier"] = dossier
    broken = GeneratedTopic(
        topic_id=topic.topic_id,
        entities=(entity,),
        provenance=topic.provenance,
    )

    assert any(
        issue.code == "provider_lore_field_label_fragment"
        for issue in provider_lore_quality_issues(_node(), broken)
    )
