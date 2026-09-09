from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"expected patch anchor missing: {path}: {old[:120]!r}")
    if text.count(old) != 1:
        raise RuntimeError(f"patch anchor not unique: {path}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def append_once(path: str, marker: str, content: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if marker in text:
        return
    target.write_text(text.rstrip() + "\n\n" + content.strip() + "\n", encoding="utf-8")


# 1) Late startup-only Finviz archive recovery. Normal polling remains strict.
replace_once(
    "src/app/trading/strategy_universe_archiver.py",
    "from datetime import datetime, timedelta, timezone",
    "from datetime import datetime, time, timedelta, timezone",
)
replace_once(
    "src/app/trading/strategy_universe_archiver.py",
    '_ET = ZoneInfo("America/New_York")\n',
    '_ET = ZoneInfo("America/New_York")\n_REGULAR_CLOSE_ET = time(16, 0)\n',
)
replace_once(
    "src/app/trading/strategy_universe_archiver.py",
    "    catalyst_repository: TradingCatalystRepository | None = None,\n    catalyst_discovery: Callable[..., tuple] = discover_yahoo_catalyst_headlines,\n) -> GapperUniverseSnapshot | None:\n",
    "    catalyst_repository: TradingCatalystRepository | None = None,\n    catalyst_discovery: Callable[..., tuple] = discover_yahoo_catalyst_headlines,\n    allow_late_recovery: bool = False,\n) -> GapperUniverseSnapshot | None:\n",
)
replace_once(
    "src/app/trading/strategy_universe_archiver.py",
    '    """Create one configured point-in-time morning archive when due, otherwise return ``None``.\n\n    Archival is evidence-only: it never changes ``active_universe_id`` and cannot\n    authorize a trade. Source members and their dispositions are immutable so a\n    later provider failure cannot be mistaken for a legitimate source filter.\n    """\n',
    '    """Create one configured morning archive, with explicit startup recovery.\n\n    Normal polling is strictly limited to the configured scan/grace window. A\n    caller may opt into ``allow_late_recovery`` during application startup; only\n    Finviz archives may then be reconstructed later in the same regular session.\n    Their real evaluation timestamp is preserved, so integrity assessment marks\n    them non-preopen/non-prospective and they can never qualify AUTO PAPER.\n\n    Archival is evidence-only: it never changes ``active_universe_id`` and cannot\n    authorize a trade. Source members and their dispositions are immutable so a\n    later provider failure cannot be mistaken for a legitimate source filter.\n    """\n',
)
replace_once(
    "src/app/trading/strategy_universe_archiver.py",
    "    scan_end = scan_start + timedelta(minutes=config.config.universe_archive_grace_minutes)\n    if not scan_start <= now_et <= scan_end:\n        return None\n\n    universe_id = _archive_universe_id(config, now_et)\n",
    "    scan_end = scan_start + timedelta(minutes=config.config.universe_archive_grace_minutes)\n    if now_et < scan_start:\n        return None\n    late_recovery = now_et > scan_end\n    if late_recovery:\n        if (\n            not allow_late_recovery\n            or config.config.universe_discovery_source != \"finviz\"\n            or now_et.time() >= _REGULAR_CLOSE_ET\n        ):\n            return None\n\n    universe_id = _archive_universe_id(config, now_et)\n",
)
replace_once(
    "src/app/trading/strategy_universe_archiver.py",
    "        grace_minutes=config.config.universe_archive_grace_minutes,\n        execution_authority=False,\n",
    "        grace_minutes=config.config.universe_archive_grace_minutes,\n        late_recovery=late_recovery,\n        recovery_reason=(\n            \"startup_after_archive_window\" if late_recovery else None\n        ),\n        execution_authority=False,\n",
)

# 2) Run one reconciliation pass before the periodic archiver starts.
replace_once(
    "src/app/trading/strategy_universe_archive_monitor.py",
    "    async def run_once(self) -> int:\n",
    "    async def run_once(self, *, allow_late_recovery: bool = False) -> int:\n",
)
replace_once(
    "src/app/trading/strategy_universe_archive_monitor.py",
    "                    repository,\n                    now=now,\n                )\n",
    "                    repository,\n                    now=now,\n                    allow_late_recovery=allow_late_recovery,\n                )\n",
)
replace_once(
    "src/app/trading/strategy_universe_archive_monitor.py",
    "    async def startup() -> None:\n        if strategy_universe_archive_monitor_enabled():\n            monitor.start()\n",
    "    async def startup() -> None:\n        if not strategy_universe_archive_monitor_enabled():\n            return\n        try:\n            recovered = await monitor.run_once(allow_late_recovery=True)\n            trade_log(\n                \"auto_trading\",\n                \"daily_universe_archive_startup_reconciliation\",\n                observed_at=datetime.now(timezone.utc),\n                archive_count=recovered,\n                execution_authority=False,\n            )\n        except Exception as exc:\n            # Reconciliation is best-effort. A provider/database problem at boot\n            # must not prevent the normal periodic monitor from starting.\n            monitor.last_error = f\"startup_reconciliation: {type(exc).__name__}: {exc}\"\n            trade_log(\n                \"auto_trading\",\n                \"daily_universe_archive_startup_reconciliation_error\",\n                observed_at=datetime.now(timezone.utc),\n                error_type=type(exc).__name__,\n                detail=str(exc),\n                execution_authority=False,\n            )\n        monitor.start()\n",
)

# 3) Malformed Alpaca quote timestamps degrade to trade-only evidence. The book
# is discarded and freshness becomes fallback, so AUTO PAPER stays fail-closed.
replace_once(
    "src/app/trading/providers/alpaca_iex.py",
    "        quote_available = isinstance(latest_quote, dict)\n        quote_time = (\n            _parse_timestamp(latest_quote.get(\"t\"), field=\"quote\")\n            if quote_available\n            else None\n        )\n        trade_time = _parse_timestamp(latest_trade.get(\"t\"), field=\"trade\")\n        source_time = min(quote_time, trade_time) if quote_time is not None else trade_time\n",
    "        quote_available = isinstance(latest_quote, dict)\n        quote_timestamp_degraded = False\n        quote_time = None\n        if quote_available:\n            try:\n                quote_time = _parse_timestamp(latest_quote.get(\"t\"), field=\"quote\")\n            except ProviderContractError:\n                # A malformed quote timestamp makes the book non-causal. Keep a\n                # valid latest trade as research/SHADOW price evidence, but drop\n                # bid/ask entirely so execution eligibility remains fail-closed.\n                quote_available = False\n                quote_timestamp_degraded = True\n        trade_time = _parse_timestamp(latest_trade.get(\"t\"), field=\"trade\")\n        source_time = min(quote_time, trade_time) if quote_time is not None else trade_time\n",
)
replace_once(
    "src/app/trading/providers/alpaca_iex.py",
    '            "freshness_mode": "live",\n',
    '            "freshness_mode": "fallback" if quote_timestamp_degraded else "live",\n',
)

# 4) Regression coverage.
append_once(
    "src/tests/trading/test_trading_strategy_universe_archiver.py",
    "test_late_finviz_startup_recovery_is_research_only",
    r'''
def test_late_finviz_startup_recovery_is_research_only(monkeypatch) -> None:
    from app.trading.strategy_data_integrity import assess_universe_integrity

    repository = FakeRepository()
    calls = []

    def finviz(**kwargs):
        calls.append(kwargs)
        observed = kwargs["evaluation_time"]
        return freeze_gapper_universe(
            universe_id=kwargs["universe_id"],
            session_date=observed.astimezone(archiver._ET).date(),
            evaluation_time=observed,
            discovery_source="finviz",
            source_locator=FINVIZ_ATOMIC_SOURCE_LOCATOR,
            source_candidate_symbols=("TEST",),
            candidates=[],
            allow_empty=True,
        )

    monkeypatch.setattr(archiver, "discover_finviz_gappers", finviz)
    # 10:06 ET: the machine came back after the 09:20+10m archive window.
    now = datetime(2026, 9, 9, 14, 6, tzinfo=timezone.utc)
    value = strategy(discovery_source="finviz")

    assert archiver.archive_daily_universe_if_due(value, repository, now=now) is None
    recovered = archiver.archive_daily_universe_if_due(
        value,
        repository,
        now=now,
        allow_late_recovery=True,
    )

    assert recovered is not None
    assert len(calls) == 1
    integrity = assess_universe_integrity(recovered)
    assert integrity.capture_on_time is False
    assert integrity.prospective_eligible is False
    assert "FINVIZ_CAPTURE_NOT_PREOPEN" in integrity.reason_codes


def test_late_finviz_startup_recovery_stops_at_regular_close(monkeypatch) -> None:
    repository = FakeRepository()
    called = False

    def finviz(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("late recovery must not capture after regular close")

    monkeypatch.setattr(archiver, "discover_finviz_gappers", finviz)
    now = datetime(2026, 9, 9, 20, 1, tzinfo=timezone.utc)  # 16:01 ET

    assert archiver.archive_daily_universe_if_due(
        strategy(discovery_source="finviz"),
        repository,
        now=now,
        allow_late_recovery=True,
    ) is None
    assert called is False
''',
)

append_once(
    "src/tests/trading/test_trading_alpaca_iex_execution.py",
    "test_alpaca_iex_malformed_quote_timestamp_degrades_to_trade_only",
    r'''
def test_alpaca_iex_malformed_quote_timestamp_degrades_to_trade_only(monkeypatch) -> None:
    _credentials(monkeypatch)
    runtime = _FixtureRuntime(
        snapshot_payload={
            "latestQuote": {
                "t": "not-a-timestamp",
                "bp": 9.99,
                "ap": 10.01,
                "bs": 300,
                "as": 400,
            },
            "latestTrade": {
                "t": "2026-08-18T14:00:00.050000Z",
                "p": 10.00,
                "s": 100,
            },
            "minuteBar": {
                "t": "2026-08-18T14:00:00Z",
                "o": 9.98,
                "h": 10.04,
                "l": 9.97,
                "c": 10.00,
                "v": 2500,
            },
            "dailyBar": {"v": 1_250_000},
        }
    )

    value = _provider(runtime).execution_observation(
        "equity:NASDAQ:AAPL",
        policy=ExecutionEligibilityPolicy(max_age_seconds="300", max_spread_bps="100"),
    )

    assert value.last == Decimal("10.0")
    assert value.bid is None
    assert value.ask is None
    assert value.freshness_mode == "fallback"
    assert value.execution_eligible is False
    assert "BID_ASK_UNAVAILABLE" in value.rejection_reasons
    assert "NON_EXECUTION_FRESHNESS" in value.rejection_reasons
''',
)

monitor_test = Path("src/tests/trading/test_trading_strategy_universe_archive_monitor.py")
if not monitor_test.exists():
    monitor_test.write_text(
        r'''from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.trading import strategy_universe_archive_monitor as archive_monitor


class _Repository:
    def list_configs(self, *, active_only=False):
        assert active_only is False
        return [SimpleNamespace(strategy_id="restart-test")]


def test_startup_reconciliation_forwards_late_recovery(monkeypatch) -> None:
    seen = []
    monkeypatch.setattr(archive_monitor, "default_strategy_repository", lambda: _Repository())

    def archive(config, repository, *, now, allow_late_recovery=False):
        seen.append((config.strategy_id, allow_late_recovery))
        return None

    monkeypatch.setattr(archive_monitor, "archive_daily_universe_if_due", archive)
    monitor = archive_monitor.TradingStrategyUniverseArchiveMonitor(interval_seconds=60)

    assert asyncio.run(monitor.run_once(allow_late_recovery=True)) == 0
    assert seen == [("restart-test", True)]
''',
        encoding="utf-8",
    )

print("Applied Sep 9 trading restart recovery hardening")
