from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from app.trading.bounce_model import BounceFeatureVector, LABEL_DEFINITION
from app.trading.bounce_training import (
    BounceTrainingExample,
    fit_bounce_logistic,
    score_fitted_bounce_model,
)


TRAINED_AT = datetime(2026, 8, 18, 20, 0, tzinfo=timezone.utc)


def features(*, gap: str, breakout: str, spread: str = "50") -> BounceFeatureVector:
    return BounceFeatureVector(
        gap_pct=Decimal(gap),
        premarket_dollar_volume_log10=Decimal("6.3"),
        tod_rvol=Decimal("5"),
        float_shares_log10=Decimal("6.7"),
        market_cap_log10=Decimal("7.7"),
        spread_bps=Decimal(spread),
        opening_impulse_pct=Decimal("12"),
        hod_distance_pct=Decimal("2"),
        pullback_depth_pct=Decimal("12"),
        pullback_volume_ratio=Decimal("0.55"),
        l2_over_l1=Decimal("1.04"),
        vwap_distance_pct=Decimal("1.5"),
        vwap_slope_pct=Decimal("0.4"),
        breakout_volume_ratio=Decimal(breakout),
        atr_pct=Decimal("8"),
        minutes_since_open=Decimal("25"),
        catalyst_positive=Decimal("0"),
        catalyst_negative=Decimal("0"),
        dilution_flag=Decimal("0"),
    )


def training_examples() -> list[BounceTrainingExample]:
    negatives = [
        BounceTrainingExample(
            features=features(gap=str(20 + index / 10), breakout=str(0.8 + index / 100)),
            label=0,
        )
        for index in range(10)
    ]
    positives = [
        BounceTrainingExample(
            features=features(gap=str(45 + index / 10), breakout=str(2.0 + index / 100)),
            label=1,
        )
        for index in range(10)
    ]
    return [*negatives, *positives]


def test_fitted_logistic_artifact_is_deterministic_transparent_and_shadow_only() -> None:
    kwargs = dict(
        model_version="fixture-v1",
        trained_at=TRAINED_AT,
        iterations=500,
        learning_rate=Decimal("0.05"),
        l2_penalty=Decimal("0.001"),
    )
    first = fit_bounce_logistic(training_examples(), **kwargs)
    second = fit_bounce_logistic(training_examples(), **kwargs)

    assert first.fingerprint == second.fingerprint
    assert first.label_definition == LABEL_DEFINITION
    assert first.training_examples == 20
    assert first.positive_examples == 10
    assert first.shadow_only is True
    assert first.coefficients.keys() == first.feature_means.keys() == first.feature_scales.keys()
    assert first.training_log_loss < Decimal("0.7")


def test_fitted_model_scores_separated_fixture_in_expected_order() -> None:
    artifact = fit_bounce_logistic(
        training_examples(),
        model_version="fixture-v1",
        trained_at=TRAINED_AT,
        iterations=600,
    )
    weak = score_fitted_bounce_model(
        artifact,
        features(gap="21", breakout="0.85"),
        observed_at=TRAINED_AT,
    )
    strong = score_fitted_bounce_model(
        artifact,
        features(gap="46", breakout="2.05"),
        observed_at=TRAINED_AT,
    )
    assert weak.probability < strong.probability
    assert weak.shadow_only is True
    assert strong.shadow_only is True
    assert strong.model_version == "fixture-v1"


def test_model_artifacts_have_relational_authority_and_no_execution_gate() -> None:
    migration = Path("src/app/persistence/migrations/0040_trading_model_artifacts.sql").read_text()
    model_api = Path("src/app/trading/model_api.py").read_text().lower()
    strategy_monitor = Path("src/app/trading/strategy_monitor.py").read_text().lower()

    assert "create table if not exists omnix_trading_model_artifacts" in migration.lower()
    assert "check (shadow_only = true)" in migration.lower()
    assert "/bounce/train" in model_api
    assert "/bounce/score-shadow" in model_api
    assert "bounce_model" not in strategy_monitor
    assert "model_score" not in strategy_monitor
