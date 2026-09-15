from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.companion_activity.cognition import DeliveryIntent
from app.companion_activity.delivery_quality import (
    CompanionDeliveryQualityMetrics,
    CompanionDeliveryQualityScorer,
    DeliveryQualityFeatures,
    DeliveryQualityOutcome,
)

NOW = datetime(2026, 9, 15, 8, 0, tzinfo=timezone.utc)


def intent(*, created_at: datetime = NOW, salience: float = 0.8, confidence: float = 0.9):
    return DeliveryIntent(
        intent_id="intent:quality",
        session_id="chat:1",
        kind="REACT",
        reason="quality test",
        grounding_proposition_ids=("p:1",),
        confidence=confidence,
        salience=salience,
        created_at=created_at,
    )


def test_quality_score_retains_components_and_penalizes_interruption_repetition() -> None:
    scorer = CompanionDeliveryQualityScorer()
    high = scorer.score(
        intent(),
        DeliveryQualityFeatures(
            novelty=0.9,
            relevance=0.9,
            open_loop_relevance=0.8,
            progress_significance=0.8,
            interruption_cost=0.0,
            repetition_debt=0.0,
        ),
        now=NOW,
    )
    low = scorer.score(
        intent(),
        DeliveryQualityFeatures(
            novelty=0.2,
            relevance=0.3,
            interruption_cost=1.0,
            repetition_debt=1.0,
        ),
        now=NOW,
    )

    assert high.composite > low.composite
    assert high.open_loop_relevance == 0.8
    assert low.interruption_cost == 1.0
    assert low.repetition_debt == 1.0


def test_stale_intent_loses_freshness_without_changing_authority() -> None:
    scorer = CompanionDeliveryQualityScorer()
    fresh = scorer.score(
        intent(created_at=NOW),
        DeliveryQualityFeatures(freshness_window_seconds=120),
        now=NOW,
    )
    stale = scorer.score(
        intent(created_at=NOW - timedelta(minutes=3)),
        DeliveryQualityFeatures(freshness_window_seconds=120),
        now=NOW,
    )

    assert fresh.freshness == 1.0
    assert stale.freshness == 0.0
    assert fresh.composite > stale.composite


def test_content_free_metrics_measure_quality_without_storing_text() -> None:
    metrics = CompanionDeliveryQualityMetrics()
    metrics.record(
        DeliveryQualityOutcome(
            delivered=True,
            interrupted=True,
            ignored_by_user=True,
            activity_state_corrected=True,
            open_loop_resolution_predicted=True,
            open_loop_resolution_correct=True,
            memory_promotion_predicted=True,
            memory_promotion_correct=False,
        )
    )
    metrics.record(
        DeliveryQualityOutcome(
            delivered=False,
            stale_suppressed=True,
            repeated_suppressed=True,
            false_objective_transition=True,
            open_loop_resolution_predicted=True,
            open_loop_resolution_correct=False,
            memory_promotion_predicted=True,
            memory_promotion_correct=True,
        )
    )

    snapshot = metrics.snapshot()
    assert snapshot.samples == 2
    assert snapshot.delivered == 1
    assert snapshot.stale_comment_rate == 0.5
    assert snapshot.repeated_comment_rate == 0.5
    assert snapshot.interruption_rate == 1.0
    assert snapshot.ignored_initiative_rate == 1.0
    assert snapshot.activity_state_correction_rate == 0.5
    assert snapshot.false_objective_transition_rate == 0.5
    assert snapshot.open_loop_completion_precision == 0.5
    assert snapshot.memory_promotion_precision == 0.5
    assert "text" not in snapshot.model_fields
    assert "content" not in snapshot.model_fields
