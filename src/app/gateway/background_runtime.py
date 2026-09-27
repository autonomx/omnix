"""One explicitly assigned background worker process, with supervised hooks."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from functools import wraps
import hashlib
import inspect
import logging
import threading

from app.persistence.authority import AuthorityOperation, require_authority_operation
from app.persistence.background_authority import background_execution

logger = logging.getLogger(__name__)


class BackgroundOwnershipUnavailable(RuntimeError):
    pass


class GatewayBackgroundRuntime:
    def __init__(
        self,
        database,
        workspace_id: str,
        *,
        role: str = "worker",
        poll_seconds: float = 2,
    ):
        if role not in ("api", "worker") or poll_seconds <= 0:
            raise ValueError(
                "background role must be api or worker, with a positive supervision interval"
            )
        self.database = database
        self.role = role
        self.poll_seconds = poll_seconds
        digest = hashlib.sha256(
            f"omnix:gateway-background:{workspace_id}".encode()
        ).digest()
        self.lock_key = int.from_bytes(digest[:8], "big", signed=True)
        self.healthy = False
        self.connection = None
        self._connection_context = None
        self._connection_lock = threading.Lock()
        self._workers = []
        self._started = []

    def acquire(self):
        if self.role == "api":
            return
        self._connection_context = self.database.connection()
        connection = self._connection_context.__enter__()
        try:
            require_authority_operation(connection, AuthorityOperation.RUNTIME_MUTATION)
            acquired = connection.execute(
                "SELECT pg_try_advisory_lock(%s)", (self.lock_key,)
            ).fetchone()[0]
            connection.commit()
            if not acquired:
                raise BackgroundOwnershipUnavailable(
                    "Another process owns background workers; use OMNIX_GATEWAY_BACKGROUND_ROLE=api for API replicas"
                )
            self.connection = connection
            self.healthy = True
        except BaseException:
            self._connection_context.__exit__(*__import__("sys").exc_info())
            self._connection_context = None
            raise

    def require_live(self):
        if self.role != "worker" or not self.healthy or self.connection is None:
            raise BackgroundOwnershipUnavailable(
                "This gateway does not own background execution"
            )
        try:
            with self._connection_lock:
                self.connection.execute("SELECT 1").fetchone()
                self.connection.commit()
        except Exception as exc:
            self.healthy = False
            raise BackgroundOwnershipUnavailable(
                "Background ownership connection was lost"
            ) from exc

    def ready(self):
        if self.role == "api":
            return True
        self.require_live()
        return True

    def register(self, name, monitor, startup, shutdown):
        # Protect manual control endpoints as well as startup hooks.
        original_start = getattr(monitor, "start", None)
        if original_start is not None:

            @wraps(original_start)
            def start(*args, **kwargs):
                with background_execution(self):
                    result = original_start(*args, **kwargs)
                    service = getattr(monitor, "service", None)
                    buffer = getattr(
                        getattr(service, "binance", None), "liquidation_buffer", None
                    )
                    if buffer is not None:
                        buffer.start_guard = self.require_live
                    return result

            monitor.start = start
        self._workers.append((name, startup, shutdown))

    async def _call(self, callback):
        result = callback()
        if inspect.isawaitable(result):
            await result

    async def startup(self):
        if self.role == "api":
            return
        for worker in self._workers:
            self._started.append(worker)
            with background_execution(self):
                for callback in worker[1]:
                    await self._call(callback)

    async def shutdown(self):
        failed = []
        for name, _, callbacks in reversed(self._started):
            for callback in reversed(callbacks):
                try:
                    await asyncio.wait_for(self._call(callback), timeout=10)
                except Exception:
                    failed.append(name)
                    logger.exception("Background worker shutdown failed: %s", name)
        self._started.clear()
        if failed:
            raise RuntimeError(f"Background workers did not stop: {failed}")

    async def _supervise(self):
        while True:
            await asyncio.sleep(self.poll_seconds)
            try:
                await asyncio.to_thread(self.require_live)
            except Exception:
                self.healthy = False
                logger.exception("Background ownership lost; stopping workers")
                await self.shutdown()
                return

    def release(self):
        self.healthy = False
        context, self._connection_context = self._connection_context, None
        connection, self.connection = self.connection, None
        if context is not None:
            try:
                with self._connection_lock:
                    if not connection.closed:
                        connection.execute(
                            "SELECT pg_advisory_unlock(%s)", (self.lock_key,)
                        )
                        connection.commit()
            except Exception:
                logger.warning(
                    "Background ownership connection unavailable during release",
                    exc_info=True,
                )
                connection.close()
            finally:
                try:
                    context.__exit__(None, None, None)
                except Exception:
                    logger.warning(
                        "Could not return background ownership connection",
                        exc_info=True,
                    )

    @asynccontextmanager
    async def lifespan(self):
        await asyncio.to_thread(self.acquire)
        task = asyncio.create_task(self._supervise()) if self.role == "worker" else None
        try:
            yield
        finally:
            if task is not None:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            try:
                await self.shutdown()
            finally:
                await asyncio.to_thread(self.release)


def register_background_monitor(gateway, registrar):
    runtime = getattr(gateway.state, "background_runtime", None)
    if runtime is None:
        return registrar(gateway)
    starts, stops = len(gateway.router.on_startup), len(gateway.router.on_shutdown)
    monitor = registrar(gateway)
    startup = gateway.router.on_startup[starts:]
    shutdown = gateway.router.on_shutdown[stops:]
    del gateway.router.on_startup[starts:]
    del gateway.router.on_shutdown[stops:]
    runtime.register(registrar.__name__, monitor, startup, shutdown)
    return monitor
