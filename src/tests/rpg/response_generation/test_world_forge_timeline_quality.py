from app.rpg.session.genesis.world_forge_contract import CampaignTopicNode
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg.session.genesis.world_forge_lore_scoring import assess_provider_lore_quality
from app.rpg.session.genesis.world_forge_timeline_quality import (
    timeline_lore_quality_issues,
)


def _node() -> CampaignTopicNode:
    return CampaignTopicNode(
        topic_id="history_timeline",
        title="History and Timeline",
        category="lore",
        metadata={
            "lore_quality": {
                "minimum_words": 240,
                "minimum_paragraph_words": 20,
                "minimum_summary_words": 12,
                "required_sections": [
                    "overview",
                    "date-and-context",
                    "causes",
                    "event",
                    "participants-and-places",
                    "immediate-consequences",
                    "long-term-legacy",
                    "sources-and-uncertainty",
                ],
            }
        },
    )


def _rich_topic() -> GeneratedTopic:
    paragraphs = {
        "overview": "The Night of Broken Antennas ended the citywide information monopoly and became the event by which residents date the modern civic era. Its effects remain visible in district law, memorial architecture, and the suspicion directed at every centralized network.",
        "date-and-context": "The uprising began on 17 Rainfall 2084, during the third week of the Helix Directorate's communications rationing. Rolling blackouts had isolated the eastern districts while company broadcasters insisted that service remained stable and blamed local technicians for deliberate sabotage.",
        "causes": "Years of escalating subscription debt, censored emergency warnings, and forced identity verification created the conditions for revolt. The immediate trigger came when Directorate security seized a community relay and allowed a hospital ward to lose contact with its volunteer power crews.",
        "event": "Technicians, couriers, and neighborhood defenders climbed the transmission towers and physically severed the Directorate's encrypted antenna trunks. Independent mesh nodes came online district by district, carrying medical requests, witness recordings, and instructions for avoiding advancing security teams.",
        "participants-and-places": "The central actions occurred at Crown Spire, the Lowmarket exchange, and three rooftop relay farms. Union signal engineer Mara Venn coordinated the technical crews, while dock collectives protected access routes and student broadcasters preserved evidence of the Directorate response.",
        "immediate-consequences": "For six days the city operated through improvised local networks, and the Directorate lost both surveillance coverage and control of public messaging. Security units withdrew after several commanders realized that their private communications were being rebroadcast to the population in real time.",
        "long-term-legacy": "The settlement created the Civic Mesh Charter, limited corporate ownership of emergency infrastructure, and established elected relay stewards in every district. Modern activists invoke the uprising whenever authorities propose centralized identity systems, while corporations fund campaigns portraying the event as reckless technological vandalism.",
        "sources-and-uncertainty": "Most surviving accounts come from mesh archives, union testimony, and heavily edited Directorate tribunal records. Historians still dispute whether Mara Venn planned the first tower seizure or merely coordinated a movement already underway, and several districts claim their relay activated first.",
    }
    return GeneratedTopic(
        topic_id="history_timeline",
        entities=(
            {
                "id": "historical_event:broken_antennas",
                "kind": "historical_event",
                "name": "The Night of Broken Antennas",
                "date_label": "17 Rainfall 2084",
                "chronology_index": 12,
                "cause": "Communications rationing and the seizure of a community relay.",
                "participants": ["Mara Venn", "dock collectives", "student broadcasters"],
                "consequences": "The Civic Mesh Charter and elected relay stewardship.",
                "legacy": "A lasting prohibition against centralized emergency communications.",
                "sources": "Mesh archives, union testimony, and contested tribunal records.",
                "short_summary": "The Night of Broken Antennas shattered the Helix Directorate's communications monopoly and established the decentralized Civic Mesh Charter still governing emergency networks.",
                "dossier": {
                    "schema_version": "rpg_world_entity_dossier_v1",
                    "sections": [
                        {
                            "id": section_id,
                            "title": section_id.replace("-", " ").title(),
                            "paragraphs": [paragraph],
                        }
                        for section_id, paragraph in paragraphs.items()
                    ],
                    "related_entity_ids": [],
                },
            },
        ),
        provenance={"generator": "structured_world_forge_provider_v1"},
    )


def test_rich_dated_event_passes_timeline_quality() -> None:
    topic = _rich_topic()
    assert timeline_lore_quality_issues(_node(), topic) == ()
    assessment = assess_provider_lore_quality(_node(), topic)
    assert assessment.passed is True
    assert assessment.score >= 80


def test_one_line_dated_event_scores_below_threshold() -> None:
    topic = GeneratedTopic(
        topic_id="history_timeline",
        entities=(
            {
                "id": "historical_event:fall",
                "kind": "historical_event",
                "name": "The Fall",
                "year": 2084,
                "short_summary": "The city fell after a battle.",
                "dossier": {
                    "schema_version": "rpg_world_entity_dossier_v1",
                    "sections": [
                        {
                            "id": "overview",
                            "title": "Overview",
                            "paragraphs": ["The city fell after a short battle and the survivors fled."],
                        }
                    ],
                },
            },
        ),
        provenance={"generator": "structured_world_forge_provider_v1"},
    )

    codes = {issue.code for issue in timeline_lore_quality_issues(_node(), topic)}
    assert "provider_timeline_entry_too_short" in codes
    assert "provider_timeline_entry_insufficient_narrative" in codes
    assert "provider_timeline_cause_missing" in codes
    assert "provider_timeline_consequences_missing" in codes
    assert "provider_timeline_legacy_missing" in codes
    assert assess_provider_lore_quality(_node(), topic).score < 80


def test_document_only_history_requires_structured_timeline_entries() -> None:
    topic = GeneratedTopic(
        topic_id="history_timeline",
        documents=(
            {
                "title": "History",
                "full_text": "A short general history without individually dated events.",
            },
        ),
        provenance={"generator": "structured_world_forge_provider_v1"},
    )

    codes = {issue.code for issue in timeline_lore_quality_issues(_node(), topic)}
    assert "provider_timeline_document_too_short" in codes
    assert "provider_timeline_entries_missing" in codes
