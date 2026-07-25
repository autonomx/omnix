import pytest

from app.rpg.session.genesis.world_forge_contract import CampaignTopicNode
from app.rpg.session.genesis.world_forge_default import ReferenceSafeWorldForgeGenerator
from app.rpg.session.genesis.world_forge_fact_pipeline import (
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
        title="Actors and NPCs",
        category="actors",
        visibility="game_master_canon",
        target_count=1,
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
                    "field_id": "current_pressure",
                    "value_type": "string",
                    "required": True,
                },
            ],
            "lore_quality": {
                "minimum_words": 40,
                "minimum_paragraph_words": 12,
                "minimum_summary_words": 8,
                "required_sections": ["overview", "backstory"],
            },
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


def _topic(*, contradictory: bool = False, valid_dossier: bool = True) -> GeneratedTopic:
    location_reference = (
        "place:false_moon_base" if contradictory else "place:true_harbor"
    )
    dossier = {
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
                    "She defected after discovering that the company was editing witnesses, "
                    "and she now intends to expose its memory-auction ledger before it is erased."
                ],
            },
            {
                "id": "backstory",
                "title": "Backstory",
                "paragraphs": [
                    "She operates from borrowed rooms above a night market in "
                    f"{location_reference}, paying couriers with harmless childhood recollections. "
                    "A corporate extraction team will reach her safehouse before dawn."
                ],
            },
        ],
        "related_entity_ids": ["place:true_harbor"],
    }
    if not valid_dossier:
        dossier = {"schema_version": "rpg_world_entity_dossier_v1", "sections": []}
    return GeneratedTopic(
        topic_id="actors",
        entities=(
            {
                "id": "actor:nyra_vek",
                "kind": "actor",
                "name": "Nyra Vek",
                "location_id": "place:true_harbor",
                "goal": "Expose the Helix Directorate's memory-auction ledger before it is erased.",
                "current_pressure": "A corporate extraction team will reach her safehouse before dawn.",
                "short_summary": (
                    "Nyra Vek is a former mnemonic auditor who now sells stolen memories "
                    "back to the people they were taken from."
                ),
                "dossier": dossier,
                "visibility": "game_master_canon",
            },
        ),
        provenance={"generator": "structured_world_forge_provider_v1"},
    )


def test_clean_provider_dossier_is_preserved_without_template_prose() -> None:
    topic = _topic()
    compiled = compile_structured_entity_facts(_node(), topic, _dependencies())
    rendered = render_fact_derived_presentations(_node(), compiled)

    entity = rendered.entities[0]
    sections = entity["dossier"]["sections"]
    rendered_text = " ".join(
        paragraph
        for section in sections
        for paragraph in section.get("paragraphs") or ()
    )

    assert entity["short_summary"] == topic.entities[0]["short_summary"]
    assert [section["id"] for section in sections] == ["overview", "backstory"]
    assert "mnemonic auditor" in rendered_text
    assert "borrowed rooms above a night market" in rendered_text
    assert "Goal:" not in rendered_text
    assert "Current Pressure:" not in rendered_text
    assert entity["dossier"]["provider_authored_presentation"] is True
    assert rendered.provenance["provider_presentations_preserved"] is True
    assert rendered.provenance["provider_presentation_entity_ids"] == ["actor:nyra_vek"]


def test_invalid_provider_dossier_requires_regeneration() -> None:
    compiled = compile_structured_entity_facts(
        _node(),
        _topic(valid_dossier=False),
        _dependencies(),
    )
    with pytest.raises(WorldForgeIntegrityError) as raised:
        render_fact_derived_presentations(_node(), compiled)

    assert any(issue.code == "provider_dossier_invalid" for issue in raised.value.issues)


class _SequentialProviderGenerator:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, *args, **kwargs) -> GeneratedTopic:
        self.calls += 1
        return _topic(contradictory=self.calls == 1)


def test_contradictory_provider_lore_retries_llm_instead_of_falling_back() -> None:
    provider = _SequentialProviderGenerator()
    generator = ReferenceSafeWorldForgeGenerator(provider)

    generated = generator.generate(
        _node(),
        seed=7,
        campaign_context={"targeted_regeneration_max_attempts": 2},
        dependency_topics=_dependencies(),
    )

    assert provider.calls == 2
    dossier_text = " ".join(
        paragraph
        for section in generated.entities[0]["dossier"]["sections"]
        for paragraph in section.get("paragraphs") or ()
    )
    assert "place:true_harbor" in dossier_text
    assert "place:false_moon_base" not in dossier_text
    assert generated.provenance["targeted_regeneration_attempt_count"] == 2


def test_exhausted_provider_retries_fail_without_synthetic_lore() -> None:
    class _AlwaysContradictory:
        def generate(self, *args, **kwargs) -> GeneratedTopic:
            return _topic(contradictory=True)

    generator = ReferenceSafeWorldForgeGenerator(_AlwaysContradictory())
    with pytest.raises(WorldForgeIntegrityError):
        generator.generate(
            _node(),
            seed=7,
            campaign_context={"targeted_regeneration_max_attempts": 2},
            dependency_topics=_dependencies(),
        )
