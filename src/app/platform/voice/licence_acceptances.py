"""Recorded licence acceptances for model installs (desktop roadmap D-4, DT-2.3; migration 0168).

A model installs only after someone in the workspace accepted its licence for
the exact revision the catalog pins. The acceptance is recorded when the
install is submitted (the request names ``accept_terms``) and checked when the
install job runs, so an install without a recorded acceptance is refused even
if a job is submitted some other way. Rows are workspace-scoped
(``tenant_isolation``) and every query also names the workspace.

Without PostgreSQL (a lightweight developer run) acceptances are not stored;
Voice Studio's install marker keeps the acceptance flag as before.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.persistence.unit_of_work import unit_of_work
from app.runtime.tenant_context import current_tenant


def available() -> bool:
    from app.persistence.runtime import uses_postgresql_runtime

    return uses_postgresql_runtime()


def record(models: Iterable[Any]) -> int:
    """Records the current user's acceptance of each model (catalog entries) at its pinned revision."""
    tenant = current_tenant()
    rows = [(tenant.workspace_id, tenant.user_id, entry.id, entry.revision, entry.licence.id, entry.licence.url)
            for entry in models]
    if not rows:
        return 0
    with unit_of_work() as work:
        for row in rows:
            work.connection.execute(
                "INSERT INTO omnix_model_licence_acceptances "
                "(workspace_id, user_id, model_id, revision, licence_id, licence_url) VALUES (%s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (workspace_id, model_id, revision, user_id) DO NOTHING",
                row,
            )
        work.commit()
    return len(rows)


def accepted(model_id: str, revision: str, licence_id: str) -> bool:
    """Whether anyone in the current workspace accepted this model's licence at this revision.

    A catalog update that changes the licence at the same revision asks again (roadmap R-8)."""
    workspace = current_tenant().workspace_id
    with unit_of_work() as work:
        row = work.connection.execute(
            "SELECT 1 FROM omnix_model_licence_acceptances WHERE workspace_id = %s AND model_id = %s AND revision = %s "
            "AND licence_id = %s LIMIT 1",
            (workspace, model_id, revision, licence_id),
        ).fetchone()
    return row is not None


def accepted_models() -> dict[str, set[tuple[str, str]]]:
    """model id -> the (revision, licence id) pairs accepted in the current workspace."""
    workspace = current_tenant().workspace_id
    with unit_of_work() as work:
        rows = work.connection.execute(
            "SELECT model_id, revision, licence_id FROM omnix_model_licence_acceptances WHERE workspace_id = %s",
            (workspace,),
        ).fetchall()
    found: dict[str, set[tuple[str, str]]] = {}
    for model_id, revision, licence_id in rows:
        found.setdefault(str(model_id), set()).add((str(revision), str(licence_id)))
    return found


__all__ = ["accepted", "accepted_models", "available", "record"]
