from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from app.apps.trading import strategy_dynamic_discovery as dd
from app.apps.trading.strategy_discovery_acquisition import (
    CausalMarketObservation,
    PersistedCatalystIntelligenceSource,
    install_default_discovery_sources,
    registered_discovery_sources,
    unregister_discovery_acquisition_source,
)
from app.apps.trading.strategy_discovery_replay import (
    DiscoveryOpportunityLabel,
    DiscoveryReplayObservation,
    replay_dynamic_discovery,
)
from app.apps.trading.strategy_interday_postclose import label_candidate_outcome


SESSION = date(2026, 9, 11)
T0 = datetime(2026, 9, 11, 13, 5, tzinfo=timezone.utc)


def _market(at: datetime, *, gap: float, rvol: float = 0.0):
    return dd.MarketAnomalyFeatures(
        observed_at=at,
        gap_pct=gap,
        tod_rvol=rvol,
        volume_to_float=0.0,
        dollar_volume=20_000_000.0,
    )


def _observation(
    at: datetime,
    *,
    symbol: str = "equity:NASDAQ:TEST",
    source: str = "finviz_live_leaders",
    gap: float = 10.0,
    rvol: float = 0.0,
    catalyst_payload=None,
    candidate_payload=None,
):
    return CausalMarketObservation(
        instrument_id=symbol,
        session_date=SESSION,
        observed_at=at,
        source=source,
        market=_market(at, gap=gap, rvol=rvol) if gap is not None else None,
        catalyst_payload=catalyst_payload,
        candidate_payload=candidate_payload,
        catalyst_known=catalyst_payload is not None,
    )


def _candidate(symbol: str, score: float, at: datetime = T0):
    event = dd.DiscoveryEvent(
        event_id=(symbol.replace(":", "") + "x" * 40)[:32],
        session_date=SESSION,
        instrument_id=symbol,
        discovered_at=at,
        trigger_type=dd.DiscoveryTriggerType.MARKET_ANOMALY,
        source="fixture",
        causal_as_of=at,
        attention_score=score,
    )
    return dd.merge_discovery_event(None, event)


def test_default_acquisition_includes_market_and_persisted_catalyst_sources():
    before = {row.name for row in registered_discovery_sources()}
    install_default_discovery_sources()
    names = {row.name for row in registered_discovery_sources()}
    assert "finviz_live_leaders" in names
    assert PersistedCatalystIntelligenceSource.name in names
    for name in names - before:
        unregister_discovery_acquisition_source(name)


def test_live_and_replay_share_leader_fallback_and_lifecycle():
    first = _observation(T0, gap=10.0, rvol=0.0)
    live_first = dd.apply_discovery_scan(
        previous_state={}, observations=(first,), watermark=T0, session_date=SESSION
    )
    assert len(live_first.candidates) == 1
    assert live_first.events[0].attention_score == 35.0

    # Off the live leaderboard from T0+5; cooling 31 minutes later.
    left_at = T0 + timedelta(minutes=5)
    left = _observation(left_at, source="fixture", gap=1.0, rvol=0.0)
    live_left = dd.apply_discovery_scan(
        previous_state={row.instrument_id: row for row in live_first.candidates},
        observations=(left,),
        watermark=left_at,
        session_date=SESSION,
    )
    weak_at = left_at + timedelta(minutes=31)
    weak = _observation(weak_at, source="fixture", gap=1.0, rvol=0.0)
    live_second = dd.apply_discovery_scan(
        previous_state={row.instrument_id: row for row in live_left.candidates},
        observations=(weak,),
        watermark=weak_at,
        session_date=SESSION,
    )
    assert live_second.candidates[0].lifecycle == dd.CandidateLifecycleState.COOLING

    replay_result = replay_dynamic_discovery(
        session_date=SESSION,
        observations=(
            DiscoveryReplayObservation(
                instrument_id=first.instrument_id,
                observed_at=first.observed_at,
                source=first.source,
                market=first.market,
            ),
            DiscoveryReplayObservation(
                instrument_id=left.instrument_id,
                observed_at=left.observed_at,
                source=left.source,
                market=left.market,
            ),
            DiscoveryReplayObservation(
                instrument_id=weak.instrument_id,
                observed_at=weak.observed_at,
                source=weak.source,
                market=weak.market,
            ),
        ),
    )
    replay_candidate = replay_result.final_candidates[0]
    assert replay_candidate.instrument_id == live_second.candidates[0].instrument_id
    assert replay_candidate.lifecycle == live_second.candidates[0].lifecycle
    assert replay_candidate.tier == live_second.candidates[0].tier
    assert replay_candidate.discovered_at == live_second.candidates[0].discovered_at


def test_current_attention_drops_while_peak_is_retained_for_analysis():
    hot = _observation(T0, gap=30.0, rvol=200.0)
    first = dd.apply_discovery_scan(
        previous_state={}, observations=(hot,), watermark=T0, session_date=SESSION
    ).candidates[0]
    assert first.attention_score > 35

    later = T0 + timedelta(minutes=5)
    cool = _observation(later, gap=10.0, rvol=0.0)
    second = dd.apply_discovery_scan(
        previous_state={first.instrument_id: first},
        observations=(cool,),
        watermark=later,
        session_date=SESSION,
    ).candidates[0]
    assert second.attention_score < first.attention_score
    assert second.peak_attention_score == first.peak_attention_score


def test_scan_heartbeat_does_not_rewrite_last_causal_observation_time():
    first_observation = _observation(T0, gap=30.0, rvol=200.0)
    first = dd.apply_discovery_scan(
        previous_state={}, observations=(first_observation,), watermark=T0, session_date=SESSION
    ).candidates[0]
    heartbeat = dd.apply_discovery_scan(
        previous_state={first.instrument_id: first},
        observations=(),
        watermark=T0 + timedelta(minutes=5),
        session_date=SESSION,
    ).candidates[0]
    assert heartbeat.last_observed_at == T0


def test_catalyst_decay_is_operational_in_shared_state():
    catalyst = {
        "fundamental_materiality": "high",
        "materiality_to_company_size": "high",
        "catalyst_novelty": "high",
        "attention_strength": "high",
        "event_certainty": "high",
        "catalyst_strength": "high",
        "expected_attention_duration": "minutes",
        "intraday_persistence_class": "mixed",
    }
    observation = _observation(
        T0,
        gap=None,
        source="persisted_catalyst_intelligence_v2",
        catalyst_payload=catalyst,
    )
    first = dd.apply_discovery_scan(
        previous_state={}, observations=(observation,), watermark=T0, session_date=SESSION
    ).candidates[0]
    later = T0 + timedelta(minutes=60)
    decayed = dd.apply_discovery_scan(
        previous_state={first.instrument_id: first},
        observations=(),
        watermark=later,
        session_date=SESSION,
    ).candidates[0]
    assert decayed.catalyst_score < first.catalyst_score
    assert decayed.peak_catalyst_score >= first.catalyst_score


def test_unknown_supply_and_promo_are_neutral_not_benign():
    candidate = _candidate("equity:NASDAQ:UNK", 80)
    char = dd.build_opportunity_characterization(
        candidate,
        observed_at=T0,
        catalyst=None,
        market_structure=SimpleNamespace(confirmation_score=0.5),
    )
    assert char.catalyst_strength == 0
    assert char.fundamental_materiality == 0
    assert char.supply_pressure == 50
    assert char.promotional_risk == 50
    assert char.market_confirmation == 50


def test_experiment_cohorts_are_independent():
    catalyst = {
        "fundamental_materiality": "extreme",
        "materiality_to_company_size": "extreme",
        "catalyst_novelty": "high",
        "attention_strength": "high",
        "event_certainty": "high",
        "catalyst_strength": "very_high",
        "expected_attention_duration": "session",
    }
    observation = _observation(
        T0,
        gap=None,
        source="persisted_catalyst_intelligence_v2",
        catalyst_payload=catalyst,
    )
    scan = dd.apply_discovery_scan(
        previous_state={}, observations=(observation,), watermark=T0, session_date=SESSION
    )
    symbol = observation.instrument_id
    assert symbol in scan.experiment_cohorts["catalyst_only"]
    assert symbol in scan.experiment_cohorts["combined"]
    assert symbol not in scan.experiment_cohorts["market_only"]


def test_catalyst_first_candidate_can_gain_later_market_payload_without_new_admission():
    catalyst = {
        "fundamental_materiality": "extreme",
        "materiality_to_company_size": "extreme",
        "catalyst_novelty": "high",
        "attention_strength": "high",
        "event_certainty": "high",
        "catalyst_strength": "very_high",
        "expected_attention_duration": "session",
    }
    first_obs = _observation(
        T0,
        gap=None,
        source="persisted_catalyst_intelligence_v2",
        catalyst_payload=catalyst,
    )
    first = dd.apply_discovery_scan(
        previous_state={}, observations=(first_obs,), watermark=T0, session_date=SESSION
    ).candidates[0]

    payload = {"instrument_id": first.instrument_id, "sentinel": "causal-market-payload"}
    later = T0 + timedelta(minutes=1)
    market_obs = _observation(
        later,
        source="fixture",
        gap=1.0,
        rvol=0.0,
        candidate_payload=payload,
    )
    second = dd.apply_discovery_scan(
        previous_state={first.instrument_id: first},
        observations=(market_obs,),
        watermark=later,
        session_date=SESSION,
    ).candidates[0]
    assert second.latest_candidate_payload == payload


def test_future_observation_is_rejected_and_counted_not_self_authorized():
    future = _observation(T0 + timedelta(seconds=1), gap=30, rvol=100)
    scan = dd.apply_discovery_scan(
        previous_state={}, observations=(future,), watermark=T0, session_date=SESSION
    )
    assert scan.candidates == ()
    assert len(scan.violations) == 1
    assert scan.violations[0].reason == "FUTURE_OBSERVATION"


def test_per_arm_selection_can_keep_common_rank_outside_top_five():
    rows = []
    for index in range(12):
        candidate = _candidate(
            f"equity:NASDAQ:T{index:02d}",
            100 - index,
            T0 + timedelta(seconds=index),
        )
        char = dd.OpportunityCharacterization(
            instrument_id=candidate.instrument_id,
            observed_at=T0,
            attention_intensity=100 - index,
            continuation_prior=10 if index == 11 else 80,
            failed_selloff_prior=100 if index == 11 else 20,
            market_confirmation=100 if index == 11 else 20,
            execution_quality=100,
        )
        rows.append(candidate.model_copy(update={"characterization": char}))
    ranked = dd.apply_strategy_rankings(rows)
    special = next(row for row in ranked if row.instrument_id.endswith("T11"))
    assert special.strategy_ranks["deterministic-v2"] == 1
    assert "deterministic-v2" in special.selected_for_strategies


def test_qualification_enforces_execution_drawdown_lcb_stress_and_holdout():
    metrics = {
        "independent_sessions": 30,
        "labeled_opportunities": 200,
        "discovery_recall": 0.8,
        "discovery_precision": 0.3,
        "execution_sample_count": 50,
        "holdout_session_count": 8,
        "execution_adjusted_expectancy_r": 0.4,
        "expectancy_lcb_r": 0.2,
        "stressed_expectancy_r": 0.3,
        "holdout_expectancy_r": 0.25,
        "max_drawdown_r": -3.0,
        "data_reliability_fraction": 0.99,
        "causality_violations": 0,
    }
    passing = dd.evaluate_shadow_qualification(metrics)
    assert passing.eligible_for_review is True
    assert passing.auto_paper_authorized is False
    failing = dd.evaluate_shadow_qualification(
        {**metrics, "max_drawdown_r": -6.0}
    )
    assert failing.eligible_for_review is False
    assert "max_drawdown_exceeds_gate" in failing.reasons


class _Bar:
    def __init__(self, at: datetime, open_: float, high: float, low: float, close: float):
        self.start_time = at
        self.end_time = at + timedelta(minutes=1)
        self.open = open_
        self.high = high
        self.low = low
        self.close = close
        self.is_final = True
        self.session = "regular"


def test_discovery_label_uses_ohlc_and_stop_first_for_same_bar_ambiguity():
    regular_open = datetime(2026, 9, 11, 13, 30, tzinfo=timezone.utc)
    discovery_at = regular_open - timedelta(hours=1)
    candidate = _candidate("equity:NASDAQ:X", 80, discovery_at)
    bar = _Bar(regular_open, 100, 111, 94, 110)
    outcome = label_candidate_outcome(
        SimpleNamespace(bars=lambda *args: SimpleNamespace(bars=(bar,))),
        candidate,
        observed_at=regular_open + timedelta(minutes=2),
    )
    assert isinstance(outcome, dd.TrendDurabilityOutcome)
    assert outcome.plus_1r_before_minus_1r is False
    assert outcome.plus_2r_before_minus_1r is False
    assert outcome.discovery_at == discovery_at
    assert outcome.tradeable_reference_at == regular_open
    assert outcome.label_kind == "discovery_path"


def test_replay_uses_same_finviz_fallback_as_live():
    row = DiscoveryReplayObservation(
        instrument_id="equity:NASDAQ:FB",
        observed_at=T0,
        source="finviz_live_leaders",
        market=_market(T0, gap=10, rvol=0),
    )
    result = replay_dynamic_discovery(
        session_date=SESSION,
        observations=(row,),
        labels=(
            DiscoveryOpportunityLabel(
                instrument_id=row.instrument_id,
                opportunity=True,
                first_actionable_at=T0,
            ),
        ),
    )
    assert result.discovered_symbol_count == 1
    assert result.discovery_recall == 1
    assert result.events[0].attention_score == 35


def test_replay_precision_ignores_unlabeled_symbols_instead_of_calling_them_false_positive():
    candidate = "equity:NASDAQ:LABELED"
    unlabeled = "equity:NASDAQ:UNKNOWN"
    label = DiscoveryOpportunityLabel(
        instrument_id=candidate,
        opportunity=True,
        first_actionable_at=T0,
    )
    result = replay_dynamic_discovery(
        session_date=SESSION,
        observations=(
            DiscoveryReplayObservation(
                instrument_id=candidate,
                observed_at=T0,
                source="fixture",
                market=_market(T0, gap=30, rvol=20),
            ),
            DiscoveryReplayObservation(
                instrument_id=unlabeled,
                observed_at=T0,
                source="fixture",
                market=_market(T0, gap=25, rvol=20),
            ),
        ),
        labels=(label,),
    )
    assert result.discovery_precision == 1.0
    assert result.false_positive_symbols == ()


def test_a_live_leaderboard_member_stays_active_while_its_features_are_thin():
    # HOST, 2026-10-20: on the top-gainers board all day, but its scored features stayed
    # near zero (attention ~18, below the 42 retention score), so it expired at 09:17
    # and never reached a strategy.
    state: dict = {}
    result = None
    for minute in range(0, 181, 5):
        at = T0 + timedelta(minutes=minute)
        result = dd.apply_discovery_scan(
            previous_state=state, observations=(_observation(at, gap=17.0),), watermark=at, session_date=SESSION
        )
        state = {row.instrument_id: row for row in result.candidates}
    [candidate] = result.candidates
    assert candidate.common_priority < dd.DEFAULT_DYNAMIC_DISCOVERY_CONFIG.retention_score
    assert candidate.lifecycle == dd.CandidateLifecycleState.ACTIVE
    assert candidate.tier == dd.EvaluationTier.A
    assert candidate.instrument_id in result.experiment_cohorts[dd.DiscoveryExperimentArm.MARKET_ONLY.value]
    assert candidate.instrument_id in result.experiment_cohorts[dd.DiscoveryExperimentArm.COMBINED.value]

    # Off the board the retention hysteresis applies as before.
    last = T0 + timedelta(minutes=180)
    for minute in (5, 65):
        at = last + timedelta(minutes=minute)
        result = dd.apply_discovery_scan(previous_state=state, observations=(), watermark=at, session_date=SESSION)
        state = {row.instrument_id: row for row in result.candidates}
    assert result.candidates[0].lifecycle == dd.CandidateLifecycleState.EXPIRED

    # Back on the board, it is active again.
    back = last + timedelta(minutes=70)
    result = dd.apply_discovery_scan(
        previous_state=state, observations=(_observation(back, gap=17.0),), watermark=back, session_date=SESSION
    )
    assert result.candidates[0].lifecycle == dd.CandidateLifecycleState.ACTIVE


def test_another_source_does_not_retain_a_weak_candidate():
    state: dict = {}
    result = None
    for minute in range(0, 71, 5):
        at = T0 + timedelta(minutes=minute)
        result = dd.apply_discovery_scan(
            previous_state=state,
            observations=(_observation(at, gap=17.0, source="fixture" if minute else "finviz_live_leaders"),),
            watermark=at,
            session_date=SESSION,
        )
        state = {row.instrument_id: row for row in result.candidates}
    assert result.candidates[0].lifecycle == dd.CandidateLifecycleState.EXPIRED
