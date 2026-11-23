"""Trading monitors are tasks on the shared scheduler (WP-8.3).

The scheduler owns the loop. A monitor inherits ``ScheduledTradingMonitor``
and exposes ``run_once`` and its cadence; it has no start, stop or loop of
its own. Each monitor module returns a ``TradingMonitorTask`` from its
``create_*_task`` factory, and ``scheduled_task_spec`` turns that into the
``ScheduledTaskSpec`` the trading feature registers.

An async monitor's cycle runs on the trading loop (``on_trading_loop``), not
on the gateway's: a cycle that blocks (a synchronous read, a provider call)
then delays only other trading work, never a live call or a chat stream.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import threading
import time
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from typing import Any, ClassVar

from app.config.env import environment
from app.persistence.runtime import is_legacy_test_persistence
from app.runtime.scheduler import ScheduledTaskSpec, TaskContext

from .trade_logging import trade_log

# A trading cycle fetches bars and may call a model for dozens of candidates;
# at the open that legitimately takes longer than a minute.
TRADING_MONITOR_TIMEOUT_SECONDS = 300.0
# The trading loop watches its own lag: the gateway's watchdog no longer sees a cycle that blocks it.
_LAG_PROBE_SECONDS = 1.0
_LAG_WARN_SECONDS = 5.0

logger = logging.getLogger(__name__)


async def _watch_lag() -> None:
    while True:
        started = time.monotonic()
        await asyncio.sleep(_LAG_PROBE_SECONDS)
        late = time.monotonic() - started - _LAG_PROBE_SECONDS
        if late >= _LAG_WARN_SECONDS:
            # Every trading job queued behind it waited this long, and it counts against their timeouts.
            logger.warning("[trading] the trading loop stalled %.1f s: a cycle blocked it", late)


class _TradingLoop:
    """The trading monitors' own event loop, on its own thread, started on first use."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    def loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is None or self._thread is None or not self._thread.is_alive():
                loop = asyncio.new_event_loop()
                thread = threading.Thread(target=loop.run_forever, name="omnix-trading-loop", daemon=True)
                thread.start()
                loop.call_soon_threadsafe(lambda: loop.create_task(_watch_lag(), name="omnix-trading-loop-lag"))
                self._loop, self._thread = loop, thread
            return self._loop

    def close(self, timeout: float = 5.0) -> None:
        """Cancel what is left on the trading loop, shut its executor down and stop its thread; the next use starts a
        fresh one. Tests close it so work one leaves behind never runs into the next."""
        with self._lock:
            loop, thread = self._loop, self._thread
            self._loop = self._thread = None
        if loop is None or thread is None:
            return

        async def wind_down() -> None:
            current = asyncio.current_task()
            pending = [task for task in asyncio.all_tasks() if task is not current]
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            await loop.shutdown_default_executor()

        if thread.is_alive():
            try:
                asyncio.run_coroutine_threadsafe(wind_down(), loop).result(timeout)
            except Exception:  # noqa: BLE001 - a task that will not stop is left to the daemon thread
                logger.warning("[trading] the trading loop did not wind down in %.0f s", timeout)
            loop.call_soon_threadsafe(loop.stop)
            thread.join(timeout)
        if not thread.is_alive():
            loop.close()


_TRADING_LOOP = _TradingLoop()


def close_trading_loop() -> None:
    _TRADING_LOOP.close()


async def _call(work: Callable[[], Any]) -> Any:
    result = work()
    if inspect.isawaitable(result):
        result = await result
    return result


def _post(loop: asyncio.AbstractEventLoop, callback: Callable[..., Any], *args: Any) -> None:
    try:
        loop.call_soon_threadsafe(callback, *args)
    except RuntimeError:  # the caller's loop has closed: nobody waits for the result
        pass


async def on_trading_loop(work: Callable[[], Any]) -> Any:
    """Run ``work`` (a function, or one returning an awaitable) on the trading loop and return its result.

    The caller's context variables go with it (tenant, background owner, statement class). Cancelling the caller
    cancels the work and waits it out, as the scheduler does for its own tasks, so a timed-out cycle never overlaps
    the next one.
    """
    caller = asyncio.get_running_loop()
    loop = _TRADING_LOOP.loop()
    if loop is caller:
        return await _call(work)
    outcome: asyncio.Future[Any] = caller.create_future()
    started: list[asyncio.Task[Any]] = []

    def relay(task: asyncio.Task[Any]) -> None:
        if outcome.done():
            return
        if task.cancelled():
            outcome.cancel()
        elif (error := task.exception()) is not None:
            outcome.set_exception(error)
        else:
            outcome.set_result(task.result())

    def start() -> None:
        # Runs in a copy of the caller's context (call_soon_threadsafe copies it); the task copies it again.
        task = loop.create_task(_call(work))
        started.append(task)
        task.add_done_callback(lambda done: _post(caller, relay, done))

    def cancel() -> None:
        for task in started:
            task.cancel()

    loop.call_soon_threadsafe(start)
    try:
        return await asyncio.shield(outcome)
    except asyncio.CancelledError:
        loop.call_soon_threadsafe(cancel)
        # A second cancel (a shutdown while a timed-out cycle stops) must not abandon the work: the caller's
        # shutdown would then close the runner beside a cycle still running. ``wait`` never cancels ``outcome``.
        while not outcome.done():
            try:
                await asyncio.wait({outcome})
            except asyncio.CancelledError:
                continue
        if not outcome.cancelled():
            outcome.exception()  # retrieved: the cycle's own error is not the caller's to raise now
        raise


def _on_trading_loop_callback(callback: Callable[[], Any]) -> Callable[[], Awaitable[Any]]:
    return lambda: on_trading_loop(callback)


class ScheduledTradingMonitor:
    """Cadence, error reporting and diagnostics shared by every trading monitor."""

    interval_seconds: float = 60.0
    # Longest a single cycle may run before the scheduler cancels it; None
    # means TRADING_MONITOR_TIMEOUT_SECONDS (or the interval, when longer).
    timeout_seconds: float | None = None
    last_error: str | None = None
    # True once the scheduler runs this monitor in this process.
    scheduled: bool = False
    # The trade-log event a failed cycle records; None records only last_error.
    error_event: ClassVar[str | None] = None
    _wake_requested: bool = False
    _last_cycle_at: float | None = None

    def tick_seconds(self) -> float:
        """How often the scheduler checks whether a cycle is due."""
        return self.interval_seconds

    def current_interval_seconds(self) -> float:
        """The time between cycles now; monitors with an adaptive cadence override it."""
        return self.interval_seconds

    def wake(self) -> None:
        """Run the next cycle at the next tick instead of waiting for the interval."""
        self._wake_requested = True

    def run_timeout_seconds(self) -> float:
        if self.timeout_seconds is not None:
            return float(self.timeout_seconds)
        return max(TRADING_MONITOR_TIMEOUT_SECONDS, self.tick_seconds())

    def cycle_due(self, now: float) -> bool:
        if self._wake_requested or self._last_cycle_at is None:
            return True
        interval = self.current_interval_seconds()
        if self.tick_seconds() >= interval:
            return True
        return now - self._last_cycle_at >= interval

    def begin_cycle(self, now: float) -> None:
        self._wake_requested = False
        self._last_cycle_at = now

    def error_log_fields(self) -> dict[str, Any]:
        return {"execution_authority": False}

    def record_cycle_error(self, exc: Exception) -> None:
        self.last_error = f"{type(exc).__name__}: {exc}"
        if self.error_event is not None:
            trade_log(
                "auto_trading",
                self.error_event,
                error_type=type(exc).__name__,
                detail=str(exc),
                **self.error_log_fields(),
            )


class SingleFlightTasks:
    """Side work a monitor starts but its cycle never awaits: at most one running task per key."""

    def __init__(self, on_error: Callable[[BaseException], None]) -> None:
        self.on_error = on_error
        self._tasks: dict[str, asyncio.Task[Any]] = {}

    def start(self, key: str, work: Callable[[], Coroutine[Any, Any, Any]]) -> bool:
        running = self._tasks.get(key)
        if running is not None and not running.done():
            return False
        task = asyncio.create_task(work())
        self._tasks[key] = task
        task.add_done_callback(self._finished)
        return True

    def _finished(self, task: asyncio.Task[Any]) -> None:
        if not task.cancelled() and (error := task.exception()) is not None:
            self.on_error(error)

    async def close(self) -> None:
        running = [task for task in self._tasks.values() if not task.done()]
        for task in running:
            task.cancel()
        await asyncio.gather(*running, return_exceptions=True)
        self._tasks.clear()


def _switch_on(name: str, default: str) -> bool:
    return environment().get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def monitor_switch(name: str) -> Callable[[], bool]:
    """A monitor's on/off switch: ``name``, on unless set off.

    Under legacy test persistence (pytest) the monitor stays off unless ``<name>_IN_TESTS`` turns it on. The
    configuration registry lists both names for every ``monitor_switch`` call.
    """
    in_tests = f"{name}_IN_TESTS"

    def enabled() -> bool:
        if is_legacy_test_persistence():
            return _switch_on(in_tests, "0")
        return _switch_on(name, "1")

    enabled.__name__ = enabled.__qualname__ = f"monitor_switch({name})"
    return enabled


@dataclass(frozen=True, slots=True)
class TradingMonitorTask:
    """A monitor and how the scheduler runs it."""

    name: str
    monitor: ScheduledTradingMonitor
    enabled: Callable[[], bool]
    startup: tuple[Callable[[], Any], ...] = ()
    shutdown: tuple[Callable[[], Any], ...] = ()


def scheduled_task_spec(task: TradingMonitorTask) -> ScheduledTaskSpec:
    monitor = task.monitor
    run_once = getattr(monitor, "run_once", None)
    if not callable(run_once):
        raise TypeError(f"Scheduled trading monitor {task.name} must expose run_once()")
    interval_seconds = float(monitor.tick_seconds())

    def due() -> bool:
        now = time.monotonic()
        if not monitor.cycle_due(now):
            return False
        monitor.begin_cycle(now)
        return True

    run: Callable[[TaskContext], Any]
    if inspect.iscoroutinefunction(run_once):
        async def run_async(_task_context: TaskContext) -> None:
            if not due():
                return
            try:
                await on_trading_loop(run_once)
            except Exception as exc:
                monitor.record_cycle_error(exc)
                raise

        run = run_async
        executor = "async"
    else:
        def run_sync(_task_context: TaskContext) -> None:
            if not due():
                return
            try:
                result = run_once()
            except Exception as exc:
                monitor.record_cycle_error(exc)
                raise
            if inspect.isawaitable(result):
                raise TypeError(f"Synchronous trading monitor {task.name} returned an awaitable")

        run = run_sync
        executor = "thread"

    startup = task.startup
    prepare = getattr(monitor, "prepare_for_scheduled_execution", None)
    if not startup and callable(prepare):
        startup = (prepare,)
    shutdown = task.shutdown
    if executor == "async":
        # Its startup and shutdown run where its cycles do: a task or client a cycle made belongs to that loop.
        startup = tuple(_on_trading_loop_callback(callback) for callback in startup)
        shutdown = tuple(_on_trading_loop_callback(callback) for callback in shutdown)

    # The scheduler runs these only in the process that owns the task.
    def started() -> None:
        monitor.scheduled = True

    def stopped() -> None:
        monitor.scheduled = False

    return ScheduledTaskSpec(
        task_id=task.name,
        run=run,
        interval_seconds=max(0.25, interval_seconds),
        jitter_seconds=min(1.0, max(0.0, interval_seconds * 0.05)),
        timeout_seconds=monitor.run_timeout_seconds(),
        # One slow cycle (a provider stall at the open) must not stop the
        # monitor for the rest of the process lifetime; the next cycle retries.
        disable_on_timeout=False,
        executor=executor,
        enabled=task.enabled,
        on_startup=(*startup, started),
        on_shutdown=(stopped, *shutdown),
    )


__all__ = [
    "TRADING_MONITOR_TIMEOUT_SECONDS",
    "ScheduledTradingMonitor",
    "SingleFlightTasks",
    "TradingMonitorTask",
    "close_trading_loop",
    "monitor_switch",
    "on_trading_loop",
    "scheduled_task_spec",
]
