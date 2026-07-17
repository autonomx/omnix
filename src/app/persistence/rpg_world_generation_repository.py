from __future__ import annotations

from typing import Any, Mapping

from .errors import EntityNotFound
from .rpg_repository import canonical_json
from .tenant import TenantContext


_RUN_COLUMNS = """
workspace_id, run_id, world_id, draft_revision, status, graph_jsonb,
context_jsonb, settings_jsonb, plan_jsonb, progress_jsonb, error_jsonb,
parent_run_id, lineage_jsonb, created_at, updated_at, completed_at
"""


def _run_row(row: Any) -> dict[str, Any]:
    return {
        "workspace_id": str(row[0]),
        "run_id": str(row[1]),
        "world_id": str(row[2]),
        "draft_revision": int(row[3]),
        "status": str(row[4]),
        "graph": dict(row[5]),
        "context": dict(row[6]),
        "settings": dict(row[7]),
        "plan": dict(row[8]),
        "progress": dict(row[9]),
        "error": dict(row[10]),
        "parent_run_id": str(row[11]) if row[11] is not None else None,
        "lineage": dict(row[12]),
        "created_at": row[13].isoformat(),
        "updated_at": row[14].isoformat(),
        "completed_at": row[15].isoformat() if row[15] is not None else None,
    }


class PostgresRpgWorldGenerationRepository:
    """Durable coordination state for world-owned topic generation DAGs."""

    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def start(
        self,
        context: TenantContext,
        *,
        run_id: str,
        world_id: str,
        draft_revision: int,
        graph: Mapping[str, Any],
        generation_context: Mapping[str, Any],
        settings: Mapping[str, Any],
        plan: Mapping[str, Any],
        progress: Mapping[str, Any],
    ) -> dict[str, Any]:
        world = self.connection.execute(
            "SELECT status FROM omnix_rpg_worlds WHERE workspace_id = %s "
            "AND id = %s FOR UPDATE",
            (context.workspace_id, world_id),
        ).fetchone()
        if world is None:
            raise EntityNotFound(world_id)
        if str(world[0]) == "archived":
            raise ValueError(f"world_archived:{world_id}")
        parent = self.connection.execute(
            "SELECT run_id, draft_revision, lineage_jsonb "
            "FROM omnix_rpg_world_generation_runs "
            "WHERE workspace_id = %s AND world_id = %s AND draft_revision < %s "
            "ORDER BY draft_revision DESC LIMIT 1",
            (context.workspace_id, world_id, int(draft_revision)),
        ).fetchone()
        parent_run_id = str(parent[0]) if parent is not None else None
        parent_draft_revision = int(parent[1]) if parent is not None else None
        parent_lineage = dict(parent[2]) if parent is not None else {}
        root_run_id = str(parent_lineage.get("root_run_id") or parent_run_id or run_id)
        lineage = {
            "root_run_id": root_run_id,
            "parent_run_id": parent_run_id,
            "parent_draft_revision": parent_draft_revision,
            "draft_revision": int(draft_revision),
        }
        row = self.connection.execute(
            f"""
            INSERT INTO omnix_rpg_world_generation_runs (
                workspace_id, run_id, world_id, draft_revision, status,
                graph_jsonb, context_jsonb, settings_jsonb, plan_jsonb,
                progress_jsonb, parent_run_id, lineage_jsonb
            ) VALUES (%s, %s, %s, %s, 'planned', %s::jsonb, %s::jsonb,
                      %s::jsonb, %s::jsonb, %s::jsonb, %s, %s::jsonb)
            ON CONFLICT (workspace_id, world_id, draft_revision) DO NOTHING
            RETURNING {_RUN_COLUMNS}
            """,
            (
                context.workspace_id,
                run_id,
                world_id,
                int(draft_revision),
                canonical_json(dict(graph)),
                canonical_json(dict(generation_context)),
                canonical_json(dict(settings)),
                canonical_json(dict(plan)),
                canonical_json(dict(progress)),
                parent_run_id,
                canonical_json(lineage),
            ),
        ).fetchone()
        if row is not None:
            return _run_row(row)
        existing = self.get_for_world_revision(
            context,
            world_id=world_id,
            draft_revision=draft_revision,
        )
        if existing is None:
            raise RuntimeError("world_generation_run_insert_failed")
        if existing["run_id"] != run_id:
            raise RuntimeError("world_generation_run_identity_conflict")
        return existing

    def get(self, context: TenantContext, run_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            f"SELECT {_RUN_COLUMNS} FROM omnix_rpg_world_generation_runs "
            "WHERE workspace_id = %s AND run_id = %s",
            (context.workspace_id, run_id),
        ).fetchone()
        return _run_row(row) if row is not None else None

    def get_for_world_revision(
        self,
        context: TenantContext,
        *,
        world_id: str,
        draft_revision: int,
    ) -> dict[str, Any] | None:
        row = self.connection.execute(
            f"SELECT {_RUN_COLUMNS} FROM omnix_rpg_world_generation_runs "
            "WHERE workspace_id = %s AND world_id = %s AND draft_revision = %s",
            (context.workspace_id, world_id, int(draft_revision)),
        ).fetchone()
        return _run_row(row) if row is not None else None

    def update(
        self,
        context: TenantContext,
        *,
        run_id: str,
        status: str | None = None,
        plan: Mapping[str, Any] | None = None,
        progress: Mapping[str, Any] | None = None,
        error: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        row = self.connection.execute(
            f"""
            UPDATE omnix_rpg_world_generation_runs
               SET status = COALESCE(%s, status),
                   plan_jsonb = COALESCE(%s::jsonb, plan_jsonb),
                   progress_jsonb = COALESCE(%s::jsonb, progress_jsonb),
                   error_jsonb = COALESCE(%s::jsonb, error_jsonb),
                   completed_at = CASE
                       WHEN COALESCE(%s, status) IN ('ready', 'failed', 'canceled')
                       THEN COALESCE(completed_at, CURRENT_TIMESTAMP)
                       ELSE completed_at
                   END,
                   updated_at = CURRENT_TIMESTAMP
             WHERE workspace_id = %s AND run_id = %s
            RETURNING {_RUN_COLUMNS}
            """,
            (
                status,
                canonical_json(dict(plan)) if plan is not None else None,
                canonical_json(dict(progress)) if progress is not None else None,
                canonical_json(dict(error)) if error is not None else None,
                status,
                context.workspace_id,
                run_id,
            ),
        ).fetchone()
        if row is None:
            raise EntityNotFound(run_id)
        return _run_row(row)

    def get_topic(
        self,
        context: TenantContext,
        *,
        world_id: str,
        topic_id: str,
    ) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT topic_id, draft_revision, source, status, content_jsonb,
                   directives_jsonb, dependency_hashes_jsonb, input_hash,
                   content_hash, provenance_jsonb, updated_at
              FROM omnix_rpg_world_topics
             WHERE workspace_id = %s AND world_id = %s AND topic_id = %s
            """,
            (context.workspace_id, world_id, topic_id),
        ).fetchone()
        return _topic_row(row) if row is not None else None

    def list_topics(
        self,
        context: TenantContext,
        *,
        world_id: str,
        draft_revision: int,
    ) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT topic_id, draft_revision, source, status, content_jsonb,
                   directives_jsonb, dependency_hashes_jsonb, input_hash,
                   content_hash, provenance_jsonb, updated_at
              FROM omnix_rpg_world_topics
             WHERE workspace_id = %s AND world_id = %s AND draft_revision = %s
             ORDER BY topic_id
            """,
            (context.workspace_id, world_id, int(draft_revision)),
        ).fetchall()
        return [_topic_row(row) for row in rows]


def _topic_row(row: Any) -> dict[str, Any]:
    return {
        "topic_id": str(row[0]),
        "draft_revision": int(row[1]),
        "source": str(row[2]),
        "status": str(row[3]),
        "content": dict(row[4]),
        "directives": dict(row[5]),
        "dependency_hashes": dict(row[6]),
        "input_hash": str(row[7]),
        "content_hash": str(row[8]),
        "provenance": dict(row[9]),
        "updated_at": row[10].isoformat(),
    }
