from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(relative: str, old: str, new: str) -> None:
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{relative}: expected one replacement target, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def write_file(relative: str, content: str) -> None:
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


write_file(
    "src/app/persistence/migrations/0060_trading_solana_ai_strategy.sql",
    r'''
CREATE TABLE IF NOT EXISTS omnix_trading_solana_ai_strategies (
    workspace_id TEXT NOT NULL REFERENCES omnix_workspaces(id) ON DELETE CASCADE,
    strategy_id TEXT NOT NULL,
    strategy_kind TEXT NOT NULL,
    strategy_version TEXT NOT NULL,
    display_name TEXT NOT NULL,
    instrument_id TEXT NOT NULL,
    binding_id TEXT NOT NULL,
    chart_interval TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode = 'shadow'),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (workspace_id, strategy_id)
);

CREATE TABLE IF NOT EXISTS omnix_trading_solana_ai_decisions (
    workspace_id TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    instrument_id TEXT NOT NULL,
    state TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    idempotency_key TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (workspace_id, strategy_id, event_id),
    UNIQUE (workspace_id, strategy_id, idempotency_key),
    FOREIGN KEY (workspace_id, strategy_id)
        REFERENCES omnix_trading_solana_ai_strategies(workspace_id, strategy_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_omnix_trading_solana_ai_decisions_recent
    ON omnix_trading_solana_ai_decisions (workspace_id, strategy_id, observed_at DESC, created_at DESC);
''',
)

write_file(
    "src/app/trading/strategy_solana_ai_repository.py",
    r'''
from __future__ import annotations

import json

from app.persistence.tenant import TenantContext, local_tenant_context
from app.persistence.unit_of_work import unit_of_work

from .strategy_repository import StrategyEvent
from .strategy_solana_ai import (
    SOLANA_AI_STRATEGY_ID,
    SOLANA_BINDING_ID,
    SOLANA_INSTRUMENT_ID,
)


SOLANA_AI_STRATEGY_VERSION = "solana-ai-1m-v1"
SOLANA_AI_STRATEGY_KIND = "solana_ai_1m_shadow"
SOLANA_AI_DISPLAY_NAME = "Solana AI 1m Shadow"


class SolanaAIStrategyRepository:
    """Durable configuration identity and decision history for the SOL AI shadow strategy.

    This repository is intentionally separate from the gap-pullback strategy tables:
    those tables validate a GapPullbackConfig and require a paper-account parent,
    neither of which belongs to this research-only crypto strategy.
    """

    def __init__(
        self,
        *,
        context: TenantContext | None = None,
        uow_factory=unit_of_work,
    ) -> None:
        self.context = context or local_tenant_context()
        self.uow_factory = uow_factory

    def _upsert_strategy(self, connection, *, enabled: bool) -> None:
        connection.execute(
            """
            INSERT INTO omnix_trading_solana_ai_strategies (
                workspace_id, strategy_id, strategy_kind, strategy_version,
                display_name, instrument_id, binding_id, chart_interval, mode, enabled
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'shadow', %s)
            ON CONFLICT (workspace_id, strategy_id) DO UPDATE
               SET strategy_kind = EXCLUDED.strategy_kind,
                   strategy_version = EXCLUDED.strategy_version,
                   display_name = EXCLUDED.display_name,
                   instrument_id = EXCLUDED.instrument_id,
                   binding_id = EXCLUDED.binding_id,
                   chart_interval = EXCLUDED.chart_interval,
                   mode = EXCLUDED.mode,
                   enabled = EXCLUDED.enabled,
                   updated_at = CURRENT_TIMESTAMP
            """,
            (
                self.context.workspace_id,
                SOLANA_AI_STRATEGY_ID,
                SOLANA_AI_STRATEGY_KIND,
                SOLANA_AI_STRATEGY_VERSION,
                SOLANA_AI_DISPLAY_NAME,
                SOLANA_INSTRUMENT_ID,
                SOLANA_BINDING_ID,
                "1m",
                bool(enabled),
            ),
        )

    def ensure_strategy(self, *, enabled: bool) -> None:
        with self.uow_factory() as uow:
            self._upsert_strategy(uow.connection, enabled=enabled)
            uow.commit()

    def append_decision(self, event: StrategyEvent, *, enabled: bool) -> bool:
        if event.strategy_id != SOLANA_AI_STRATEGY_ID:
            raise ValueError("solana_ai_strategy_id_mismatch")
        if event.event_type != "solana_ai_decision":
            raise ValueError("solana_ai_event_type_mismatch")
        with self.uow_factory() as uow:
            # The parent and event are committed atomically so a freshly deployed
            # strategy cannot race its own first decision against configuration setup.
            self._upsert_strategy(uow.connection, enabled=enabled)
            inserted = uow.connection.execute(
                """
                INSERT INTO omnix_trading_solana_ai_decisions (
                    workspace_id, strategy_id, event_id, instrument_id, state,
                    observed_at, idempotency_key, payload
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (workspace_id, strategy_id, idempotency_key) DO NOTHING
                RETURNING event_id
                """,
                (
                    self.context.workspace_id,
                    event.strategy_id,
                    event.event_id,
                    event.instrument_id,
                    event.state,
                    event.observed_at,
                    event.idempotency_key,
                    json.dumps(event.payload, default=str),
                ),
            ).fetchone()
            uow.commit()
        return inserted is not None

    def recent_decisions(self, *, limit: int = 50) -> list[StrategyEvent]:
        normalized_limit = max(1, min(int(limit), 200))
        with self.uow_factory() as uow:
            rows = uow.connection.execute(
                """
                SELECT event_id, instrument_id, state, observed_at, idempotency_key, payload
                  FROM omnix_trading_solana_ai_decisions
                 WHERE workspace_id = %s AND strategy_id = %s
                 ORDER BY observed_at DESC, created_at DESC, event_id DESC
                 LIMIT %s
                """,
                (self.context.workspace_id, SOLANA_AI_STRATEGY_ID, normalized_limit),
            ).fetchall()
        return [
            StrategyEvent(
                strategy_id=SOLANA_AI_STRATEGY_ID,
                event_id=str(row[0]),
                instrument_id=str(row[1]),
                event_type="solana_ai_decision",
                state=str(row[2]),
                reason_code=None,
                observed_at=row[3],
                idempotency_key=str(row[4]),
                payload=dict(row[5] or {}),
            )
            for row in rows
        ]

    def decision_counts(self) -> tuple[int, int]:
        with self.uow_factory() as uow:
            row = uow.connection.execute(
                """
                SELECT COUNT(*),
                       COUNT(*) FILTER (WHERE state IN ('enter_long', 'exit_long'))
                  FROM omnix_trading_solana_ai_decisions
                 WHERE workspace_id = %s AND strategy_id = %s
                """,
                (self.context.workspace_id, SOLANA_AI_STRATEGY_ID),
            ).fetchone()
        if row is None:
            return (0, 0)
        return (int(row[0] or 0), int(row[1] or 0))


def default_solana_ai_strategy_repository() -> SolanaAIStrategyRepository:
    return SolanaAIStrategyRepository()


__all__ = [
    "SOLANA_AI_DISPLAY_NAME",
    "SOLANA_AI_STRATEGY_KIND",
    "SOLANA_AI_STRATEGY_VERSION",
    "SolanaAIStrategyRepository",
    "default_solana_ai_strategy_repository",
]
''',
)

replace_once(
    "src/app/trading/strategy_solana_ai_monitor.py",
    '''from .strategy_repository import StrategyEvent, TradingStrategyRepository, default_strategy_repository
from .strategy_solana_ai import (
''',
    '''from .strategy_repository import StrategyEvent
from .strategy_solana_ai_repository import (
    SolanaAIStrategyRepository,
    default_solana_ai_strategy_repository,
)
from .strategy_solana_ai import (
''',
)

replace_once(
    "src/app/trading/strategy_solana_ai_monitor.py",
    '''def _default_strategy_repository_factory() -> TradingStrategyRepository | None:
    if os.environ.get("OMNIX_PERSISTENCE_MODE", "").strip() == "legacy_test":
        return None
    return default_strategy_repository()
''',
    '''def _default_strategy_repository_factory() -> SolanaAIStrategyRepository | None:
    if os.environ.get("OMNIX_PERSISTENCE_MODE", "").strip() == "legacy_test":
        return None
    return default_solana_ai_strategy_repository()
''',
)

replace_once(
    "src/app/trading/strategy_solana_ai_monitor.py",
    '''        strategy_repository_factory: Callable[[], TradingStrategyRepository | None] = _default_strategy_repository_factory,
''',
    '''        strategy_repository_factory: Callable[[], SolanaAIStrategyRepository | None] = _default_strategy_repository_factory,
''',
)

replace_once(
    "src/app/trading/strategy_solana_ai_monitor.py",
    '''    The monitor intentionally does not accept a paper repository or execution
    adapter. Signal events are audit-only observations; no order can be created
    by this strategy.
''',
    '''    The monitor intentionally does not accept a paper repository or execution
    adapter. Decisions are durably recorded for strategy history, but no order
    can be created by this strategy.
''',
)

replace_once(
    "src/app/trading/strategy_solana_ai_monitor.py",
    '''    def strategy_record(self) -> SolanaAIStrategyRecord:
        task = self._task
        return SolanaAIStrategyRecord(
            configured_enabled=solana_ai_monitor_enabled(),
            running=bool(task is not None and not task.done()),
            last_run_at=self.last_run_at,
            last_error=self.last_error,
            decision_count=self.decision_count,
            signal_count=self.signal_count,
        )

    def recent_decisions(self, limit: int = 50) -> list[StrategyEvent]:
        normalized_limit = max(1, min(int(limit), 200))
        repository = self.strategy_repository_factory()
        if repository is not None:
            try:
                return [
                    event
                    for event in repository.recent_events(SOLANA_AI_STRATEGY_ID, limit=normalized_limit)
                    if event.event_type == "solana_ai_decision"
                ][:normalized_limit]
            except Exception:
                # Runtime state remains inspectable during a persistence outage;
                # new decisions still fail closed on the write path below.
                pass
        return list(reversed(self._decision_events[-normalized_limit:]))
''',
    '''    def strategy_record(self) -> SolanaAIStrategyRecord:
        task = self._task
        decision_count = self.decision_count
        signal_count = self.signal_count
        repository = self.strategy_repository_factory()
        if repository is not None:
            try:
                durable_decisions, durable_signals = repository.decision_counts()
                decision_count = max(decision_count, durable_decisions)
                signal_count = max(signal_count, durable_signals)
            except Exception:
                # Status must remain inspectable during a read-side outage. The
                # write path still fails closed and leaves the candle retryable.
                pass
        return SolanaAIStrategyRecord(
            configured_enabled=solana_ai_monitor_enabled(),
            running=bool(task is not None and not task.done()),
            last_run_at=self.last_run_at,
            last_error=self.last_error,
            decision_count=decision_count,
            signal_count=signal_count,
        )

    def recent_decisions(self, limit: int = 50) -> list[StrategyEvent]:
        normalized_limit = max(1, min(int(limit), 200))
        repository = self.strategy_repository_factory()
        if repository is not None:
            try:
                return repository.recent_decisions(limit=normalized_limit)
            except Exception:
                # Runtime state remains inspectable during a read-side outage;
                # new decisions still fail closed on the write path below.
                pass
        return list(reversed(self._decision_events[-normalized_limit:]))
''',
)

replace_once(
    "src/app/trading/strategy_solana_ai_monitor.py",
    '''    def _persist_decision(self, event: StrategyEvent) -> bool:
        repository = self.strategy_repository_factory()
        if repository is None:
            self._decision_events.append(event)
            return False
        persisted = repository.append_event(event)
        self._decision_events.append(event)
        return persisted

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())
            trade_log(
                "auto_trading",
                "solana_ai_monitor_started",
                strategy_id=SOLANA_AI_STRATEGY_ID,
                instrument_id=SOLANA_INSTRUMENT_ID,
                binding_id=SOLANA_BINDING_ID,
                chart_interval="1m",
                poll_interval_seconds=self.interval_seconds,
                paper_only=True,
                research_only=True,
                execution_authority=False,
            )
''',
    '''    def _persist_decision(self, event: StrategyEvent) -> bool:
        repository = self.strategy_repository_factory()
        if repository is None:
            self._decision_events.append(event)
            return False
        persisted = repository.append_decision(
            event,
            enabled=solana_ai_monitor_enabled(),
        )
        self._decision_events.append(event)
        return persisted

    def start(self) -> bool:
        if self._task is not None and not self._task.done():
            return True
        repository = self.strategy_repository_factory()
        if repository is not None:
            try:
                repository.ensure_strategy(enabled=solana_ai_monitor_enabled())
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                self.error_count += 1
                trade_log(
                    "auto_trading",
                    "solana_ai_strategy_persistence_error",
                    strategy_id=SOLANA_AI_STRATEGY_ID,
                    instrument_id=SOLANA_INSTRUMENT_ID,
                    error_type=type(exc).__name__,
                    detail=str(exc),
                    paper_only=True,
                    research_only=True,
                    execution_authority=False,
                )
                return False
        self._task = asyncio.create_task(self._loop())
        self.last_error = None
        trade_log(
            "auto_trading",
            "solana_ai_monitor_started",
            strategy_id=SOLANA_AI_STRATEGY_ID,
            instrument_id=SOLANA_INSTRUMENT_ID,
            binding_id=SOLANA_BINDING_ID,
            chart_interval="1m",
            poll_interval_seconds=self.interval_seconds,
            paper_only=True,
            research_only=True,
            execution_authority=False,
        )
        return True
''',
)

replace_once(
    "src/app/trading/strategy_solana_ai_monitor.py",
    '''        decision = result.decision
        self.last_decision = decision
        self._last_processed_bar_end = latest.end_time
        self.last_error = None
        self.last_provider = result.provider
        self.last_model = result.model
        self.last_action = decision.action
        self.decision_count += 1
        if decision.action in {"enter_long", "exit_long"}:
            self.signal_count += 1

        payload = {
''',
    '''        decision = result.decision
        payload = {
''',
)

replace_once(
    "src/app/trading/strategy_solana_ai_monitor.py",
    '''        self.last_decision = decision
        self._last_processed_bar_end = latest.end_time
        trade_log("auto_trading", "solana_ai_decision", **payload, decision_persisted=persisted)
''',
    '''        # A candle becomes processed only after its decision is durable. If
        # persistence failed above, the next loop retries this same completed bar.
        self.last_decision = decision
        self._last_processed_bar_end = latest.end_time
        self.last_error = None
        self.last_provider = result.provider
        self.last_model = result.model
        self.last_action = decision.action
        self.decision_count += 1
        if decision.action in {"enter_long", "exit_long"}:
            self.signal_count += 1
        trade_log("auto_trading", "solana_ai_decision", **payload, decision_persisted=persisted)
''',
)

replace_once(
    "src/app/trading/strategy_solana_ai_monitor.py",
    '''        monitor.start()
        return SolanaAIMonitorControlResponse(
            status="started",
            running=True,
            configured_enabled=solana_ai_monitor_enabled(),
        )
''',
    '''        if not monitor.start():
            raise HTTPException(
                status_code=503,
                detail=monitor.last_error or "solana_ai_strategy_persistence_unavailable",
            )
        return SolanaAIMonitorControlResponse(
            status="started",
            running=True,
            configured_enabled=solana_ai_monitor_enabled(),
        )
''',
)

# Replace the first-pass in-memory fixture with the dedicated Solana repository
# contract and add retry/fail-closed coverage.
replace_once(
    "src/tests/trading/test_strategy_solana_ai.py",
    '''class FixtureStrategyRepository:
    def __init__(self) -> None:
        self.events = []

    def append_event(self, event):
        self.events.append(event)
        return True

    def recent_events(self, strategy_id: str, limit: int = 200):
        assert strategy_id == "solana-ai-1m-shadow"
        return list(reversed(self.events[-limit:]))
''',
    '''class FixtureStrategyRepository:
    def __init__(self) -> None:
        self.events = []
        self.ensure_calls = 0

    def ensure_strategy(self, *, enabled: bool) -> None:
        assert isinstance(enabled, bool)
        self.ensure_calls += 1

    def append_decision(self, event, *, enabled: bool):
        assert isinstance(enabled, bool)
        self.events.append(event)
        return True

    def recent_decisions(self, *, limit: int = 200):
        return list(reversed(self.events[-limit:]))

    def decision_counts(self):
        signals = sum(event.state in {"enter_long", "exit_long"} for event in self.events)
        return (len(self.events), signals)
''',
)

write_file(
    "src/tests/trading/test_strategy_solana_ai_repository.py",
    r'''
from __future__ import annotations

from pathlib import Path

from app.trading.strategy_solana_ai_repository import (
    SOLANA_AI_STRATEGY_KIND,
    SOLANA_AI_STRATEGY_VERSION,
    SolanaAIStrategyRepository,
)


ROOT = Path(__file__).resolve().parents[2]


def test_solana_ai_has_dedicated_durable_strategy_and_decision_tables() -> None:
    migration = (
        ROOT / "app/persistence/migrations/0060_trading_solana_ai_strategy.sql"
    ).read_text(encoding="utf-8")
    repository = (
        ROOT / "app/trading/strategy_solana_ai_repository.py"
    ).read_text(encoding="utf-8")

    assert "omnix_trading_solana_ai_strategies" in migration
    assert "omnix_trading_solana_ai_decisions" in migration
    assert "REFERENCES omnix_trading_solana_ai_strategies" in migration
    assert "omnix_trading_strategy_events" not in repository
    assert SOLANA_AI_STRATEGY_KIND == "solana_ai_1m_shadow"
    assert SOLANA_AI_STRATEGY_VERSION == "solana-ai-1m-v1"
    assert SolanaAIStrategyRepository is not None
''',
)

# Add a regression that proves failed persistence leaves the candle retryable
# and does not advance any accepted-decision counters/state.
with (ROOT / "src/tests/trading/test_strategy_solana_ai.py").open("a", encoding="utf-8") as handle:
    handle.write(
        r'''


class FailOnceStrategyRepository(FixtureStrategyRepository):
    def __init__(self) -> None:
        super().__init__()
        self.failures_remaining = 1

    def append_decision(self, event, *, enabled: bool):
        if self.failures_remaining:
            self.failures_remaining -= 1
            raise RuntimeError("database unavailable")
        return super().append_decision(event, enabled=enabled)


def test_solana_ai_persistence_failure_keeps_completed_bar_retryable() -> None:
    market = FixtureMarket(_bars())
    analyzer = FixtureAnalyzer()
    repository = FailOnceStrategyRepository()
    monitor = TradingSolanaAIMonitor(
        market_service_factory=lambda: market,
        analyzer_factory=lambda: analyzer,
        strategy_repository_factory=lambda: repository,
        now_factory=lambda: START + timedelta(minutes=3, seconds=5),
        interval_seconds=2,
    )

    import asyncio

    assert asyncio.run(monitor.run_once()) == 0
    assert monitor.last_decision is None
    assert monitor.decision_count == 0
    assert monitor._last_processed_bar_end is None
    assert "database unavailable" in str(monitor.last_error)

    assert asyncio.run(monitor.run_once()) == 1
    assert monitor.last_decision is not None
    assert monitor.decision_count == 1
    assert monitor._last_processed_bar_end == START + timedelta(minutes=3)
    assert analyzer.calls == 2
    assert len(repository.events) == 1
'''
    )

print("Applied durable Solana strategy persistence hardening.")
