"""Runtime monitor for the AI-only SOL/USDT one-minute shadow strategy."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime, timezone

from fastapi import APIRouter, FastAPI, HTTPException, Request

from .service import TradingMarketDataService, default_market_data_service
from .strategy_solana_ai import (
    SOLANA_AI_STRATEGY_ID,
    SOLANA_BINDING_ID,
    SOLANA_INSTRUMENT_ID,
    SolanaAIDecision,
    SolanaAIAnalyzer,
)
from .trade_logging import trade_log


_STATE_KEY = "_omnix_trading_solana_ai_monitor"


def _flag(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def solana_ai_monitor_enabled() -> bool:
    if os.environ.get("OMNIX_PERSISTENCE_MODE", "").strip() == "legacy_test":
        return _flag("OMNIX_TRADING_SOLANA_AI_MONITOR_IN_TESTS", "0")
    return _flag("OMNIX_TRADING_SOLANA_AI_MONITOR", "1")


def _interval_seconds() -> float:
    try:
        value = float(os.environ.get("OMNIX_TRADING_SOLANA_AI_POLL_SECONDS", "5"))
    except ValueError:
        value = 5.0
    return max(2.0, min(value, 60.0))


class TradingSolanaAIMonitor:
    """Poll completed 1m candles and ask the AI for one shadow decision.

    The monitor intentionally does not accept a paper repository or execution
    adapter. Signal events are audit-only observations; no order can be created
    by this strategy.
    """

    def __init__(
        self,
        *,
        market_service_factory: Callable[[], TradingMarketDataService] = default_market_data_service,
        analyzer_factory: Callable[[], SolanaAIAnalyzer] = SolanaAIAnalyzer,
        now_factory: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        interval_seconds: float | None = None,
    ) -> None:
        self.market_service_factory = market_service_factory
        self.analyzer_factory = analyzer_factory
        self.now_factory = now_factory
        self.interval_seconds = interval_seconds or _interval_seconds()
        self._task: asyncio.Task[None] | None = None
        self._last_processed_bar_end: datetime | None = None
        self.last_run_at: datetime | None = None
        self.last_bar_end: datetime | None = None
        self.last_error: str | None = None
        self.last_decision: SolanaAIDecision | None = None
        self.last_action: str | None = None
        self.last_provider: str | None = None
        self.last_model: str | None = None
        self.bar_fetch_count = 0
        self.completed_bar_count = 0
        self.ai_call_count = 0
        self.decision_count = 0
        self.signal_count = 0
        self.error_count = 0

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

    async def stop(self, *, reason: str = "gateway_shutdown") -> None:
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            trade_log(
                "auto_trading",
                "solana_ai_monitor_stopped",
                strategy_id=SOLANA_AI_STRATEGY_ID,
                instrument_id=SOLANA_INSTRUMENT_ID,
                binding_id=SOLANA_BINDING_ID,
                chart_interval="1m",
                reason=reason,
                paper_only=True,
                research_only=True,
                execution_authority=False,
            )

    async def run_once(self) -> int:
        now = self.now_factory()
        if now.tzinfo is None:
            raise ValueError("solana_ai_monitor_clock_must_be_timezone_aware")
        now = now.astimezone(timezone.utc)
        self.last_run_at = now
        market_service = self.market_service_factory()
        response = await asyncio.to_thread(
            market_service.bars,
            SOLANA_INSTRUMENT_ID,
            "1m",
            120,
            SOLANA_BINDING_ID,
        )
        self.bar_fetch_count += 1
        bars = sorted(
            [
                bar
                for bar in getattr(response, "bars", ())
                if bar.is_final and bar.end_time <= now
            ],
            key=lambda bar: bar.end_time,
        )
        if not bars:
            self.last_error = "solana_ai_no_completed_1m_candle"
            self.error_count += 1
            trade_log(
                "auto_trading",
                "solana_ai_data_unavailable",
                strategy_id=SOLANA_AI_STRATEGY_ID,
                instrument_id=SOLANA_INSTRUMENT_ID,
                reason="no_completed_1m_candle",
                observed_at=now,
                paper_only=True,
                execution_authority=False,
            )
            return 0

        latest = bars[-1]
        self.last_bar_end = latest.end_time
        self.completed_bar_count = len(bars)
        if self._last_processed_bar_end == latest.end_time:
            self.last_error = None
            return 0

        quote: dict[str, object] | None = None
        try:
            raw_quote = await asyncio.to_thread(
                market_service.quote,
                SOLANA_INSTRUMENT_ID,
                SOLANA_BINDING_ID,
            )
            if isinstance(raw_quote, dict):
                quote = raw_quote
        except Exception as exc:
            trade_log(
                "auto_trading",
                "solana_ai_quote_unavailable",
                strategy_id=SOLANA_AI_STRATEGY_ID,
                instrument_id=SOLANA_INSTRUMENT_ID,
                error_type=type(exc).__name__,
                detail=str(exc),
                observed_at=now,
                paper_only=True,
                execution_authority=False,
            )

        trade_log(
            "auto_trading",
            "solana_ai_candle_ready",
            strategy_id=SOLANA_AI_STRATEGY_ID,
            instrument_id=SOLANA_INSTRUMENT_ID,
            binding_id=SOLANA_BINDING_ID,
            chart_interval="1m",
            candle_end=latest.end_time,
            candle_close=latest.close,
            completed_candle_count=len(bars),
            quote_available=quote is not None,
            paper_only=True,
            research_only=True,
            execution_authority=False,
        )

        previous = self.last_decision
        self.ai_call_count += 1
        try:
            result = await asyncio.to_thread(
                self.analyzer_factory().assess,
                bars=bars,
                observed_at=latest.end_time,
                quote=quote,
                previous_decision=previous,
            )
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            self.error_count += 1
            trade_log(
                "auto_trading",
                "solana_ai_decision_error",
                strategy_id=SOLANA_AI_STRATEGY_ID,
                instrument_id=SOLANA_INSTRUMENT_ID,
                candle_end=latest.end_time,
                error_type=type(exc).__name__,
                detail=str(exc),
                paper_only=True,
                research_only=True,
                execution_authority=False,
            )
            return 0

        decision = result.decision
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
            "strategy_id": SOLANA_AI_STRATEGY_ID,
            "strategy_version": "solana-ai-1m-v1",
            "instrument_id": SOLANA_INSTRUMENT_ID,
            "binding_id": SOLANA_BINDING_ID,
            "chart_interval": "1m",
            "candle_end": latest.end_time,
            "decision": decision.model_dump(mode="json"),
            "provider": result.provider,
            "model": result.model,
            "input_characters": result.input_characters,
            "output_characters": result.output_characters,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "total_tokens": result.total_tokens,
            "usage_source": result.usage_source,
            "paper_only": True,
            "research_only": True,
            "order_created": False,
            "execution_authority": False,
        }
        trade_log("auto_trading", "solana_ai_decision", **payload)
        if decision.action in {"enter_long", "exit_long"}:
            trade_log(
                "auto_trading",
                "solana_ai_signal_observed",
                **payload,
                signal_action=decision.action,
            )
        return 1

    async def _loop(self) -> None:
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                self.error_count += 1
                trade_log(
                    "auto_trading",
                    "solana_ai_monitor_error",
                    strategy_id=SOLANA_AI_STRATEGY_ID,
                    instrument_id=SOLANA_INSTRUMENT_ID,
                    error_type=type(exc).__name__,
                    detail=str(exc),
                    paper_only=True,
                    execution_authority=False,
                )
            await asyncio.sleep(self.interval_seconds)


def register_trading_solana_ai_monitor(gateway: FastAPI) -> TradingSolanaAIMonitor:
    existing = getattr(gateway.state, _STATE_KEY, None)
    if isinstance(existing, TradingSolanaAIMonitor):
        return existing
    monitor = TradingSolanaAIMonitor()
    setattr(gateway.state, _STATE_KEY, monitor)

    async def startup() -> None:
        if solana_ai_monitor_enabled():
            monitor.start()

    async def shutdown() -> None:
        await monitor.stop()

    gateway.router.add_event_handler("startup", startup)
    gateway.router.add_event_handler("shutdown", shutdown)
    return monitor


def create_trading_solana_ai_control_router() -> APIRouter:
    """Create local runtime controls for the AI-only shadow monitor."""

    router = APIRouter(
        prefix="/api/trading/solana-ai",
        tags=["trading-solana-ai"],
    )

    def monitor_for(request: Request) -> TradingSolanaAIMonitor:
        monitor = getattr(request.app.state, _STATE_KEY, None)
        if not isinstance(monitor, TradingSolanaAIMonitor):
            raise HTTPException(
                status_code=503,
                detail="solana_ai_monitor_not_registered",
            )
        return monitor

    @router.post("/stop", status_code=202)
    async def stop_solana_ai_monitor(request: Request) -> dict[str, object]:
        monitor = monitor_for(request)
        await monitor.stop(reason="operator_request")
        return {
            "status": "stopped",
            "strategy_id": SOLANA_AI_STRATEGY_ID,
            "running": False,
            "configured_enabled": solana_ai_monitor_enabled(),
            "execution_authority": False,
        }

    @router.post("/start", status_code=202)
    async def start_solana_ai_monitor(request: Request) -> dict[str, object]:
        monitor = monitor_for(request)
        monitor.start()
        return {
            "status": "started",
            "strategy_id": SOLANA_AI_STRATEGY_ID,
            "running": True,
            "configured_enabled": solana_ai_monitor_enabled(),
            "execution_authority": False,
        }

    return router


__all__ = [
    "TradingSolanaAIMonitor",
    "create_trading_solana_ai_control_router",
    "register_trading_solana_ai_monitor",
    "solana_ai_monitor_enabled",
]
