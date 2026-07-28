import pytest

from app.rpg.session.genesis.world_forge_contract import CampaignTopicNode
from app.rpg.session.genesis.world_forge_default import ReferenceSafeWorldForgeGenerator
from app.rpg.session.genesis.world_forge_fact_pipeline import (
    StructuredFactIssue,
    StructuredFactValidationError,
)
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg.session.genesis.world_forge_regeneration import (
    enforce_targeted_regeneration,
    generate_with_targeted_regeneration,
    regeneration_request_from_error,
)


class RecordingGenerator:
    def __init__(self, *, provider: bool = True, always_bad: bool = False) -> None:
        self.provider = provider
        self.always_bad = always_bad
        self.contexts: list[dict] = []

    def generate(
        self,
        node: CampaignTopicNode,
        *,
        seed: int,
        campaign_context: dict,
        dependency_topics: dict,
    ) -> GeneratedTopic:
        del seed, dependency_topics
        self.contexts.append(dict(campaign_context))
        targeted = campaign_context.get("targeted_regeneration")
        action = (
            "Wait."
            if self.always_bad or not targeted
            else "Inspect the flooded relay chamber before the evening tide."
        )
        return GeneratedTopic(
            topic_id=node.topic_id,
            entities=(
                {
                    "id": "actor:ada",
                    "kind": "actor",
                    "name": "Mutated Ada" if targeted else "Ada",
                    "next_action": action,
                },
                {
                    "id": "actor:bram",
                    "kind": "actor",
                    "name": "Mutated Bram" if targeted else "Bram",
                    "next_action": (
                        "Abandon the harbor without warning."
                        if targeted
                        else "Recalibrate the harbor crane after the noon shift."
                    ),
                },
            ),
            provenance={
                "generator": (
                    "structured_world_forge_provider_v1"
                    if self.provider
                    else "deterministic_structured_domain_v1"
                )
            },
        )


def _node() -> CampaignTopicNode:
    return CampaignTopicNode(topic_id="actors", title="Actors", category="domain")


def _process(topic: GeneratedTopic) -> GeneratedTopic:
    if topic.entities[0]["next_action"] == "Wait.":
        raise StructuredFactValidationError(
            (
                StructuredFactIssue(
                    code="weak_operational_state",
                    topic_id="actors",
                    entity_id="actor:ada",
                    field_id="next_action",
                    message="Replace the placeholder with a concrete near-term action.",
                    supplied_value="Wait.",
                ),
            )
        )
    return topic


def test_live_failure_generates_targeted_request_and_retries() -> None:
    generator = RecordingGenerator()
    result = generate_with_targeted_regeneration(
        generator,
        _node(),
        seed=7,
        campaign_context={"world_brief": {"title": "Harbor"}},
        dependency_topics={},
        process=_process,
        max_attempts=3,
    )

    assert len(generator.contexts) == 2
    request = generator.contexts[1]["targeted_regeneration"]
    assert request["topic_id"] == "actors"
    assert request["entity_ids"] == ["actor:ada"]
    assert request["fields"] == ["next_action"]
    assert request["preserve_entity_ids"] == ["actor:bram"]
    assert request["prior_failing_entities"][0]["next_action"] == "Wait."
    assert result.entities[0]["name"] == "Ada"
    assert result.entities[0]["next_action"].startswith("Inspect the flooded")
    assert result.entities[1]["name"] == "Bram"
    assert result.entities[1]["next_action"].startswith("Recalibrate the harbor")
    assert result.provenance["targeted_regeneration_enforced"] is True
    assert result.provenance["targeted_regeneration_succeeded"] is True
    assert result.provenance["targeted_regeneration_attempt_count"] == 2


def test_targeted_merge_rejects_missing_selected_entity() -> None:
    prior = GeneratedTopic(
        topic_id="actors",
        entities=(
            {"id": "actor:ada", "kind": "actor", "next_action": "Wait."},
        ),
    )
    candidate = GeneratedTopic(topic_id="actors", entities=())
    error = StructuredFactValidationError(
        (
            StructuredFactIssue(
                code="weak_operational_state",
                topic_id="actors",
                entity_id="actor:ada",
                field_id="next_action",
                message="Replace the placeholder.",
            ),
        )
    )
    request = regeneration_request_from_error(_node(), error, attempt=2)
    assert request is not None
    with pytest.raises(StructuredFactValidationError) as raised:
        enforce_targeted_regeneration(prior, candidate, request)
    assert raised.value.issues[0].code == "targeted_regeneration_invariant"


def test_deterministic_generation_never_retries_semantic_failures() -> None:
    generator = RecordingGenerator(provider=False)
    with pytest.raises(StructuredFactValidationError):
        generate_with_targeted_regeneration(
            generator,
            _node(),
            seed=7,
            campaign_context={},
            dependency_topics={},
            process=_process,
            max_attempts=3,
        )
    assert len(generator.contexts) == 1


def test_retry_budget_is_bounded() -> None:
    generator = RecordingGenerator(always_bad=True)
    with pytest.raises(StructuredFactValidationError):
        generate_with_targeted_regeneration(
            generator,
            _node(),
            seed=7,
            campaign_context={},
            dependency_topics={},
            process=_process,
            max_attempts=2,
        )
    assert len(generator.contexts) == 2


def test_validation_issue_maps_to_machine_readable_request() -> None:
    error = StructuredFactValidationError(
        (
            StructuredFactIssue(
                code="unresolved_typed_reference",
                topic_id="actors",
                entity_id="actor:ada",
                field_id="location_id",
                message="Location must resolve in places.",
                supplied_value="place:missing",
            ),
        )
    )
    request = regeneration_request_from_error(_node(), error, attempt=2)
    assert request is not None
    assert request.reason_codes == ("unresolved_typed_reference",)
    assert request.entity_ids == ("actor:ada",)
    assert request.fields == ("location_id",)
    assert request.scope == "entity_fields"


class InvalidReferenceProvider:
    def generate(
        self,
        node: CampaignTopicNode,
        *,
        seed: int,
        campaign_context: dict,
        dependency_topics: dict,
    ) -> GeneratedTopic:
        del seed, campaign_context, dependency_topics
        return GeneratedTopic(
            topic_id=node.topic_id,
            entities=(
                {
                    "id": "setting_rule:corp_hegemony",
                    "kind": "setting_rule",
                    "name": "Corporate Hegemony",
                    "rule": "Corporate law governs access to every secure district.",
                    "observable_consequences": {"detail": "Security gates scan every traveler."},
                },
            ),
            facts=(
                {
                    "id": "fact:corp_hegemony",
                    "entity_refs": ["group:omnicorp"],
                },
            ),
            relationships=(
                {
                    "id": "relationship:corp_hegemony",
                    "source_id": "setting_rule:corp_hegemony",
                    "target_id": "group:omnicorp",
                },
            ),
            provenance={"generator": "structured_world_forge_provider_v1"},
        )


def test_live_provider_grounding_failure_retains_candidate_for_review() -> None:
    node = CampaignTopicNode(
        topic_id="setting_rules",
        title="Setting Rules",
        category="domain",
        target_count=1,
        metadata={
            "entity_kind": "setting_rule",
            "field_definitions": [
                {"field_id": "name", "value_type": "string", "required": True},
                {"field_id": "rule", "value_type": "string", "required": True},
                {
                    "field_id": "observable_consequences",
                    "value_type": "structured_object",
                    "required": True,
                },
            ],
        },
    )

    result = ReferenceSafeWorldForgeGenerator(InvalidReferenceProvider()).generate(
        node,
        seed=7,
        campaign_context={
            "world_brief": {
                "title": "Neon Harbor",
                "description": "A corporate port city.",
            }
        },
        dependency_topics={},
    )

    assert result.entities[0]["name"] == "Corporate Hegemony"
    assert result.provenance["generation_status"] == "needs_review"
    review = result.provenance["generation_review"]
    assert review["blocking"] is True
    assert review["reason_codes"]
    assert result.provenance["generator"].startswith("structured_world_forge_provider_")


class ExhaustedStructuredProvider:
    def generate(
        self,
        node: CampaignTopicNode,
        *,
        seed: int,
        campaign_context: dict,
        dependency_topics: dict,
    ) -> GeneratedTopic:
        del node, seed, campaign_context, dependency_topics
        raise RuntimeError(
            "structured World Forge provider failed for places batch 1/18 after 3 attempts"
        )


def test_provider_failure_without_candidate_remains_terminal() -> None:
    node = CampaignTopicNode(
        topic_id="setting_rules",
        title="Setting Rules",
        category="domain",
        target_count=1,
        metadata={
            "entity_kind": "setting_rule",
            "field_definitions": [
                {"field_id": "name", "value_type": "string", "required": True},
                {"field_id": "rule", "value_type": "string", "required": True},
                {
                    "field_id": "observable_consequences",
                    "value_type": "structured_object",
                    "required": True,
                },
            ],
        },
    )

    with pytest.raises(
        RuntimeError,
        match="structured World Forge provider failed for places batch 1/18 after 3 attempts",
    ):
        ReferenceSafeWorldForgeGenerator(ExhaustedStructuredProvider()).generate(
            node,
            seed=7,
            campaign_context={
                "world_brief": {
                    "title": "Neon Harbor",
                    "description": "A corporate port city.",
                }
            },
            dependency_topics={},
        )
