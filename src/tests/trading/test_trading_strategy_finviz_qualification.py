from __future__ import annotations

import hashlib
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from app.trading.strategies.models import StrategyRiskProfile
from app.trading.strategy_finviz_qualification import (
    FINVIZ_V2_PROSPECTIVE_START,
    FINVIZ_V2_QUALIFICATION_VERSION,
    FINVIZ_V2_REPLAY_VERSION,
    FROZEN_FINVIZ_V2_PROFILE_FINGERPRINT,
    evaluate_finviz_v2_prospective_qualification,
    frozen_finviz_v2_config,
)
from app.trading.strategy_repository import StrategyEvent, TradingStrategyConfigDocument
from app.trading.strategy_v2_qualification import FROZEN_V2_PROFILE_FINGERPRINT, v2_profile_fingerprint


def _strategy(config=None) -> TradingStrategyConfigDocument:
    active = config or frozen_finviz_v2_config()
    return TradingStrategyConfigDocument(
        strategy_id="finviz-v2-prospective",
        account_id="paper-1",
        strategy_kind="gap_pullback_v1",
        strategy_version="2.0.0",
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
    idem = hashlib.sha256(
        f"{event_type}|{instrument_id}|{observed_at.isoformat()}|{suffix}".encode()
    ).hexdigest()
    return StrategyEvent(
        strategy_id="finviz-v2-prospective",
        event_id=idem[:32],
        instrument_id=instrument_id,
        event_type=event_type,
        state="entry_ready",
        reason_code=reason_code,
        observed_at=observed_at,
        idempotency_key=idem,
        payload=payload,
    )


def _session_dates(count: int) -> list[date]:
    values: list[date] = []
    current = FINVIZ_V2_PROSPECTIVE_START
    while len(values) < count:
        if current.weekday() < 5:
            values.append(current)
        current += timedelta(days=1)
    return values


def _qualified_evidence() -> list[StrategyEvent]:
    events: list[StrategyEvent] = []
    sessions = _session_dates(20)
    for index, session in enumerate(sessions):
        instrument = f"equity:FIN{index % 10}"
        signal_at = datetime.combine(session, time(14, 0), tzinfo=timezone.utc)
        entry_at = signal_at + timedelta(minutes=1)
        universe_id = f"auto-archive-{session.isoformat()}-0920-finviz-test"
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
                    "profile_fingerprint": FROZEN_FINVIZ_V2_PROFILE_FINGERPRINT,
                    "execution_authority": False,
                    "execution": {"execution_eligible": True},
                },
            )
        )
        # Stable positive but non-constant sample: mean 0.60R, positive LCB.
        r_result = Decimal("0.55") if index % 2 == 0 else Decimal("0.65")
        events.append(
            _event(
                event_type="finviz_v2_shadow_replay_trade",
                instrument_id=instrument,
                observed_at=entry_at + timedelta(hours=1),
                reason_code="FINVIZ_V2_SHADOW_REPLAY_TRADE",
                suffix=f"replay-{index}",
                payload={
                    "qualification_version": FINVIZ_V2_QUALIFICATION_VERSION,
                    "replay_version": FINVIZ_V2_REPLAY_VERSION,
                    "session_date": session.isoformat(),
                    "universe_id": universe_id,
                    "universe_source": "auto_archive_shadow",
                    "discovery_source": "finviz",
                    "profile_fingerprint": FROZEN_FINVIZ_V2_PROFILE_FINGERPRINT,
                    "entry_time": entry_at.isoformat(),
                    "r_result": str(r_result),
                    "execution_authority": False,
                },
            )
        )
    return events


def test_finviz_profile_is_isolated_from_canonical_yahoo_v2() -> None:
    assert FROZEN_FINVIZ_V2_PROFILE_FINGERPRINT != FROZEN_V2_PROFILE_FINGERPRINT
    assert (
        v2_profile_fingerprint(frozen_finviz_v2_config())
        == FROZEN_FINVIZ_V2_PROFILE_FINGERPRINT
    )


def test_finviz_qualification_starts_after_policy_freeze() -> None:
    strategy = _strategy()
    prior = FINVIZ_V2_PROSPECTIVE_START - timedelta(days=3)
    signal_at = datetime.combine(prior, time(14, 0), tzinfo=timezone.utc)
    entry_at = signal_at + timedelta(minutes=1)
    events = [
        _event(
            event_type="shadow_execution",
            instrument_id="equity:OLD",
            observed_at=signal_at,
            reason_code="SHADOW_EXECUTION_OBSERVED",
            suffix="old-live",
            payload={
                "universe_source": "auto_archive_shadow",
                "profile_fingerprint": FROZEN_FINVIZ_V2_PROFILE_FINGERPRINT,
                "execution_authority": False,
                "execution": {"execution_eligible": True},
            },
        ),
        _event(
            event_type="finviz_v2_shadow_replay_trade",
            instrument_id="equity:OLD",
            observed_at=entry_at + timedelta(hours=1),
            reason_code="FINVIZ_V2_SHADOW_REPLAY_TRADE",
            suffix="old-replay",
            payload={
                "qualification_version": FINVIZ_V2_QUALIFICATION_VERSION,
                "replay_version": FINVIZ_V2_REPLAY_VERSION,
                "session_date": prior.isoformat(),
                "universe_source": "auto_archive_shadow",
                "discovery_source": "finviz",
                "profile_fingerprint": FROZEN_FINVIZ_V2_PROFILE_FINGERPRINT,
                "entry_time": entry_at.isoformat(),
                "r_result": "1",
                "execution_authority": False,
            },
        ),
    ]
    result = evaluate_finviz_v2_prospective_qualification(strategy, events)
    assert result.replay_trade_count == 0
    assert result.matched_eligible_trade_count == 0
    assert result.auto_paper_authorized is False


def test_finviz_quantitative_floors_then_explicit_review_authorize_auto_paper() -> None:
    strategy = _strategy()
    events = _qualified_evidence()

    before_review = evaluate_finviz_v2_prospective_qualification(strategy, events)
    assert before_review.profile_match is True
    assert before_review.matched_eligible_trade_count == 20
    assert before_review.distinct_sessions == 20
    assert before_review.distinct_symbols == 10
    assert before_review.execution_match_rate == Decimal("1")
    assert before_review.expectancy_r == Decimal("0.60")
    assert before_review.one_sided_90_lcb_r is not None
    assert before_review.one_sided_90_lcb_r > 0
    assert before_review.max_drawdown_r == Decimal("0")
    assert before_review.qualified is True
    assert before_review.reviewed is False
    assert before_review.auto_paper_authorized is False
    assert "FINVIZ_V2_OPERATOR_REVIEW_REQUIRED" in before_review.reason_codes

    review_at = max(event.observed_at for event in events) + timedelta(minutes=1)
    review = _event(
        event_type="finviz_v2_promotion_review",
        instrument_id="strategy:finviz-v2-prospective",
        observed_at=review_at,
        reason_code="FINVIZ_V2_PROMOTION_REVIEW_APPROVED",
        suffix="review",
        payload={
            "qualification_version": FINVIZ_V2_QUALIFICATION_VERSION,
            "profile_fingerprint": before_review.current_profile_fingerprint,
            "evidence_fingerprint": before_review.evidence_fingerprint,
            "approved": True,
            "review_note": "Reviewed exact Finviz prospective evidence for AUTO PAPER.",
            "execution_authority": False,
        },
    )
    after_review = evaluate_finviz_v2_prospective_qualification(
        strategy, [*events, review]
    )
    assert after_review.qualified is True
    assert after_review.reviewed is True
    assert after_review.auto_paper_authorized is True
    assert "FINVIZ_V2_OPERATOR_REVIEW_REQUIRED" not in after_review.reason_codes


def test_new_finviz_replay_trade_invalidates_exact_review() -> None:
    strategy = _strategy()
    events = _qualified_evidence()
    qualified = evaluate_finviz_v2_prospective_qualification(strategy, events)
    review_at = max(event.observed_at for event in events) + timedelta(minutes=1)
    events.append(
        _event(
            event_type="finviz_v2_promotion_review",
            instrument_id="strategy:finviz-v2-prospective",
            observed_at=review_at,
            reason_code="FINVIZ_V2_PROMOTION_REVIEW_APPROVED",
            suffix="review",
            payload={
                "qualification_version": FINVIZ_V2_QUALIFICATION_VERSION,
                "profile_fingerprint": qualified.current_profile_fingerprint,
                "evidence_fingerprint": qualified.evidence_fingerprint,
                "approved": True,
                "execution_authority": False,
            },
        )
    )
    assert evaluate_finviz_v2_prospective_qualification(
        strategy, events
    ).auto_paper_authorized is True

    session = _session_dates(21)[-1]
    signal_at = datetime.combine(session, time(14, 0), tzinfo=timezone.utc)
    entry_at = signal_at + timedelta(minutes=1)
    events.extend(
        [
            _event(
                event_type="shadow_execution",
                instrument_id="equity:NEW",
                observed_at=signal_at,
                reason_code="SHADOW_EXECUTION_OBSERVED",
                suffix="new-live",
                payload={
                    "universe_source": "auto_archive_shadow",
                    "profile_fingerprint": FROZEN_FINVIZ_V2_PROFILE_FINGERPRINT,
                    "execution_authority": False,
                    "execution": {"execution_eligible": True},
                },
            ),
            _event(
                event_type="finviz_v2_shadow_replay_trade",
                instrument_id="equity:NEW",
                observed_at=entry_at + timedelta(hours=1),
                reason_code="FINVIZ_V2_SHADOW_REPLAY_TRADE",
                suffix="new-replay",
                payload={
                    "qualification_version": FINVIZ_V2_QUALIFICATION_VERSION,
                    "replay_version": FINVIZ_V2_REPLAY_VERSION,
                    "session_date": session.isoformat(),
                    "universe_source": "auto_archive_shadow",
                    "discovery_source": "finviz",
                    "profile_fingerprint": FROZEN_FINVIZ_V2_PROFILE_FINGERPRINT,
                    "entry_time": entry_at.isoformat(),
                    "r_result": "0.50",
                    "execution_authority": False,
                },
            ),
        ]
    )
    changed = evaluate_finviz_v2_prospective_qualification(strategy, events)
    assert changed.qualified is True
    assert changed.reviewed is False
    assert changed.auto_paper_authorized is False
    assert "FINVIZ_V2_OPERATOR_REVIEW_REQUIRED" in changed.reason_codes


def test_finviz_execution_profile_change_fails_closed_but_llm_settings_do_not() -> None:
    base = frozen_finviz_v2_config()
    observational = base.model_copy(
        update={
            "intraday_llm_enabled": False,
            "intraday_llm_top_n": 12,
            "intraday_llm_interval_minutes": 30,
        }
    )
    assert (
        v2_profile_fingerprint(observational)
        == FROZEN_FINVIZ_V2_PROFILE_FINGERPRINT
    )

    changed = base.model_copy(update={"v2_maximum_l2_to_signal_minutes": 9})
    result = evaluate_finviz_v2_prospective_qualification(
        _strategy(changed), _qualified_evidence()
    )
    assert result.profile_match is False
    assert result.auto_paper_authorized is False
    assert "FINVIZ_V2_PROFILE_MISMATCH" in result.reason_codes
