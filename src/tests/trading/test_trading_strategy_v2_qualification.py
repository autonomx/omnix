from __future__ import annotations

import hashlib
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from app.trading.strategies.models import GapPullbackConfig, StrategyRiskProfile
from app.trading.strategy_repository import StrategyEvent, TradingStrategyConfigDocument
from app.trading.strategy_v2_qualification import (
    FROZEN_V2_PROFILE_FINGERPRINT,
    V2_PROSPECTIVE_START,
    V2_QUALIFICATION_VERSION,
    V2_REPLAY_VERSION,
    evaluate_v2_prospective_qualification,
    frozen_v2_config,
    v2_profile_fingerprint,
)


def _strategy(config: GapPullbackConfig | None = None) -> TradingStrategyConfigDocument:
    active = config or frozen_v2_config()
    return TradingStrategyConfigDocument(
        strategy_id="v2-prospective",
        account_id="paper-1",
        strategy_kind="gap_pullback_v1",
        strategy_version=active.strategy_version,
        mode="shadow",
        active_universe_id=None,
        config=active,
        risk=StrategyRiskProfile(),
        enabled=True,
    )


def _event(
    *,
    event_type: str,
    instrument_id: str,
    observed_at: datetime,
    reason_code: str | None,
    payload: dict[str, object],
    suffix: str,
) -> StrategyEvent:
    idem = hashlib.sha256(f"{event_type}|{instrument_id}|{observed_at.isoformat()}|{suffix}".encode()).hexdigest()
    return StrategyEvent(
        strategy_id="v2-prospective",
        event_id=idem[:32],
        instrument_id=instrument_id,
        event_type=event_type,
        state="entry_ready",
        reason_code=reason_code,
        observed_at=observed_at,
        idempotency_key=idem,
        payload=payload,
    )


def _qualified_evidence() -> list[StrategyEvent]:
    events: list[StrategyEvent] = []
    for index in range(20):
        session = V2_PROSPECTIVE_START + timedelta(days=index)
        # Keep the test independent of exchange-calendar logic; qualification
        # counts the immutable session labels that replay persisted.
        instrument = f"equity:SYM{index % 10}"
        signal_at = datetime.combine(session, time(14, 0), tzinfo=timezone.utc)
        entry_at = signal_at + timedelta(minutes=1)
        universe_id = f"auto-archive-{session.isoformat()}-0920-test"
        events.append(
            _event(
                event_type="shadow_execution",
                instrument_id=instrument,
                observed_at=signal_at,
                reason_code="SHADOW_EXECUTION_OBSERVED",
                suffix=f"live-{index}",
                payload={
                    "strategy_version": "2.0.0",
                    "mode": "shadow",
                    "universe_id": universe_id,
                    "universe_source": "auto_archive_shadow",
                    "profile_fingerprint": FROZEN_V2_PROFILE_FINGERPRINT,
                    "execution_authority": False,
                    "execution": {"execution_eligible": True},
                },
            )
        )
        events.append(
            _event(
                event_type="v2_shadow_replay_trade",
                instrument_id=instrument,
                observed_at=entry_at + timedelta(hours=1),
                reason_code="V2_SHADOW_REPLAY_TRADE",
                suffix=f"replay-{index}",
                payload={
                    "qualification_version": V2_QUALIFICATION_VERSION,
                    "replay_version": V2_REPLAY_VERSION,
                    "session_date": session.isoformat(),
                    "universe_id": universe_id,
                    "universe_source": "auto_archive_shadow",
                    "profile_fingerprint": FROZEN_V2_PROFILE_FINGERPRINT,
                    "entry_time": entry_at.isoformat(),
                    "exit_time": (entry_at + timedelta(minutes=20)).isoformat(),
                    "r_result": "0.50",
                    "execution_authority": False,
                },
            )
        )
    return events


def test_frozen_v2_profile_fingerprint_is_stable_and_exact() -> None:
    assert v2_profile_fingerprint(frozen_v2_config()) == FROZEN_V2_PROFILE_FINGERPRINT
    changed = frozen_v2_config().model_copy(update={"v2_maximum_l2_to_signal_minutes": 9})
    assert v2_profile_fingerprint(changed) != FROZEN_V2_PROFILE_FINGERPRINT


def test_qualification_requires_explicit_review_bound_to_current_evidence() -> None:
    strategy = _strategy()
    events = _qualified_evidence()

    before_review = evaluate_v2_prospective_qualification(strategy, events)

    assert before_review.profile_match is True
    assert before_review.replay_trade_count == 20
    assert before_review.matched_eligible_trade_count == 20
    assert before_review.distinct_sessions == 20
    assert before_review.distinct_symbols == 10
    assert before_review.execution_match_rate == Decimal("1")
    assert before_review.expectancy_r == Decimal("0.50")
    assert before_review.one_sided_90_lcb_r == Decimal("0.50")
    assert before_review.max_drawdown_r == Decimal("0")
    assert before_review.qualified is True
    assert before_review.reviewed is False
    assert before_review.auto_paper_authorized is False
    assert "V2_OPERATOR_REVIEW_REQUIRED" in before_review.reason_codes

    review_at = max(event.observed_at for event in events) + timedelta(minutes=1)
    events.append(
        _event(
            event_type="v2_promotion_review",
            instrument_id="strategy:v2-prospective",
            observed_at=review_at,
            reason_code="V2_PROMOTION_REVIEW_APPROVED",
            suffix="review",
            payload={
                "qualification_version": V2_QUALIFICATION_VERSION,
                "profile_fingerprint": before_review.current_profile_fingerprint,
                "evidence_fingerprint": before_review.evidence_fingerprint,
                "approved": True,
                "review_note": "Prospective evidence reviewed and approved for AUTO PAPER.",
                "execution_authority": False,
            },
        )
    )

    after_review = evaluate_v2_prospective_qualification(strategy, events)
    assert after_review.qualified is True
    assert after_review.reviewed is True
    assert after_review.auto_paper_authorized is True
    assert "V2_OPERATOR_REVIEW_REQUIRED" not in after_review.reason_codes


def test_new_trade_invalidates_prior_review_until_evidence_is_reviewed_again() -> None:
    strategy = _strategy()
    events = _qualified_evidence()
    qualified = evaluate_v2_prospective_qualification(strategy, events)
    review_at = max(event.observed_at for event in events) + timedelta(minutes=1)
    review = _event(
        event_type="v2_promotion_review",
        instrument_id="strategy:v2-prospective",
        observed_at=review_at,
        reason_code="V2_PROMOTION_REVIEW_APPROVED",
        suffix="review",
        payload={
            "qualification_version": V2_QUALIFICATION_VERSION,
            "profile_fingerprint": qualified.current_profile_fingerprint,
            "evidence_fingerprint": qualified.evidence_fingerprint,
            "approved": True,
            "review_note": "Initial prospective evidence explicitly reviewed.",
            "execution_authority": False,
        },
    )
    events.append(review)
    assert evaluate_v2_prospective_qualification(strategy, events).auto_paper_authorized is True

    session = date(2026, 9, 20)
    signal_at = datetime(2026, 9, 20, 14, 0, tzinfo=timezone.utc)
    entry_at = signal_at + timedelta(minutes=1)
    instrument = "equity:NEW"
    universe_id = f"auto-archive-{session.isoformat()}-0920-test"
    events.extend([
        _event(
            event_type="shadow_execution",
            instrument_id=instrument,
            observed_at=signal_at,
            reason_code="SHADOW_EXECUTION_OBSERVED",
            suffix="new-live",
            payload={
                "universe_source": "auto_archive_shadow",
                "profile_fingerprint": FROZEN_V2_PROFILE_FINGERPRINT,
                "execution_authority": False,
                "execution": {"execution_eligible": True},
            },
        ),
        _event(
            event_type="v2_shadow_replay_trade",
            instrument_id=instrument,
            observed_at=entry_at + timedelta(hours=1),
            reason_code="V2_SHADOW_REPLAY_TRADE",
            suffix="new-replay",
            payload={
                "qualification_version": V2_QUALIFICATION_VERSION,
                "replay_version": V2_REPLAY_VERSION,
                "session_date": session.isoformat(),
                "universe_id": universe_id,
                "universe_source": "auto_archive_shadow",
                "profile_fingerprint": FROZEN_V2_PROFILE_FINGERPRINT,
                "entry_time": entry_at.isoformat(),
                "r_result": "0.50",
                "execution_authority": False,
            },
        ),
    ])

    changed = evaluate_v2_prospective_qualification(strategy, events)
    assert changed.qualified is True
    assert changed.reviewed is False
    assert changed.auto_paper_authorized is False


def test_profile_mismatch_and_missing_execution_match_fail_closed() -> None:
    changed_config = frozen_v2_config().model_copy(update={"minimum_tod_rvol": Decimal("4")})
    strategy = _strategy(changed_config)
    events = _qualified_evidence()
    # Remove one live observation while retaining every replay trade.
    first_live = next(event for event in events if event.event_type == "shadow_execution")
    events.remove(first_live)

    result = evaluate_v2_prospective_qualification(strategy, events)

    assert result.profile_match is False
    assert result.matched_eligible_trade_count == 19
    assert result.execution_match_rate == Decimal("0.95")
    assert result.qualified is False
    assert "V2_PROFILE_MISMATCH" in result.reason_codes
    assert "V2_MATCHED_TRADES_LOW" in result.reason_codes
