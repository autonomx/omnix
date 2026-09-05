from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.trading import paper_monitor as paper_monitor_module
from app.trading import strategy_monitor as strategy_monitor_module
from app.trading.execution import ExecutionObservation
from app.trading.gapper_dataset import GapperCandidate, freeze_gapper_universe
from app.trading.models import MarketBar
from app.trading.paper import (
    PaperAccount,
    PaperAccountSnapshot,
    PaperBalance,
    PaperExecutionPolicy,
    PaperFill,
    PaperOrder,
    PaperOrderRequest,
    PaperPosition,
    paper_buy_reservation,
    paper_fill_decision,
    paper_fill_is_fundable,
    paper_fill_key,
)
from app.trading.paper_monitor import TradingPaperMonitor
from app.trading.strategies.gap_pullback import evaluate_gap_pullback
from app.trading.strategies.models import StrategyRiskProfile
from app.trading.strategy_data_integrity import finviz_atomic_source_locator
from app.trading.strategy_monitor import TradingStrategyMonitor
from app.trading.strategy_repository import (
    StrategyEvent,
    StrategyProtection,
    TradingStrategyConfigDocument,
)
from app.trading.strategy_universe_archiver import _archive_universe_id
from app.trading.strategy_v2_qualification import (
    PROSPECTIVE_ECONOMIC_POLICY_VERSION,
    V2_PROSPECTIVE_START,
    V2_QUALIFICATION_VERSION,
    V2_REPLAY_VERSION,
    evaluate_v2_prospective_qualification,
    managed_finviz_v2_config,
    v2_profile_fingerprint,
)


FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "2026-09-03-auto-paper-e2e.json"
)
SOURCE_SESSION_DATE = date(2026, 9, 3)
# Replay the Sep 3 market example on a later synthetic session so the full
# 15-session/20-trade qualification policy can have matured before AUTO PAPER.
REPLAY_SESSION_DATE = date(2026, 10, 1)
REPLAY_CAPTURE_UTC = datetime(2026, 10, 1, 13, 16, 18, tzinfo=timezone.utc)
REPLAY_OPEN_UTC = datetime(2026, 10, 1, 13, 30, tzinfo=timezone.utc)
REPLAY_RUNTIME_NOW = datetime(2026, 10, 1, 14, 0, tzinfo=timezone.utc)  # 10:00 ET
_ET = ZoneInfo("America/New_York")


def _frozen_datetime(now: datetime):
    class FrozenRuntimeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return now.replace(tzinfo=None)
            return now.astimezone(tz)

    return FrozenRuntimeDateTime


class InMemoryStrategyRepository:
    def __init__(self, config: TradingStrategyConfigDocument, universe) -> None:
        self.config = config
        self.universe = universe
        self.events: list[StrategyEvent] = []
        self._event_keys: set[str] = set()
        self.protections: dict[str, StrategyProtection] = {}
        self.archive_requests: list[str] = []

    def list_configs(self, active_only=True):
        if active_only and (not self.config.enabled or self.config.mode == "off"):
            return []
        return [self.config]

    def get_universe(self, universe_id):
        self.archive_requests.append(universe_id)
        if universe_id != self.universe.universe_id:
            raise ValueError("gapper_universe_not_found")
        return self.universe

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

    def append_event(self, event: StrategyEvent):
        if event.idempotency_key in self._event_keys:
            return False
        self._event_keys.add(event.idempotency_key)
        self.events.append(event)
        return True

    def entry_events_between(self, strategy_id, *, start_time, end_time):
        return [
            event
            for event in self.events
            if event.strategy_id == strategy_id
            and event.event_type == "entry_order_submitted"
            and start_time <= event.observed_at < end_time
        ]

    def daily_paper_pnl(self, account_id, *, start_time, end_time):
        return Decimal("0")

    def recent_events(self, strategy_id, limit):
        values = [event for event in self.events if event.strategy_id == strategy_id]
        return values[-limit:]

    def list_protections(self, strategy_id, *, active_only=True):
        values = [
            item.model_copy(deep=True)
            for item in self.protections.values()
            if item.strategy_id == strategy_id
        ]
        if active_only:
            values = [
                item
                for item in values
                if item.status in {"pending_entry", "active", "exit_submitted"}
            ]
        return values

    def save_protection(self, protection: StrategyProtection):
        previous = self.protections.get(protection.protection_id)
        revision = 1 if previous is None else previous.revision + 1
        saved = protection.model_copy(deep=True, update={"revision": revision})
        self.protections[saved.protection_id] = saved
        return saved.model_copy(deep=True)


class InMemoryPaperRepository:
    """Paper repository adapter that uses the production paper fill rules."""

    def __init__(self, account_id: str, *, now: datetime) -> None:
        self.now = now
        self.account = PaperAccount(
            account_id=account_id,
            name="Sep 3 E2E Paper",
            base_currency="USD",
            commission_bps=Decimal("0"),
            enabled=True,
            revision=1,
            created_at=self.now,
            updated_at=self.now,
        )
        self.balance = PaperBalance(
            currency="USD",
            available=Decimal("10000"),
            reserved=Decimal("0"),
        )
        self.orders: dict[str, PaperOrder] = {}
        self.positions: dict[str, PaperPosition] = {}
        self.fills: list[PaperFill] = []
        self.policy = PaperExecutionPolicy(
            latency_ms=0,
            max_volume_participation_pct=Decimal("1"),
            max_observation_age_seconds=Decimal("60"),
        )

    def list_accounts(self, limit=100):
        return [self.account]

    def snapshot(self, account_id):
        if account_id != self.account.account_id:
            raise ValueError("paper_account_not_found")
        history = list(self.orders.values())
        return PaperAccountSnapshot(
            account=self.account.model_copy(deep=True),
            balances=[self.balance.model_copy(deep=True)],
            positions=[
                item.model_copy(deep=True)
                for item in self.positions.values()
                if item.quantity != 0
            ],
            open_orders=[
                item.model_copy(deep=True)
                for item in history
                if item.status == "open"
            ],
            order_history=[item.model_copy(deep=True) for item in history],
            recent_fills=[item.model_copy(deep=True) for item in self.fills],
            recent_ledger=[],
        )

    def place_order(self, account_id, request: PaperOrderRequest):
        if account_id != self.account.account_id:
            raise ValueError("paper_account_not_found")
        existing = self.orders.get(request.order_id)
        if existing is not None:
            if existing.idempotency_key == request.idempotency_key:
                return existing.model_copy(deep=True)
            raise ValueError("paper_order_id_conflict")

        reserved_cash = paper_buy_reservation(
            request,
            available_cash=self.balance.available,
            commission_bps=self.account.commission_bps,
        )
        if request.side == "buy" and reserved_cash > self.balance.available:
            raise ValueError("insufficient_paper_cash")
        if request.side == "buy":
            self.balance.available -= reserved_cash
            self.balance.reserved += reserved_cash

        order = PaperOrder(
            account_id=account_id,
            **request.model_dump(),
            reserved_cash=reserved_cash,
            created_at=self.now,
            updated_at=self.now,
        )
        self.orders[order.order_id] = order
        return order.model_copy(deep=True)

    def process_observation(self, account_id, observation):
        if account_id != self.account.account_id:
            raise ValueError("paper_account_not_found")

        fills: list[PaperFill] = []
        for order_id, order in list(self.orders.items()):
            if order.status != "open" or order.instrument_id != observation.instrument_id:
                continue
            decision = paper_fill_decision(order, observation, self.policy)
            if not decision.should_fill:
                continue

            assert decision.fill_price is not None
            assert decision.fill_quantity is not None
            quantity = decision.fill_quantity
            price = decision.fill_price
            notional = quantity * price
            if not paper_fill_is_fundable(
                order,
                total_cost=notional,
                available_cash=self.balance.available,
            ):
                raise ValueError("insufficient_paper_cash")

            key = paper_fill_key(account_id, order.order_id, observation)
            fill = PaperFill(
                fill_id=f"fill-{key[:32]}",
                order_id=order.order_id,
                instrument_id=order.instrument_id,
                side=order.side,
                quantity=quantity,
                price=price,
                commission=Decimal("0"),
                source_time=observation.source_time,
                evaluated_at=observation.evaluated_at,
                idempotency_key=key,
            )
            fills.append(fill)
            self.fills.append(fill)

            total_filled = order.filled_quantity + quantity
            filled_order = order.model_copy(
                update={
                    "filled_quantity": total_filled,
                    "average_fill_price": price,
                    "status": "filled" if total_filled >= order.quantity else "open",
                    "updated_at": observation.evaluated_at,
                }
            )
            self.orders[order_id] = filled_order

            if order.side == "buy":
                self.balance.reserved -= order.reserved_cash
                self.balance.available += order.reserved_cash - notional
                current = self.positions.get(order.instrument_id)
                if current is None:
                    self.positions[order.instrument_id] = PaperPosition(
                        instrument_id=order.instrument_id,
                        quantity=quantity,
                        average_cost=price,
                        realized_pnl=Decimal("0"),
                        last_price=price,
                    )
                else:
                    new_quantity = current.quantity + quantity
                    new_average = (
                        current.average_cost * current.quantity + price * quantity
                    ) / new_quantity
                    self.positions[order.instrument_id] = current.model_copy(
                        update={
                            "quantity": new_quantity,
                            "average_cost": new_average,
                            "last_price": price,
                        }
                    )

        return fills


class NoPaperProtections:
    def list(self, account_id, *, active_only=True):
        return []

    def get(self, *args, **kwargs):
        raise ValueError("paper_protection_not_found")


class ReplayMarketService:
    def __init__(
        self,
        bars: list[MarketBar],
        fixture: dict[str, object],
        *,
        now: datetime,
    ) -> None:
        self._bars = bars
        assumptions = fixture["execution_assumptions"]
        assert isinstance(assumptions, dict)
        selected = fixture["selected"]
        assert isinstance(selected, dict)
        self.instrument_id = str(selected["instrument_id"])
        self.binding_id = str(selected["binding_id"])
        self.execution = ExecutionObservation(
            instrument_id=self.instrument_id,
            binding_id=self.binding_id,
            provider="sep3-e2e-replay",
            bid=Decimal(str(assumptions["execution_bid"])),
            ask=Decimal(str(assumptions["execution_ask"])),
            bid_size=Decimal(str(assumptions["displayed_size"])),
            ask_size=Decimal(str(assumptions["displayed_size"])),
            last=Decimal(str(assumptions["execution_last"])),
            high=Decimal(str(assumptions["execution_ask"])),
            low=Decimal(str(assumptions["execution_bid"])),
            bar_volume=Decimal("100000"),
            bar_start_time=now,
            cumulative_volume=Decimal("2500000"),
            source_time=now,
            received_at=now,
            session="regular",
            freshness_mode="polled",
            halted=False,
            execution_eligible=True,
        )

    def bars(self, instrument_id, interval, limit, binding_id):
        assert instrument_id == self.instrument_id
        assert interval == "1m"
        assert binding_id == self.binding_id
        return SimpleNamespace(bars=list(self._bars))

    def execution_observation(self, instrument_id, binding_id=None):
        assert instrument_id == self.instrument_id
        assert binding_id in {None, self.binding_id}
        return self.execution


def _load_fixture() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _build_bars(fixture: dict[str, object]) -> list[MarketBar]:
    selected = fixture["selected"]
    assert isinstance(selected, dict)
    rows = fixture["replay_bars"]
    assert isinstance(rows, list)
    bars: list[MarketBar] = []
    for row in rows:
        assert isinstance(row, dict)
        start = REPLAY_OPEN_UTC + timedelta(minutes=int(row["minute"]))
        bars.append(
            MarketBar(
                instrument_id=str(selected["instrument_id"]),
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
                provider="sep3-e2e-replay",
                received_at=start + timedelta(minutes=1),
            )
        )
    return bars



def _qualification_event(
    *,
    strategy_id: str,
    event_type: str,
    instrument_id: str,
    observed_at: datetime,
    reason_code: str,
    payload: dict[str, object],
    suffix: str,
) -> StrategyEvent:
    raw = (
        f"{strategy_id}|{event_type}|{instrument_id}|"
        f"{observed_at.isoformat()}|{suffix}"
    )
    idem = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return StrategyEvent(
        strategy_id=strategy_id,
        event_id=idem[:32],
        instrument_id=instrument_id,
        event_type=event_type,
        state="entry_ready",
        reason_code=reason_code,
        observed_at=observed_at,
        idempotency_key=idem,
        payload=payload,
    )


def _seed_reviewed_managed_finviz_qualification(
    repository: InMemoryStrategyRepository,
    config: TradingStrategyConfigDocument,
) -> None:
    """Persist an exact-profile evidence corpus that production qualification accepts."""

    profile = v2_profile_fingerprint(config.config)
    sessions: list[date] = []
    cursor = V2_PROSPECTIVE_START
    while len(sessions) < 20:
        if cursor.weekday() < 5:
            sessions.append(cursor)
        cursor += timedelta(days=1)

    for index, session in enumerate(sessions):
        instrument = f"equity:QUAL{index % 10}"
        signal_at = datetime.combine(session, time(14, 0), tzinfo=timezone.utc)
        entry_at = signal_at + timedelta(minutes=1)
        universe_id = f"auto-archive-{session.isoformat()}-0915-finviz-e2e"

        repository.append_event(
            _qualification_event(
                strategy_id=config.strategy_id,
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
                    "profile_fingerprint": profile,
                    "execution_authority": False,
                    "execution": {"execution_eligible": True},
                },
            )
        )
        repository.append_event(
            _qualification_event(
                strategy_id=config.strategy_id,
                event_type="v2_shadow_replay_trade",
                instrument_id=instrument,
                observed_at=entry_at + timedelta(hours=2),
                reason_code="V2_SHADOW_REPLAY_TRADE",
                suffix=f"replay-{index}",
                payload={
                    "qualification_version": V2_QUALIFICATION_VERSION,
                    "replay_version": V2_REPLAY_VERSION,
                    "session_date": session.isoformat(),
                    "universe_id": universe_id,
                    "universe_source": "auto_archive_shadow",
                    "profile_fingerprint": profile,
                    "entry_time": entry_at.isoformat(),
                    "exit_time": (entry_at + timedelta(minutes=20)).isoformat(),
                    "r_result": "0.50",
                    "execution_authority": False,
                },
            )
        )

    review_at = max(event.observed_at for event in repository.events) + timedelta(minutes=1)
    repository.append_event(
        _qualification_event(
            strategy_id=config.strategy_id,
            event_type="prospective_economic_auto_paper_review",
            instrument_id=f"strategy:{config.strategy_id}",
            observed_at=review_at,
            reason_code="PROSPECTIVE_ECONOMIC_AUTO_PAPER_REVIEW_APPROVED",
            suffix="economic-review",
            payload={
                "policy_version": PROSPECTIVE_ECONOMIC_POLICY_VERSION,
                "profile_fingerprint": "profile-bound-e2e-economic-review",
                "v2_profile_fingerprint": profile,
                "pipeline_evidence_fingerprint": "pipeline-bound-e2e-review",
                "approved": True,
                "review_note": "Synthetic reviewed evidence state for local AUTO PAPER E2E.",
                "execution_authority": False,
            },
        )
    )

    before_review = evaluate_v2_prospective_qualification(config, repository.events)
    assert before_review.profile_match is True
    assert before_review.matched_eligible_trade_count == 20
    assert before_review.distinct_sessions == 20
    assert before_review.distinct_symbols == 10
    assert before_review.qualified is True
    assert before_review.reviewed is False
    assert before_review.auto_paper_authorized is False

    operator_review_at = review_at + timedelta(minutes=1)
    repository.append_event(
        _qualification_event(
            strategy_id=config.strategy_id,
            event_type="v2_promotion_review",
            instrument_id=f"strategy:{config.strategy_id}",
            observed_at=operator_review_at,
            reason_code="V2_PROMOTION_REVIEW_APPROVED",
            suffix="operator-review",
            payload={
                "qualification_version": V2_QUALIFICATION_VERSION,
                "profile_fingerprint": profile,
                "evidence_fingerprint": before_review.evidence_fingerprint,
                "approved": True,
                "review_note": "Exact managed Finviz V2 evidence reviewed for local E2E.",
                "execution_authority": False,
            },
        )
    )

    authorized = evaluate_v2_prospective_qualification(config, repository.events)
    assert authorized.auto_paper_authorized is True


def test_sep3_tlys_auto_paper_runtime_places_fills_and_protects_trade(
    monkeypatch,
) -> None:
    """One local command proves the paper execution path actually trades.

    This is intentionally deterministic and network-free. The frozen Sep 3
    cohort/TLYS references are historical inputs; the 1-minute bars are an
    explicit replay fixture, not a claim that TLYS produced this exact signal.
    The Sep 3 prices/cohort are replayed on a later synthetic session because
    Sep 3 itself was too early for the frozen 15-session qualification floor.
    The test seeds exact-profile durable evidence, runs the real V2 qualification
    evaluator, and then exercises the production AUTO PAPER/paper-fill path.
    """

    fixture = _load_fixture()
    selected = fixture["selected"]
    assumptions = fixture["execution_assumptions"]
    assert isinstance(selected, dict)
    assert isinstance(assumptions, dict)

    v2 = managed_finviz_v2_config()
    config = TradingStrategyConfigDocument(
        strategy_id="sep3-tlys-auto-paper-e2e",
        account_id="paper-sep3-e2e",
        strategy_kind="gap_pullback_v1",
        strategy_version=v2.strategy_version,
        mode="auto_paper",
        active_universe_id=None,
        config=v2,
        risk=StrategyRiskProfile(),
        enabled=True,
    )

    assert date.fromisoformat(str(fixture["session_date"])) == SOURCE_SESSION_DATE
    capture_time = REPLAY_CAPTURE_UTC
    candidate = GapperCandidate(
        instrument_id=str(selected["instrument_id"]),
        binding_id=str(selected["binding_id"]),
        observed_at=capture_time,
        previous_close=Decimal(str(selected["previous_close"])),
        premarket_price=Decimal(str(selected["premarket_price"])),
        gap_pct=Decimal(str(selected["gap_pct"])),
        premarket_volume=Decimal(str(assumptions["premarket_volume"])),
        premarket_dollar_volume=Decimal(
            str(assumptions["premarket_dollar_volume"])
        ),
        premarket_bar_count=8,
        tod_rvol=Decimal(str(assumptions["tod_rvol"])),
        market_data_complete=True,
        market_cap=Decimal(str(selected["market_cap"])),
        spread_bps=Decimal(str(assumptions["candidate_spread_bps"])),
        discovery_rank=1,
    )

    marker = datetime.combine(
        REPLAY_SESSION_DATE,
        config.config.universe_scan_time_et,
        tzinfo=_ET,
    )
    universe_id = _archive_universe_id(config, marker)
    universe = freeze_gapper_universe(
        universe_id=universe_id,
        session_date=REPLAY_SESSION_DATE,
        evaluation_time=capture_time,
        discovery_source="finviz",
        source_locator=finviz_atomic_source_locator(str(fixture["source_url"])),
        source_candidate_symbols=tuple(fixture["source_candidate_symbols"]),
        candidates=[candidate],
    )
    bars = _build_bars(fixture)

    causal = evaluate_gap_pullback(candidate, bars, config.config)
    assert causal.state == "entry_ready"
    assert causal.signal is not None
    assert causal.reason_code == "FAILED_SELLOFF_V2_TIMING_BREAK"

    strategy_repository = InMemoryStrategyRepository(config, universe)
    _seed_reviewed_managed_finviz_qualification(strategy_repository, config)
    paper_repository = InMemoryPaperRepository(
        config.account_id,
        now=REPLAY_RUNTIME_NOW,
    )
    market_service = ReplayMarketService(
        bars,
        fixture,
        now=REPLAY_RUNTIME_NOW,
    )

    frozen_clock = _frozen_datetime(REPLAY_RUNTIME_NOW)
    monkeypatch.setattr(strategy_monitor_module, "datetime", frozen_clock)
    monkeypatch.setattr(paper_monitor_module, "datetime", frozen_clock)

    strategy_monitor = TradingStrategyMonitor(
        strategy_repository_factory=lambda: strategy_repository,
        paper_repository_factory=lambda: paper_repository,
        market_service_factory=lambda: market_service,
        interval_seconds=5,
    )
    paper_monitor = TradingPaperMonitor(
        repository_factory=lambda: paper_repository,
        protection_repository_factory=lambda: NoPaperProtections(),
        market_service_factory=lambda: market_service,
        interval_seconds=5,
        active_interval_seconds=1,
    )

    async def run_replay() -> None:
        submitted = await strategy_monitor.run_once()
        assert submitted == 1
        assert strategy_monitor.paper_order_count == 1
        assert strategy_monitor.auto_paper_ready_strategy_count == 1
        assert strategy_monitor.auto_paper_blocked_strategy_count == 0

        readiness = strategy_monitor.auto_paper_readiness_by_strategy[
            config.strategy_id
        ]
        assert readiness["state"] == "ready"
        assert readiness["reason"] == "qualified_daily_universe_ready"
        assert readiness["universe_id"] == universe_id
        assert readiness["paper_execution_authority"] is True

        filled = await paper_monitor.run_once()
        assert filled == 1
        assert paper_monitor.fill_count == 1

        # The next strategy cycle reconciles the filled entry and activates the
        # strategy-owned protection without creating a duplicate paper entry.
        submitted_again = await strategy_monitor.run_once()
        assert submitted_again == 0
        assert strategy_monitor.paper_order_count == 1

    asyncio.run(run_replay())

    snapshot = paper_repository.snapshot(config.account_id)
    assert len(snapshot.order_history) == 1
    entry_order = snapshot.order_history[0]
    assert entry_order.side == "buy"
    assert entry_order.status == "filled"
    assert entry_order.filled_quantity == entry_order.quantity
    assert entry_order.average_fill_price is not None

    assert len(snapshot.recent_fills) == 1
    fill = snapshot.recent_fills[0]
    assert fill.order_id == entry_order.order_id
    assert fill.instrument_id == str(selected["instrument_id"])
    assert fill.quantity == entry_order.quantity

    position = next(
        item
        for item in snapshot.positions
        if item.instrument_id == str(selected["instrument_id"])
    )
    assert position.quantity == fill.quantity
    assert position.average_cost == fill.price
    assert snapshot.balances[0].available < Decimal("10000")

    protections = strategy_repository.list_protections(
        config.strategy_id,
        active_only=True,
    )
    assert len(protections) == 1
    assert protections[0].status == "active"
    assert protections[0].entry_order_id == entry_order.order_id

    event_types = [event.event_type for event in strategy_repository.events]
    for required in (
        "data_integrity",
        "state",
        "risk_decision",
        "entry_order_submitted",
        "protection",
    ):
        assert required in event_types

    assert strategy_repository.archive_requests
    assert set(strategy_repository.archive_requests) == {universe_id}

    print(
        "AUTO PAPER E2E PASS "
        f"symbol={selected['symbol']} "
        f"order={entry_order.order_id} "
        f"qty={entry_order.quantity} "
        f"fill={fill.price} "
        f"position={position.quantity} "
        f"protection={protections[0].status}"
    )
