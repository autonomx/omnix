"""Supervised gateway identity backed by the existing runtime-node lease ledger."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import logging
import os
import uuid

from .authority import AuthorityOperation, require_authority_operation
from .runtime_coordination import (
    PostgresRuntimeCoordinationRepository,
    RuntimeNodeConflict,
)

logger = logging.getLogger(__name__)


class GatewayRuntimeOwner:
    def __init__(
        self,
        database,
        workspace_id: str,
        *,
        lease_seconds: int = 30,
        heartbeat_seconds: float = 5,
        recovery_seconds: float = 15,
    ):
        if (
            not 1 <= lease_seconds <= 3600
            or not 0 < heartbeat_seconds < lease_seconds
            or recovery_seconds <= 0
        ):
            raise ValueError(
                "lease must be 1–3600 seconds; heartbeat must be shorter; recovery must be positive"
            )
        self.database = database
        self.workspace_id = workspace_id
        # Never reuse an expired process identity: old workers must not become live again.
        self.node_id = f"gateway:{uuid.uuid4().hex}"
        self.lease_seconds = lease_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self.recovery_seconds = recovery_seconds
        self.healthy = False
        self._registered = False
        self.recover = None

    def _mutate(self, operation):
        with self.database.transaction() as connection:
            require_authority_operation(connection, AuthorityOperation.RUNTIME_MUTATION)
            return operation(PostgresRuntimeCoordinationRepository(connection))

    def register(self):
        if self._registered:
            raise RuntimeNodeConflict(
                "A gateway process identity cannot be registered again"
            )
        self._mutate(
            lambda repository: repository.register(
                node_id=self.node_id,
                node_type="gateway",
                software_version=os.environ.get(
                    "OMNIX_SOFTWARE_REVISION", "unversioned"
                ),
                process_id=str(os.getpid()),
                lease_seconds=self.lease_seconds,
                metadata={"workspace_id": self.workspace_id},
            )
        )
        self.healthy = True
        self._registered = True

    def heartbeat(self):
        self._mutate(
            lambda repository: repository.heartbeat(
                node_id=self.node_id,
                lease_seconds=self.lease_seconds,
            )
        )

    def require_live(self, connection):
        if not self.healthy:
            raise RuntimeNodeConflict("Gateway execution owner is unavailable")
        row = connection.execute(
            "SELECT id FROM omnix_runtime_nodes WHERE id = %s AND node_type = 'gateway' "
            "AND status = 'active' AND lease_expires_at > clock_timestamp() "
            "AND metadata ->> 'workspace_id' = %s",
            (self.node_id, self.workspace_id),
        ).fetchone()
        if row is None:
            raise RuntimeNodeConflict("Gateway execution owner lease is no longer live")

    def ready(self):
        if not self.healthy:
            return False
        with self.database.connection() as connection:
            self.require_live(connection)
        return True

    async def _heartbeats(self):
        while True:
            await asyncio.sleep(self.heartbeat_seconds)
            try:
                await asyncio.to_thread(self.heartbeat)
            except Exception:
                # Latch failure; this process never re-registers its expired identity.
                self.healthy = False
                logger.exception(
                    "Gateway runtime heartbeat failed; Chat admission is disabled"
                )
                return

    async def _recoveries(self):
        while True:
            await asyncio.sleep(self.recovery_seconds)
            if not self.healthy:
                return
            try:
                if self.recover is not None:
                    await asyncio.to_thread(self.recover)
            except Exception:
                logger.exception(
                    "Periodic Chat recovery failed; will retry on the next cycle"
                )

    @asynccontextmanager
    async def lifespan(self):
        await asyncio.to_thread(self.register)
        tasks = [
            asyncio.create_task(self._heartbeats()),
            asyncio.create_task(self._recoveries()),
        ]
        try:
            yield
        finally:
            self.healthy = False
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            try:
                await asyncio.to_thread(
                    self._mutate, lambda repository: repository.stop(self.node_id)
                )
            except Exception:
                logger.exception(
                    "Could not stop gateway runtime node; its lease will expire"
                )
