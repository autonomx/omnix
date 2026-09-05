from __future__ import annotations

import asyncio
import json
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.trading.ai_shadow_reliability import (
    get_trading_research_provider,
    reset_ai_shadow_reliability_state,
)
from app.trading.execution import ExecutionObservation
from app.trading.gapper_dataset import GapperCandidate, freeze_gapper_universe
from app.trading.indicator_signals import multi_timeframe_indicator_context
from app.trading.models import MarketBar
from app.trading.strategies import evaluate_gap_pullback
from app.trading.strategy_ai_shadow import AIShadowDecision, AIShadowPositionState, feature_snapshot
from app.trading.strategy_ai_shadow_monitor import TradingAIShadowMonitor
from app.trading.strategy_intraday_learning import build_intraday_learning_snapshot
from app.trading.strategy_managed_finviz_shadow import managed_finviz_shadow_document
from app.trading.strategy_repository import StrategyEvent
from app.trading.strategy_timeframes import resample_final_bars
from app.trading.strategy_universe_archiver import _archive_universe_id


RUN_LIVE = os.environ.get("OMNIX_RUN_LIVE_AI_TRADING_E2E", "0") == "1"
REQUIRE_LIVE_ENTRY = os.environ.get("OMNIX_AI_TRADING_E2E_REQUIRE_LIVE_ENTRY", "0") == "1"
EXPECTED_PROVIDER = os.environ.get("OMNIX_AI_TRADING_E2E_EXPECTED_PROVIDER", "").strip().casefold()

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "2026-09-03-auto-paper-e2e.json"
SESSION_DATE = date(2026, 9, 3)
OPEN_UTC = datetime(2026, 9, 3, 13, 30, tzinfo=timezone.utc)
NOW_UTC = datetime(2026, 9, 3, 13, 41, 30, tzinfo=timezone.utc)
_ET = ZoneInfo("America/New_York")


class MemoryStrategyRepository:
    def __init__(self, config, universe) -> None:
        self.config = config
        self.universe = universe
        self.events: list[StrategyEvent] = []
        self._event_keys: set[str] = set()

    def list_configs(self, active_only=True):
        if active_only and (not self.config.enabled or self.config.mode == "off"):
            return []
        return [self.config]

    def get_universe(self, universe_id):
        if universe_id != self.universe.universe_id:
            raise ValueError("gapper_universe_not_found")
        return self.universe

    def append_event(self, event: StrategyEvent):
        if event.idempotency_key in self._event_keys:
            return False
        self._event_keys.add(event.idempotency_key)
        self.events.append(event)
        return True

    def recent_events(self, strategy_id, limit):
        values = [event for event in self.events if event.strategy_id == strategy_id]
        return values[-limit:]

    def events_by_types_between(
        self,
        strategy_id,
        *,
        event_types,
        start_time,
        end_time,
        limit,
    ):
        allowed = set(event_types)
        return [
            event
            for event in self.events
            if event.strategy_id == strategy_id
            and event.event_type in allowed
            and start_time <= event.observed_at < end_time
        ][:limit]


class ReplayMarketService:
    def __init__(self, bars: list[MarketBar], execution: ExecutionObservation) -> None:
        self._bars = list(bars)
        self._execution = execution

    def bars(self, instrument_id, interval, limit, binding_id):
        assert interval == "1m"
        assert limit >= len(self._bars)
        return SimpleNamespace(
            bars=[
                bar.model_copy(update={"instrument_id": instrument_id})
                for bar in self._bars
            ]
        )

    def execution_observation(self, instrument_id, binding_id=None):
        binding = str(binding_id or self._execution.binding_id)
        return self._execution.model_copy(
            update={"instrument_id": instrument_id, "binding_id": binding}
        )

    def execution_indicator_bars(self, instrument_id, binding_id=None, *, as_of=None):
        cutoff = as_of or self._execution.source_time
        return [
            bar.model_copy(update={"instrument_id": instrument_id})
            for bar in self._bars
            if bar.end_time <= cutoff
        ]

    def set_execution_time(self, observed_at: datetime) -> None:
        self._execution = self._execution.model_copy(
            update={
                "source_time": observed_at,
                "received_at": observed_at,
                "bar_start_time": observed_at - timedelta(minutes=1),
            }
        )


def _load_fixture():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _candidate(fixture) -> GapperCandidate:
    selected = fixture["selected"]
    assumptions = fixture["execution_assumptions"]
    return GapperCandidate(
        instrument_id=str(selected["instrument_id"]),
        binding_id=str(selected["binding_id"]),
        observed_at=datetime.fromisoformat(fixture["capture_time_utc"]),
        previous_close=Decimal(str(selected["previous_close"])),
        premarket_price=Decimal(str(selected["premarket_price"])),
        gap_pct=Decimal(str(selected["gap_pct"])),
        premarket_volume=Decimal(str(assumptions["premarket_volume"])),
        premarket_dollar_volume=Decimal(str(assumptions["premarket_dollar_volume"])),
        tod_rvol=Decimal(str(assumptions["tod_rvol"])),
        market_cap=Decimal(str(selected["market_cap"])),
        spread_bps=Decimal(str(assumptions["candidate_spread_bps"])),
        catalyst_evidence_ids=("live-ai-e2e-catalyst",),
        discovery_rank=1,
    )


def _bars(fixture, instrument_id: str) -> list[MarketBar]:
    values = []
    for row in fixture["replay_bars"]:
        start = OPEN_UTC + timedelta(minutes=int(row["minute"]))
        values.append(
            MarketBar(
                instrument_id=instrument_id,
                interval="1m",
                start_time=start,
                end_time=start + timedelta(minutes=1),
                open=Decimal(str(row["open"])),
                high=Decimal(str(row["high"])),
                low=Decimal(str(row["low"])),
                close=Decimal(str(row["close"])),
                volume=Decimal(str(row["volume"])),
                is_final=True,
                session="regular",
                provider="live-ai-e2e-replay",
                received_at=start + timedelta(minutes=1),
            )
        )
    return values


def _execution(candidate: GapperCandidate) -> ExecutionObservation:
    # Coherent, fresh, executable point-in-time book for the final replay bar.
    observed_at = OPEN_UTC + timedelta(minutes=11)
    return ExecutionObservation(
        instrument_id=candidate.instrument_id,
        binding_id=str(candidate.binding_id),
        provider="live-ai-e2e-replay",
        bid=Decimal("4.89"),
        ask=Decimal("4.90"),
        bid_size=Decimal("100000"),
        ask_size=Decimal("100000"),
        last=Decimal("4.895"),
        high=Decimal("4.90"),
        low=Decimal("4.89"),
        bar_volume=Decimal("500000"),
        bar_start_time=observed_at - timedelta(minutes=1),
        cumulative_volume=Decimal("1590000"),
        source_time=observed_at,
        received_at=observed_at,
        session="regular",
        freshness_mode="polled",
        halted=False,
        execution_eligible=True,
    )


def _build_fixture_world():
    fixture = _load_fixture()
    config = managed_finviz_shadow_document("live-ai-e2e-paper")
    candidate = _candidate(fixture)
    bars = _bars(fixture, candidate.instrument_id)
    marker = datetime.combine(
        SESSION_DATE,
        config.config.universe_scan_time_et,
        tzinfo=_ET,
    )
    universe_id = _archive_universe_id(config, marker)
    universe = freeze_gapper_universe(
        universe_id=universe_id,
        session_date=SESSION_DATE,
        evaluation_time=datetime.fromisoformat(fixture["capture_time_utc"]),
        discovery_source="finviz",
        source_locator=str(fixture["source_url"]),
        source_candidate_symbols=tuple(fixture["source_candidate_symbols"]),
        candidates=[candidate],
    )
    repository = MemoryStrategyRepository(config, universe)
    market = ReplayMarketService(bars, _execution(candidate))
    return config, candidate, bars, repository, market, universe


def _execution_probe_row(config, candidate, bars, universe_id, observed_at):
    structure = list(resample_final_bars(bars, config.config.structure_interval))
    deterministic = evaluate_gap_pullback(candidate, structure, config.config)
    learning = build_intraday_learning_snapshot(candidate, deterministic, bars)
    indicators = multi_timeframe_indicator_context(bars)
    execution = {
        "bid": Decimal("4.89"),
        "ask": Decimal("4.90"),
        "last": Decimal("4.895"),
        "spread_bps": Decimal("20.42900919305413687436159346"),
        "execution_eligible": True,
        "halted": False,
        "freshness_mode": "polled",
        "rejection_reasons": (),
    }
    snapshot = feature_snapshot(
        candidate=candidate,
        deterministic=deterministic,
        learning=learning,
        indicators=indicators,
        bars=bars,
        execution=execution,
        cohort_rank=1,
        position=AIShadowPositionState(policy="minute", instrument_id=candidate.instrument_id),
    )
    return {
        "candidate": candidate,
        "bars": bars,
        "deterministic": deterministic,
        "learning": learning,
        "indicators": indicators,
        "execution": execution,
        "observed_at": observed_at,
        "universe_id": universe_id,
        "rank": 1,
        "positions": {
            "minute": AIShadowPositionState(policy="minute", instrument_id=candidate.instrument_id),
            "event": AIShadowPositionState(policy="event", instrument_id=candidate.instrument_id),
        },
        "feature_snapshot": snapshot,
    }


@pytest.mark.skipif(
    not RUN_LIVE,
    reason="Set OMNIX_RUN_LIVE_AI_TRADING_E2E=1 to run the real-provider AI trading E2E",
)
def test_live_ai_trading_end_to_end() -> None:
    """Real-provider AI-shadow E2E over frozen causal market evidence.

    Phase A uses the production monitor end-to-end through the dedicated provider,
    native structured output, batch/decision persistence, and research-only action
    handling. Phase B deterministically probes the production simulated-fill path
    so the E2E remains stable even when the real model correctly chooses SKIP.
    """

    reset_ai_shadow_reliability_state()
    try:
        config, candidate, bars, repository, market, universe = _build_fixture_world()

        provider = get_trading_research_provider()
        assert provider is not None, (
            "No configured LLM provider is available. Configure Omnix's LLM provider "
            "first (for Codex, ensure the Codex CLI is installed/authenticated; for "
            "LM Studio, ensure its local API server is running)."
        )
        provider_name = str(
            getattr(provider, "provider_name", "") or type(provider).__name__
        )
        if EXPECTED_PROVIDER:
            assert provider_name.casefold() == EXPECTED_PROVIDER, (
                f"Expected provider {EXPECTED_PROVIDER!r}, got {provider_name!r}"
            )

        monitor = TradingAIShadowMonitor(
            strategy_repository_factory=lambda: repository,
            market_service_factory=lambda: market,
            now_factory=lambda: NOW_UTC,
            interval_seconds=5,
        )
        decisions = asyncio.run(monitor.run_once())

        batches = [event for event in repository.events if event.event_type == "ai_shadow_batch"]
        complete_batches = [event for event in batches if event.state == "complete"]
        error_batches = [event for event in batches if event.state == "error"]
        live_decisions = [
            event
            for event in repository.events
            if event.event_type == "ai_shadow_decision"
            and event.instrument_id == candidate.instrument_id
        ]
        live_actions = [str(event.payload.get("effective_action")) for event in live_decisions]

        assert monitor.last_error is None
        assert error_batches == []
        assert len(complete_batches) == 2, "minute and event policies must both complete"
        assert decisions == 2
        assert len(live_decisions) == 2
        assert {event.payload["policy"] for event in live_decisions} == {"minute", "event"}
        assert all(event.payload["execution_authority"] is False for event in live_decisions)
        assert all(event.payload["research_only"] is True for event in live_decisions)
        assert all(event.payload.get("provider") for event in complete_batches)
        assert monitor.total_token_count > 0
        assert not any(event.event_type == "entry_order_submitted" for event in repository.events)

        if REQUIRE_LIVE_ENTRY:
            assert "enter" in live_actions, (
                "The real model returned valid decisions but did not choose ENTER. "
                "Unset OMNIX_AI_TRADING_E2E_REQUIRE_LIVE_ENTRY for the stable contract E2E."
            )

        # Always exercise the production research fill simulator, independent of
        # whether the live model chose ENTER. Use a distinct probe instrument so
        # a legitimate live ENTER cannot suppress this lifecycle assertion.
        probe_at = NOW_UTC + timedelta(seconds=1)
        probe_candidate = candidate.model_copy(
            update={
                "instrument_id": "equity:AI_E2E_PROBE",
                "binding_id": "replay:AI_E2E_PROBE",
            }
        )
        probe_bars = [
            bar.model_copy(update={"instrument_id": probe_candidate.instrument_id})
            for bar in bars
        ]
        # The shared paper-execution-v2 policy requires its 250 ms activation
        # latency to elapse before an execution observation can fill the probe.
        market.set_execution_time(probe_at + timedelta(seconds=1))
        probe_row = _execution_probe_row(
            config,
            probe_candidate,
            probe_bars,
            universe.universe_id,
            probe_at,
        )
        forced_entry = AIShadowDecision(
            instrument_id=probe_candidate.instrument_id,
            action="enter",
            confidence=100,
            market_regime="failed_selloff",
            expected_horizon_minutes=30,
            thesis="E2E execution-contract probe.",
            reason="Exercise the production research-only fill lifecycle.",
            invalidation_price=Decimal("4.60"),
        )
        asyncio.run(
            monitor._apply_decision(
                policy="minute",
                decision=forced_entry,
                row=probe_row,
                candidate=probe_candidate,
                bars=probe_bars,
                config=config,
                repository=repository,
                market_service=market,
                events=list(repository.events),
                result=probe_row["learning"],
                batch_result=None,
                trigger_reasons=("e2e_execution_contract_probe",),
            )
        )

        probe_decisions = [
            event
            for event in repository.events
            if event.event_type == "ai_shadow_decision"
            and event.instrument_id == probe_candidate.instrument_id
        ]
        probe_fills = [
            event
            for event in repository.events
            if event.event_type == "ai_shadow_fill"
            and event.instrument_id == probe_candidate.instrument_id
        ]
        assert len(probe_decisions) == 1
        assert len(probe_fills) == 1
        assert probe_fills[0].state == "filled"
        assert probe_fills[0].reason_code == "AI_SHADOW_FILL_SIMULATED"
        assert probe_fills[0].payload["execution_authority"] is False
        assert probe_fills[0].payload["research_only"] is True
        assert not any(event.event_type == "entry_order_submitted" for event in repository.events)

        print(
            "LIVE AI TRADING E2E PASS "
            f"provider={provider_name} "
            f"model={complete_batches[0].payload.get('model')} "
            f"live_actions={','.join(live_actions)} "
            f"live_batches={len(complete_batches)} "
            f"live_decisions={len(live_decisions)} "
            f"tokens={monitor.total_token_count} "
            "execution_probe=filled "
            "execution_authority=false"
        )
    finally:
        reset_ai_shadow_reliability_state()
