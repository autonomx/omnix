from app.rpg.session.genesis.canon_audit import CanonAuditReport
from app.rpg.session.genesis.world_forge_causal_evaluation import (
    attach_causal_evaluation,
    evaluate_causal_generation,
)
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic


def _topics() -> tuple[GeneratedTopic, ...]:
    return (
        GeneratedTopic(
            topic_id="history_timeline",
            entities=(
                {
                    "id": "event:war",
                    "legacy_status": "continuing",
                    "present_day_legacies": {"trace": "Bridge fortress"},
                },
                {
                    "id": "event:treaty",
                    "legacy_status": "absorbed",
                    "present_day_legacies": {"trace": "Inheritance code"},
                },
            ),
        ),
        GeneratedTopic(
            topic_id="places",
            entities=(
                {
                    "id": "place:ironford",
                    "founding_event_ids": ["event:war"],
                },
            ),
        ),
        GeneratedTopic(
            topic_id="causal_links",
            entities=(
                {
                    "id": "causal:war_place",
                    "cause_event_ids": ["event:war"],
                    "effect_id": "place:ironford",
                    "effect_type": "founded",
                    "mechanism": "The army built a fortified permanent crossing.",
                },
                {
                    "id": "causal:treaty_place",
                    "cause_event_ids": ["event:treaty"],
                    "effect_id": "place:ironford",
                    "effect_type": "legally_inherited",
                    "mechanism": "The treaty transferred toll authority into civic law.",
                },
            ),
        ),
    )


def test_causal_evaluation_reports_coverage_and_diversity() -> None:
    metrics = evaluate_causal_generation(_topics())

    assert metrics["causal_evaluation_applicable"] == 1
    assert metrics["causal_history_events"] == 2
    assert metrics["causal_links"] == 2
    assert metrics["causal_event_coverage_bps"] == 10000
    assert metrics["causal_mechanism_diversity_bps"] == 10000
    assert metrics["causal_formation_coverage_bps"] == 10000


def test_causal_evaluation_attaches_promotion_gate_to_audit() -> None:
    report = attach_causal_evaluation(_topics(), CanonAuditReport(passed=True))

    assert report.checks["causal_errors"] == 0
    assert report.checks["causal_promotion_ready"] == 1


def test_existing_world_without_causal_topic_is_not_applicable() -> None:
    topics = (GeneratedTopic(topic_id="places", entities=({"id": "place:old"},)),)
    report = attach_causal_evaluation(topics, CanonAuditReport(passed=True))

    assert report.checks["causal_evaluation_applicable"] == 0
    assert report.checks["causal_promotion_ready"] == 0
