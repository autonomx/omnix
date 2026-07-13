from __future__ import annotations

import hashlib
import json
from typing import Any

from .database import PostgresDatabase
from .migrations import apply_migrations
from .tenant import TenantContext
from .unit_of_work import unit_of_work


def _request_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def bootstrap_local_tenant(database: PostgresDatabase) -> TenantContext:
    apply_migrations(database)
    with unit_of_work(database) as work:
        context = work.identities.ensure_local_identity()
        work.audit.append(
            context,
            aggregate_type="workspace",
            aggregate_id=context.workspace_id,
            action="workspace.local_bootstrap",
            payload={"local_installation": True},
        )
        work.commit()
        return context


def get_workspace(database: PostgresDatabase, context: TenantContext) -> dict[str, Any]:
    with unit_of_work(database) as work:
        workspace = work.identities.get_workspace(context, context.workspace_id)
        if workspace is None:
            raise KeyError(context.workspace_id)
        work.rollback()
        return workspace


def rename_workspace(
    database: PostgresDatabase,
    context: TenantContext,
    *,
    name: str,
    expected_revision: int,
    operation_key: str,
) -> dict[str, Any]:
    request = {
        "workspace_id": context.workspace_id,
        "name": str(name).strip(),
        "expected_revision": int(expected_revision),
    }
    digest = _request_hash(request)
    with unit_of_work(database) as work:
        reservation = work.idempotency.reserve(
            context,
            scope="workspace.rename",
            key=operation_key,
            request_hash=digest,
        )
        if reservation["status"] == "completed":
            response = reservation.get("response")
            if not isinstance(response, dict):
                raise RuntimeError("completed idempotency record has no response")
            work.rollback()
            return response
        if not reservation["owner"]:
            raise RuntimeError("workspace rename is already in progress")
        workspace = work.identities.update_workspace_name(
            context,
            workspace_id=context.workspace_id,
            name=request["name"],
            expected_revision=expected_revision,
        )
        work.audit.append(
            context,
            aggregate_type="workspace",
            aggregate_id=context.workspace_id,
            action="workspace.renamed",
            payload={
                "revision": workspace["revision"],
                "operation_key": operation_key,
            },
        )
        work.idempotency.complete(
            context,
            scope="workspace.rename",
            key=operation_key,
            response=workspace,
        )
        work.commit()
        return workspace
