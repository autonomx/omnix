import pytest

from app.rpg.session.genesis.world_forge_contract import CampaignTopicNode
from app.rpg.session.genesis.world_forge_fact_pipeline import (
    StructuredFactIssue,
    StructuredFactValidationError,
)
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg.session.genesis.world_forge_regeneration import (
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
        action = "Wait." if self.always_bad or not targeted else (
            "Inspect the flooded relay chamber before the evening tide."
        )
        return GeneratedTopic(
            topic_id=node.topic_id,
            entities=(
                {
                    "id": "actor:ada",
                    "kind": "actor",
                    "name": "Ada",
                    "next_action": action,
                },
                {
                    "id": "actor:bram",
                    "kind": "actor",
                    "name": "Bram",
                    "next_action": "Recalibrate the harbor crane after the noon shift.",
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
    assert result.provenance["targeted_regeneration_succeeded"] is True
    assert result.provenance["targeted_regeneration_attempt_count"] == 2


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
