from __future__ import annotations

import asyncio
import hashlib
import os
from collections import defaultdict
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI

from .execution import ExecutionObservation
from .paper import PaperMarketObservation, PaperOrderRequest, paper_protection_trigger
from .paper_protection import PaperPositionProtection
from .paper_protection_repository import (
    TradingPaperProtectionRepository,
    default_paper_protection_repository,
)
from .paper_repository import TradingPaperRepository
from .paper_runtime_repository import default_runtime_paper_repository
from .service import TradingMarketDataService, default_market_data_service


_MONITOR_STATE_KEY = "_omnix_trading_paper_monitor"


def _env_flag(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def trading_paper_monitor_enabled() -> bool:
    if os.environ.get("OMNIX_PERSISTENCE_MODE", "").strip() == "legacy_test":
        return _env_flag("OMNIX_TRADING_PAPER_MONITOR_IN_TESTS", "0")
    return _env_flag("OMNIX_TRADING_PAPER_MONITOR", "1")


def _interval_seconds() -> float:
    """Idle account scan cadence; active execution uses a separate fast cadence."""
    try:
        value = float(os.environ.get("OMNIX_TRADING_PAPER_INTERVAL_SECONDS", "15"))
    except ValueError:
        value = 15.0
    return max(5.0, value)


def _active_interval_seconds() -> float:
    """Fallback polling cadence while any order/protection needs execution evidence."""
    try:
        value = float(os.environ.get("OMNIX_TRADING_PAPER_ACTIVE_INTERVAL_SECONDS", "1"))
    except ValueError:
        value = 1.0
    return max(0.25, min(5.0, value))


def _protection_key(protection: PaperPositionProtection, trigger: str) -> str:
    raw = (
        f"{protection.account_id}|{protection.instrument_id}|"
        f"{protection.revision}|{trigger}|paper-protection-v1"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _paper_observation(execution: ExecutionObservation) -> PaperMarketObservation:
    return PaperMarketObservation(
        instrument_id=execution.instrument_id,
        binding_id=execution.binding_id,
        provider=execution.provider,
        price=execution.last,
        bid=execution.bid,
        ask=execution.ask,
        bid_size=execution.bid_size,
        ask_size=execution.ask_size,
        high=execution.high,
        low=execution.low,
        volume=execution.bar_volume,
        bar_start_time=execution.bar_start_time,
        source_time=execution.source_time,
        evaluated_at=datetime.now(timezone.utc),
        execution_eligible=execution.execution_eligible,
        freshness_mode=execution.freshness_mode,
        provider_sequence=execution.provider_sequence,
        rejection_reasons=execution.rejection_reasons,
        halted=execution.halted is True,
    )


class TradingPaperMonitor:
    """Server-authoritative paper execution and OCO protection monitor.

    Idle accounts are scanned conservatively, but once an order or protection is
    active the execution dispatcher switches to a tight polling fallback. This
    intentionally does *not* accelerate strategy signal evaluation: only already
    authorized paper orders/protections consume the fast cadence.
    """

    def __init__(
        self,
        *,
        repository_factory: Callable[[], TradingPaperRepository] = default_runtime_paper_repository,
        protection_repository_factory: Callable[[], TradingPaperProtectionRepository] = default_paper_protection_repository,
        market_service_factory: Callable[[], TradingMarketDataService] = default_market_data_service,
        interval_seconds: float | None = None,
        active_interval_seconds: float | None = None,
    ) -> None:
        self.repository_factory = repository_factory
        self.protection_repository_factory = protection_repository_factory
        self.market_service_factory = market_service_factory
        self.interval_seconds = interval_seconds or _interval_seconds()
        self.active_interval_seconds = active_interval_seconds or _active_interval_seconds()
        self._task: asyncio.Task[None] | None = None
        self._wake_event: asyncio.Event | None = None
        self.last_error: str | None = None
        self.last_run_at: datetime | None = None
        self.last_execution_observation_at: datetime | None = None
        self.last_observation_age_ms: float | None = None
        self.max_observation_age_ms = 0.0
        self.quote_count = 0
        self.rejected_quote_count = 0
        self.fill_count = 0
        self.protection_trigger_count = 0
        self.active_target_count = 0
        self.active_order_count = 0
        self.active_protection_count = 0

    def start(self) -> None:
        if self._task is None:
            self._wake_event = asyncio.Event()
            self._task = asyncio.create_task(self._run_loop())

    def wake(self) -> None:
        """Wake the dispatcher early when server-side activity changes."""
        if self._wake_event is not None:
            self._wake_event.set()

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        self._wake_event = None

    async def _reconcile_protection(
        self,
        *,
        account_id: str,
        instrument_id: str,
        execution: ExecutionObservation,
        repository: TradingPaperRepository,
        protections: TradingPaperProtectionRepository,
    ) -> None:
        try:
            protection = await asyncio.to_thread(
                protections.get,
                account_id,
                instrument_id,
                include_inactive=False,
            )
        except ValueError:
            return

        snapshot = await asyncio.to_thread(repository.snapshot, account_id)
        history = {order.order_id: order for order in snapshot.order_history}
        position = next(
            (
                item
                for item in snapshot.positions
                if item.instrument_id == instrument_id and item.quantity != 0
            ),
            None,
        )

        if protection.status == "pending_entry":
            if position is not None:
                await asyncio.to_thread(
                    protections.transition,
                    account_id,
                    instrument_id,
                    status="active",
                    exit_order_id=None,
                    trigger_reason="entry_filled",
                    expected_revision=protection.revision,
                )
                return
            entry = history.get(protection.entry_order_id or "")
            if entry is not None and entry.status in {"rejected", "cancelled"}:
                await asyncio.to_thread(
                    protections.transition,
                    account_id,
                    instrument_id,
                    status="cancelled",
                    exit_order_id=None,
                    trigger_reason=f"entry_{entry.status}",
                    expected_revision=protection.revision,
                )
            return

        if protection.status == "exit_submitted":
            exit_order = history.get(protection.exit_order_id or "")
            if exit_order is not None and exit_order.status == "filled":
                await asyncio.to_thread(
                    protections.transition,
                    account_id,
                    instrument_id,
                    status="closed",
                    exit_order_id=exit_order.order_id,
                    trigger_reason=protection.trigger_reason or "exit_filled",
                    expected_revision=protection.revision,
                )
            elif exit_order is not None and exit_order.status in {"rejected", "cancelled"}:
                await asyncio.to_thread(
                    protections.transition,
                    account_id,
                    instrument_id,
                    status="active",
                    exit_order_id=None,
                    trigger_reason=f"exit_{exit_order.status}_retry",
                    expected_revision=protection.revision,
                )
            return

        if protection.status != "active":
            return
        if position is None:
            await asyncio.to_thread(
                protections.transition,
                account_id,
                instrument_id,
                status="closed",
                exit_order_id=None,
                trigger_reason="position_closed",
                expected_revision=protection.revision,
            )
            return

        is_long = position.quantity > 0
        close_side = "sell" if is_long else "buy"
        conflicting = any(
            order.instrument_id == instrument_id
            and order.status == "open"
            and order.side == close_side
            for order in snapshot.open_orders
        )
        if conflicting:
            return

        entry = history.get(protection.entry_order_id or "")
        activated_at = (
            entry.updated_at
            if entry is not None and entry.updated_at is not None
            else protection.updated_at or protection.created_at
        )
        trigger_kind = paper_protection_trigger(
            is_long=is_long,
            stop_price=protection.stop_loss,
            target_price=protection.take_profit,
            observation=_paper_observation(execution),
            activated_at=activated_at,
        )
        if trigger_kind is None:
            return
        trigger = "stop_loss" if trigger_kind == "stop" else "take_profit"

        key = _protection_key(protection, trigger)
        order_id = f"paper-protection-{key[:32]}"
        reference = (
            execution.bid if close_side == "sell" else execution.ask
        ) or execution.last
        try:
            await asyncio.to_thread(
                repository.place_order,
                account_id,
                PaperOrderRequest(
                    order_id=order_id,
                    instrument_id=instrument_id,
                    binding_id=protection.binding_id or execution.binding_id,
                    side=close_side,
                    order_type="market",
                    quantity=abs(position.quantity),
                    reference_price=reference,
                    idempotency_key=key,
                ),
            )
        except ValueError as exc:
            self.last_error = f"paper_protection_order: {exc}"
            return

        await asyncio.to_thread(
            protections.transition,
            account_id,
            instrument_id,
            status="exit_submitted",
            exit_order_id=order_id,
            trigger_reason=trigger,
            expected_revision=protection.revision,
        )
        self.protection_trigger_count += 1
        self.wake()

    async def run_once(self) -> int:
        repository = self.repository_factory()
        protections = self.protection_repository_factory()
        accounts = await asyncio.to_thread(repository.list_accounts, 100)
        targets: dict[tuple[str, str | None], set[str]] = defaultdict(set)
        active_orders = 0
        active_protections = 0
        for account in accounts:
            if not account.enabled:
                continue
            snapshot = await asyncio.to_thread(repository.snapshot, account.account_id)
            active_orders += len(snapshot.open_orders)
            for order in snapshot.open_orders:
                targets[(order.instrument_id, order.binding_id)].add(account.account_id)
            try:
                account_protections = await asyncio.to_thread(
                    protections.list,
                    account.account_id,
                    active_only=True,
                )
            except ValueError:
                account_protections = []
            active_protections += len(account_protections)
            for protection in account_protections:
                targets[(protection.instrument_id, protection.binding_id)].add(account.account_id)

        self.active_order_count = active_orders
        self.active_protection_count = active_protections
        self.active_target_count = len(targets)

        service = self.market_service_factory()
        filled = 0
        for (instrument_id, requested_binding), account_ids in sorted(
            targets.items(), key=lambda item: (item[0][0], item[0][1] or "")
        ):
            try:
                execution = await asyncio.to_thread(
                    service.execution_observation,
                    instrument_id,
                    requested_binding,
                )
                self.quote_count += 1
                now = datetime.now(timezone.utc)
                age_ms = max(
                    0.0,
                    (now - execution.source_time.astimezone(timezone.utc)).total_seconds() * 1000.0,
                )
                self.last_execution_observation_at = execution.source_time.astimezone(timezone.utc)
                self.last_observation_age_ms = age_ms
                self.max_observation_age_ms = max(self.max_observation_age_ms, age_ms)
                if not execution.execution_eligible:
                    self.rejected_quote_count += 1
                    self.last_error = (
                        "execution_data_rejected: " + ",".join(execution.rejection_reasons)
                    )
                    continue
                observation = _paper_observation(execution)
                for account_id in sorted(account_ids):
                    fills = await asyncio.to_thread(
                        repository.process_observation,
                        account_id,
                        observation,
                    )
                    filled += len(fills)
                    await self._reconcile_protection(
                        account_id=account_id,
                        instrument_id=instrument_id,
                        execution=execution,
                        repository=repository,
                        protections=protections,
                    )
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                continue
        self.fill_count += filled
        self.last_run_at = datetime.now(timezone.utc)
        return filled

    def diagnostics(self) -> dict[str, Any]:
        return {
            "enabled": trading_paper_monitor_enabled(),
            "running": self._task is not None,
            "idle_interval_seconds": self.interval_seconds,
            "active_interval_seconds": self.active_interval_seconds,
            "current_interval_seconds": (
                self.active_interval_seconds if self.active_target_count else self.interval_seconds
            ),
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_error": self.last_error,
            "last_execution_observation_at": (
                self.last_execution_observation_at.isoformat()
                if self.last_execution_observation_at
                else None
            ),
            "last_observation_age_ms": self.last_observation_age_ms,
            "max_observation_age_ms": self.max_observation_age_ms,
            "active_target_count": self.active_target_count,
            "active_order_count": self.active_order_count,
            "active_protection_count": self.active_protection_count,
            "quote_count": self.quote_count,
            "rejected_quote_count": self.rejected_quote_count,
            "fill_count": self.fill_count,
            "protection_trigger_count": self.protection_trigger_count,
            "fail_closed": True,
            "reference_price_fallback": False,
            "server_authoritative_protection": True,
            "adaptive_execution_cadence": True,
        }

    async def _sleep_until_next_cycle(self) -> None:
        delay = self.active_interval_seconds if self.active_target_count else self.interval_seconds
        event = self._wake_event
        if event is None:
            await asyncio.sleep(delay)
            return
        event.clear()
        try:
            await asyncio.wait_for(event.wait(), timeout=delay)
        except TimeoutError:
            pass

    async def _run_loop(self) -> None:
        while True:
            try:
                await self.run_once()
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
            await self._sleep_until_next_cycle()


def register_trading_paper_monitor(gateway: FastAPI) -> TradingPaperMonitor:
    existing = getattr(gateway.state, _MONITOR_STATE_KEY, None)
    if isinstance(existing, TradingPaperMonitor):
        return existing
    monitor = TradingPaperMonitor()
    setattr(gateway.state, _MONITOR_STATE_KEY, monitor)

    async def startup() -> None:
        if trading_paper_monitor_enabled():
            monitor.start()

    async def shutdown() -> None:
        await monitor.stop()

    gateway.router.add_event_handler("startup", startup)
    gateway.router.add_event_handler("shutdown", shutdown)
    return monitor
