import threading
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.apps.trading import ibkr_market_data_monitor as monitor_module
from app.apps.trading.execution import ExecutionObservation, assess_execution_observation
from app.apps.trading.execution_observation_plane import ExecutionObservationPlane
from app.apps.trading.evidence_storage import MemoryIbkrSessionEvidence
from app.apps.trading.held_quote_demand import HeldQuoteDemand
from app.apps.trading.ibkr_evidence import IbkrEvidenceStore
from app.apps.trading.ibkr_market_data_monitor import TradingIbkrMarketDataMonitor
from app.apps.trading.streaming.manager import StreamingQuoteUpdate


ET = ZoneInfo("America/New_York")
INSTRUMENT = "equity:NASDAQ:AAPL"
NOW = datetime(2026, 9, 17, 14, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _no_held_quotes(monkeypatch):
    # Monitors read the process's held-quote demand; stocks other tests' arms held stay out of it.
    monkeypatch.setattr(monitor_module, "default_held_quote_demand", HeldQuoteDemand)


def _monitor(tmp_path):
    plane = ExecutionObservationPlane()
    store = IbkrEvidenceStore(MemoryIbkrSessionEvidence())
    monitor = TradingIbkrMarketDataMonitor(
        plane=plane,
        evidence_store=store,
        now_factory=lambda: NOW,
    )
    return monitor, plane, store


def test_ibkr_monitor_preserves_entitlement_and_contract_provenance(tmp_path):
    monitor, plane, store = _monitor(tmp_path)
    update = StreamingQuoteUpdate(
        binding_id="ibkr:socket:" + INSTRUMENT,
        instrument_id=INSTRUMENT,
        provider="ibkr",
        source_time=NOW,
        received_at=NOW,
        bid=Decimal("100.00"),
        ask=Decimal("100.02"),
        last=Decimal("100.01"),
        market_data_type="LIVE",
        live_entitled=True,
        contract_id="265598",
        primary_exchange="NASDAQ",
        local_symbol="AAPL",
        provider_sequence=7,
    )

    monitor._record_quote(update)

    envelope = plane.latest(INSTRUMENT)
    assert envelope is not None
    observation = envelope.observation
    assert observation.binding_purpose == "LIVE_DATA"
    assert observation.market_data_type == "LIVE"
    assert observation.live_entitled is True
    assert observation.contract_id == "265598"
    assert observation.primary_exchange == "NASDAQ"
    assert observation.local_symbol == "AAPL"
    assert observation.market_data_eligible is True
    assert observation.broker_execution_authorized is False

    metrics = store.session_diagnostics(NOW.astimezone(ET).date())
    assert metrics["quote_event_count"] == 1
    assert metrics["live_quote_event_count"] == 1


def test_ibkr_monitor_records_live_vs_iex_comparison_without_changing_execution_authority(tmp_path):
    monitor, plane, store = _monitor(tmp_path)
    iex = ExecutionObservation(
        instrument_id=INSTRUMENT,
        binding_id="alpaca_iex:rest:" + INSTRUMENT,
        provider="alpaca_iex",
        bid=Decimal("100.00"),
        ask=Decimal("100.04"),
        last=Decimal("100.02"),
        source_time=NOW,
        received_at=NOW,
        session="regular",
        freshness_mode="live",
    )
    plane.record(assess_execution_observation(iex), recorded_at=NOW)

    monitor._record_quote(
        StreamingQuoteUpdate(
            binding_id="ibkr:socket:" + INSTRUMENT,
            instrument_id=INSTRUMENT,
            provider="ibkr",
            source_time=NOW,
            received_at=NOW,
            bid=Decimal("100.01"),
            ask=Decimal("100.03"),
            last=Decimal("100.02"),
            market_data_type="LIVE",
            live_entitled=True,
            contract_id="265598",
            primary_exchange="NASDAQ",
            local_symbol="AAPL",
            provider_sequence=8,
        )
    )

    metrics = store.session_diagnostics(NOW.astimezone(ET).date())
    assert metrics["iex_comparison_count"] == 1
    assert Decimal(metrics["last_price_diff_bps_mean"]) == Decimal("0")
    # Existing paper-fill observation remains EXECUTION; IBKR remains LIVE_DATA.
    assert any(
        row.observation.binding_purpose == "EXECUTION"
        for row in plane.observations(INSTRUMENT)
    )
    assert any(
        row.observation.binding_purpose == "LIVE_DATA"
        for row in plane.observations(INSTRUMENT)
    )


def test_ibkr_monitor_records_missing_last_as_durable_soak_failure(tmp_path):
    monitor, _, store = _monitor(tmp_path)
    monitor._record_quote(
        StreamingQuoteUpdate(
            binding_id="ibkr:socket:" + INSTRUMENT,
            instrument_id=INSTRUMENT,
            provider="ibkr",
            source_time=NOW,
            received_at=NOW,
            bid=Decimal("100"),
            ask=Decimal("100.01"),
            last=None,
            market_data_type="LIVE",
            live_entitled=True,
            contract_id="265598",
        )
    )

    metrics = store.session_diagnostics(NOW.astimezone(ET).date())
    assert metrics["missing_quote_count"] == 1
    assert metrics["reason_counts"]["IBKR_LAST_MISSING"] == 1


def test_execution_observation_monitor_does_not_own_ibkr_subscriptions():
    source = Path("src/app/apps/trading/execution_observation_monitor.py").read_text(
        encoding="utf-8"
    ).lower()

    assert "subscribe_quote" not in source
    assert "ibkr" not in source


def test_ibkr_monitor_market_data_line_budget_preserves_existing_lines(tmp_path):
    monitor, _, _ = _monitor(tmp_path)
    monitor.market_data_line_budget = 2
    monitor._keys = {
        "equity:NASDAQ:BBB": "key-bbb",
        "equity:NASDAQ:CCC": "key-ccc",
    }

    admitted = monitor._admitted_demand(
        {
            "equity:NASDAQ:AAA",
            "equity:NASDAQ:BBB",
            "equity:NASDAQ:CCC",
        }
    )

    assert admitted == {"equity:NASDAQ:BBB", "equity:NASDAQ:CCC"}
    assert monitor.budget_denied_instrument_count == 1


@pytest.mark.anyio
async def test_ibkr_monitor_reconciliation_runs_off_the_event_loop(monkeypatch, tmp_path):
    event_loop_thread_id = threading.get_ident()
    reconciliation_thread_ids: list[int] = []

    class FakeRuntime:
        enabled = True

        def diagnostics(self):
            reconciliation_thread_ids.append(threading.get_ident())
            return {
                "connected": False,
                "reconnect_count": 0,
                "active_quote_subscriptions": 0,
            }

    class FakeProvider:
        runtime = FakeRuntime()

    class FakeRegistry:
        def provider(self, provider_id):
            assert provider_id == "ibkr"
            return FakeProvider()

    class FakeMarketService:
        registry = FakeRegistry()

    monkeypatch.setattr(monitor_module, "IbkrEquityProvider", FakeProvider)
    monitor, _, _ = _monitor(tmp_path)
    monitor.strategy_repository_factory = object
    monitor.market_service_factory = FakeMarketService
    monkeypatch.setattr(
        monitor,
        "_active_demand",
        lambda _repository, *, now: {INSTRUMENT},
    )
    monkeypatch.setattr(
        monitor,
        "_ensure_subscription",
        lambda _service, _provider, _instrument: reconciliation_thread_ids.append(
            threading.get_ident()
        ),
    )

    result = await monitor.run_once()

    assert result == 0
    assert reconciliation_thread_ids
    assert all(thread_id != event_loop_thread_id for thread_id in reconciliation_thread_ids)


@pytest.mark.anyio
async def test_ibkr_monitor_holds_the_gateway_connection_without_strategy_demand(monkeypatch, tmp_path):
    class FakeRuntime:
        enabled = True

        def __init__(self, fail: bool) -> None:
            self.fail = fail
            self.connected = False
            self.connect_calls = 0

        def is_connected(self):
            return self.connected

        def connect(self):
            self.connect_calls += 1
            if self.fail:
                raise RuntimeError("ibkr_gateway_handshake_timeout")
            self.connected = True

        def diagnostics(self):
            return {"connected": self.connected, "reconnect_count": 0, "active_quote_subscriptions": 0}

    class FakeProvider:
        def __init__(self, runtime) -> None:
            self.runtime = runtime

    monkeypatch.setattr(monitor_module, "IbkrEquityProvider", FakeProvider)

    async def run(runtime):
        class FakeRegistry:
            def provider(self, provider_id):
                return FakeProvider(runtime)

        class FakeMarketService:
            registry = FakeRegistry()

        monitor, _, _ = _monitor(tmp_path)
        monitor.strategy_repository_factory = object
        monitor.market_service_factory = FakeMarketService
        monkeypatch.setattr(monitor, "_active_demand", lambda _repository, *, now: set())
        await monitor.run_once()
        return monitor

    # Charts learn that the Gateway is running from this connection.
    running = FakeRuntime(fail=False)
    await run(running)
    assert (running.connect_calls, running.connected) == (1, True)
    await run(running)
    assert running.connect_calls == 1

    # A Gateway that is not running is retried on the next pass, not raised.
    stopped = FakeRuntime(fail=True)
    monitor = await run(stopped)
    assert stopped.connect_calls == 1
    assert monitor.last_error == "RuntimeError: ibkr_gateway_handshake_timeout"


def test_held_stocks_get_lines_before_existing_and_new_demand(tmp_path):
    monitor, _, _ = _monitor(tmp_path)
    monitor.market_data_line_budget = 2
    monitor._keys = {"equity:NASDAQ:AAA": "key-aaa", "equity:NASDAQ:BBB": "key-bbb"}

    admitted = monitor._admitted_demand(
        {"equity:NASDAQ:AAA", "equity:NASDAQ:BBB", "equity:NASDAQ:TTEC"},
        priority={"equity:NASDAQ:TTEC"},
    )

    assert admitted == {"equity:NASDAQ:TTEC", "equity:NASDAQ:AAA"}
    assert monitor.held_without_line_count == 0


def test_held_stocks_beyond_the_budget_are_reported(monkeypatch, tmp_path):
    monitor, _, _ = _monitor(tmp_path)
    monitor.market_data_line_budget = 1
    logged = []
    monkeypatch.setattr(monitor_module, "trade_log", lambda *args, **kwargs: logged.append(kwargs))

    admitted = monitor._admitted_demand({"equity:US:A", "equity:US:B"}, priority={"equity:US:A", "equity:US:B"})

    assert admitted == {"equity:US:A"}
    assert monitor.held_without_line_count == 1
    assert logged[0]["denied"] == ["equity:US:B"]


def test_a_universe_that_cannot_be_resolved_is_reported_not_silently_dropped(monkeypatch, tmp_path):
    from types import SimpleNamespace

    monitor, _, _ = _monitor(tmp_path)
    logged = []
    monkeypatch.setattr(monitor_module, "trade_log", lambda *args, **kwargs: logged.append(kwargs))

    def broken(*_args, **_kwargs):
        raise RuntimeError("union failed")

    monkeypatch.setattr(monitor_module, "resolve_v2_runtime_archive", broken)
    config = SimpleNamespace(strategy_id="interday", active_universe_id=None, strategy_kind="gap_pullback_v1")
    repository = SimpleNamespace(list_configs=lambda active_only=False: [config])

    assert monitor._active_demand(repository, now=NOW) == set()
    assert monitor.demand_error_count == 1
    assert logged[0]["strategy_id"] == "interday" and "union failed" in logged[0]["detail"]


def test_line_checks_vouch_only_for_an_unbroken_live_line(monkeypatch, tmp_path):
    """Each healthy cycle confirms the line; a reconnect or a broken line starts a new span."""
    from datetime import timedelta

    clock = {"now": NOW}
    state = {"connected": True, "connect_count": 1, "reconnect_count": 0, "breaks": 0, "farm": "OK"}

    class FakeRuntime:
        enabled = True

        def is_connected(self):
            return state["connected"]

        def diagnostics(self):
            return {
                "connected": state["connected"],
                "connect_count": state["connect_count"],
                "reconnect_count": state["reconnect_count"],
                "active_quote_subscriptions": 1,
                "transport": {
                    "farm_status": {"market_data": state["farm"]},
                    "quote_line_break_count": state["breaks"],
                },
            }

    class FakeProvider:
        runtime = FakeRuntime()

    class FakeRegistry:
        def provider(self, provider_id):
            return FakeProvider()

    class FakeMarketService:
        registry = FakeRegistry()

    monkeypatch.setattr(monitor_module, "IbkrEquityProvider", FakeProvider)
    plane = ExecutionObservationPlane()
    monitor = TradingIbkrMarketDataMonitor(
        plane=plane,
        evidence_store=IbkrEvidenceStore(MemoryIbkrSessionEvidence()),
        now_factory=lambda: clock["now"],
    )
    monitor.strategy_repository_factory = object
    monitor.market_service_factory = FakeMarketService
    monkeypatch.setattr(monitor, "_active_demand", lambda _repository, *, now: {INSTRUMENT})
    ensure_ok = {"value": True}
    monkeypatch.setattr(
        monitor,
        "_ensure_subscription",
        lambda _service, _provider, _instrument: "ibkr:socket:" + INSTRUMENT if ensure_ok["value"] else None,
    )
    monitor._record_quote(
        StreamingQuoteUpdate(
            binding_id="ibkr:socket:" + INSTRUMENT,
            instrument_id=INSTRUMENT,
            provider="ibkr",
            source_time=NOW,
            received_at=NOW,
            bid=Decimal("100.00"),
            ask=Decimal("100.02"),
            last=Decimal("100.01"),
            market_data_type="LIVE",
            live_entitled=True,
        )
    )

    def cycle(seconds):
        clock["now"] = NOW + timedelta(seconds=seconds)
        monitor._run_once_blocking()
        return plane.line_confirmations(INSTRUMENT)[-1].up_since if plane.line_confirmations(INSTRUMENT) else None

    assert cycle(0) == NOW
    assert cycle(5) == NOW  # unbroken: the span carries on
    count = len(plane.line_confirmations(INSTRUMENT))

    state["breaks"] = 1  # e.g. a 2103 farm drop or a line error since the last check
    assert cycle(10) == NOW + timedelta(seconds=10)

    state["reconnect_count"] = 1
    state["connect_count"] = 2
    assert cycle(15) == NOW + timedelta(seconds=15)

    state["farm"] = "DISCONNECTED"
    cycle(20)
    state["farm"] = "OK"
    ensure_ok["value"] = False
    cycle(25)
    assert len(plane.line_confirmations(INSTRUMENT)) == count + 2  # neither cycle vouched

    ensure_ok["value"] = True
    assert cycle(30) == NOW + timedelta(seconds=30)
    assert monitor.diagnostics()["line_confirmation_count"] == count + 3
