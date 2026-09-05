"""PostgreSQL persistence for the coding quality controller.

Quality state is deliberately separate from AgentRunStatus.  A worker crash can
therefore recover the run lifecycle and the exact quality stage independently.
"""
from __future__ import annotations

import json
from typing import Any

from app.persistence.tenant import TenantContext

from .contracts import ReviewResult, ReviewSnapshot, ValidationResult, WorkspaceState


def _json(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


class PostgresCodingQualityRepository:
    def __init__(self, connection: Any, context: TenantContext) -> None:
        self.connection = connection
        self.context = context

    def set_stage(
        self,
        run_id: str,
        *,
        stage: str,
        attempt: int,
        task_revision_id: str | None,
        workspace_state_id: str | None = None,
    ) -> dict[str, object]:
        row = self.connection.execute(
            """
            INSERT INTO omnix_agent_coding_quality_state (
                workspace_id, run_id, stage, attempt, task_revision_id,
                workspace_state_id, stage_started_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (workspace_id, run_id) DO UPDATE
               SET stage = EXCLUDED.stage,
                   attempt = EXCLUDED.attempt,
                   task_revision_id = EXCLUDED.task_revision_id,
                   workspace_state_id = EXCLUDED.workspace_state_id,
                   stage_started_at = CASE
                       WHEN omnix_agent_coding_quality_state.stage IS DISTINCT FROM EXCLUDED.stage
                         OR omnix_agent_coding_quality_state.attempt IS DISTINCT FROM EXCLUDED.attempt
                       THEN CURRENT_TIMESTAMP
                       ELSE omnix_agent_coding_quality_state.stage_started_at
                   END,
                   updated_at = CURRENT_TIMESTAMP
            RETURNING stage, attempt, task_revision_id, workspace_state_id,
                      stage_started_at, updated_at
            """,
            (
                self.context.workspace_id,
                run_id,
                stage,
                attempt,
                task_revision_id,
                workspace_state_id,
            ),
        ).fetchone()
        return {
            "stage": str(row[0]),
            "attempt": int(row[1]),
            "task_revision_id": str(row[2]) if row[2] else None,
            "workspace_state_id": str(row[3]) if row[3] else None,
            "stage_started_at": row[4],
            "updated_at": row[5],
        }

    def get_stage(self, run_id: str) -> dict[str, object] | None:
        row = self.connection.execute(
            """
            SELECT stage, attempt, task_revision_id, workspace_state_id,
                   stage_started_at, updated_at
              FROM omnix_agent_coding_quality_state
             WHERE workspace_id = %s AND run_id = %s
            """,
            (self.context.workspace_id, run_id),
        ).fetchone()
        if row is None:
            return None
        return {
            "stage": str(row[0]),
            "attempt": int(row[1]),
            "task_revision_id": str(row[2]) if row[2] else None,
            "workspace_state_id": str(row[3]) if row[3] else None,
            "stage_started_at": row[4],
            "updated_at": row[5],
        }

    def add_workspace_state(self, state: WorkspaceState) -> WorkspaceState:
        self.connection.execute(
            """
            INSERT INTO omnix_agent_workspace_states (
                workspace_id, run_id, state_id, task_revision_id, base_commit_sha,
                tracked_diff_sha256, untracked_file_manifest_sha256,
                modified_paths, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            ON CONFLICT (workspace_id, run_id, state_id) DO NOTHING
            """,
            (
                self.context.workspace_id,
                state.run_id,
                state.state_id,
                state.task_revision_id,
                state.base_commit_sha,
                state.tracked_diff_sha256,
                state.untracked_file_manifest_sha256,
                _json(state.modified_paths),
                state.created_at,
            ),
        )
        return state

    def get_workspace_state(self, run_id: str, state_id: str) -> WorkspaceState | None:
        row = self.connection.execute(
            """
            SELECT task_revision_id, base_commit_sha, tracked_diff_sha256,
                   untracked_file_manifest_sha256, modified_paths, created_at
              FROM omnix_agent_workspace_states
             WHERE workspace_id = %s AND run_id = %s AND state_id = %s
            """,
            (self.context.workspace_id, run_id, state_id),
        ).fetchone()
        if row is None:
            return None
        return WorkspaceState(
            state_id=state_id,
            run_id=run_id,
            task_revision_id=str(row[0]) if row[0] else None,
            base_commit_sha=str(row[1]),
            tracked_diff_sha256=str(row[2]),
            untracked_file_manifest_sha256=str(row[3]),
            modified_paths=list(row[4] or []),
            created_at=row[5],
        )

    def latest_workspace_state(
        self,
        run_id: str,
        *,
        task_revision_id: str | None = None,
    ) -> WorkspaceState | None:
        if task_revision_id is None:
            row = self.connection.execute(
                """
                SELECT state_id
                  FROM omnix_agent_workspace_states
                 WHERE workspace_id = %s AND run_id = %s
                 ORDER BY created_at DESC, state_id DESC
                 LIMIT 1
                """,
                (self.context.workspace_id, run_id),
            ).fetchone()
        else:
            row = self.connection.execute(
                """
                SELECT state_id
                  FROM omnix_agent_workspace_states
                 WHERE workspace_id = %s AND run_id = %s AND task_revision_id = %s
                 ORDER BY created_at DESC, state_id DESC
                 LIMIT 1
                """,
                (self.context.workspace_id, run_id, task_revision_id),
            ).fetchone()
        return self.get_workspace_state(run_id, str(row[0])) if row else None

    def add_validation_result(self, result: ValidationResult) -> ValidationResult:
        self.connection.execute(
            """
            INSERT INTO omnix_agent_validation_results (
                workspace_id, run_id, result_id, validation_id, kind,
                task_revision_id, workspace_state_id, command, exit_code,
                success, output_digest, started_at, finished_at, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (workspace_id, run_id, result_id) DO NOTHING
            """,
            (
                self.context.workspace_id,
                result.run_id,
                result.result_id,
                result.validation_id,
                result.kind,
                result.task_revision_id,
                result.workspace_state_id,
                result.command,
                result.exit_code,
                result.success,
                result.output_digest,
                result.started_at,
                result.finished_at,
                _json(result.metadata),
            ),
        )
        return result

    def list_validation_results(
        self,
        run_id: str,
        *,
        task_revision_id: str | None = None,
    ) -> list[ValidationResult]:
        if task_revision_id is None:
            rows = self.connection.execute(
                """
                SELECT result_id, validation_id, kind, task_revision_id,
                       workspace_state_id, command, exit_code, success,
                       output_digest, started_at, finished_at, metadata
                  FROM omnix_agent_validation_results
                 WHERE workspace_id = %s AND run_id = %s
                 ORDER BY finished_at, result_id
                """,
                (self.context.workspace_id, run_id),
            ).fetchall()
        else:
            rows = self.connection.execute(
                """
                SELECT result_id, validation_id, kind, task_revision_id,
                       workspace_state_id, command, exit_code, success,
                       output_digest, started_at, finished_at, metadata
                  FROM omnix_agent_validation_results
                 WHERE workspace_id = %s AND run_id = %s AND task_revision_id = %s
                 ORDER BY finished_at, result_id
                """,
                (self.context.workspace_id, run_id, task_revision_id),
            ).fetchall()
        return [
            ValidationResult(
                result_id=str(row[0]),
                run_id=run_id,
                validation_id=str(row[1]),
                kind=str(row[2]),
                task_revision_id=str(row[3]) if row[3] else None,
                workspace_state_id=str(row[4]),
                command=str(row[5]),
                exit_code=int(row[6]) if row[6] is not None else None,
                success=bool(row[7]),
                output_digest=str(row[8]),
                started_at=row[9],
                finished_at=row[10],
                metadata=dict(row[11] or {}),
            )
            for row in rows
        ]

    def add_review_snapshot(self, snapshot: ReviewSnapshot) -> ReviewSnapshot:
        self.connection.execute(
            """
            INSERT INTO omnix_agent_review_snapshots (
                workspace_id, run_id, snapshot_id, task_revision_id,
                workspace_state_id, base_commit_sha, patch_checksum,
                patch_storage_ref, workspace_root, relevant_files,
                validation_result_ids, repository_guidance_digest, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
            ON CONFLICT (workspace_id, run_id, snapshot_id) DO NOTHING
            """,
            (
                self.context.workspace_id,
                snapshot.run_id,
                snapshot.snapshot_id,
                snapshot.task_revision_id,
                snapshot.workspace_state_id,
                snapshot.base_commit_sha,
                snapshot.patch_checksum,
                snapshot.patch_storage_ref,
                snapshot.workspace_root,
                _json(snapshot.relevant_files),
                _json(snapshot.validation_result_ids),
                snapshot.repository_guidance_digest,
                snapshot.created_at,
            ),
        )
        return snapshot

    def get_review_snapshot(self, run_id: str, snapshot_id: str) -> ReviewSnapshot | None:
        row = self.connection.execute(
            """
            SELECT task_revision_id, workspace_state_id, base_commit_sha,
                   patch_checksum, patch_storage_ref, workspace_root,
                   relevant_files, validation_result_ids,
                   repository_guidance_digest, created_at
              FROM omnix_agent_review_snapshots
             WHERE workspace_id = %s AND run_id = %s AND snapshot_id = %s
            """,
            (self.context.workspace_id, run_id, snapshot_id),
        ).fetchone()
        if row is None:
            return None
        return ReviewSnapshot(
            snapshot_id=snapshot_id,
            run_id=run_id,
            task_revision_id=str(row[0]) if row[0] else None,
            workspace_state_id=str(row[1]),
            base_commit_sha=str(row[2]),
            patch_checksum=str(row[3]),
            patch_storage_ref=str(row[4]) if row[4] else None,
            workspace_root=str(row[5]),
            relevant_files=list(row[6] or []),
            validation_result_ids=list(row[7] or []),
            repository_guidance_digest=str(row[8]) if row[8] else None,
            created_at=row[9],
        )

    def latest_review_snapshot(
        self,
        run_id: str,
        *,
        task_revision_id: str | None,
        workspace_state_id: str,
    ) -> ReviewSnapshot | None:
        row = self.connection.execute(
            """
            SELECT snapshot_id
              FROM omnix_agent_review_snapshots
             WHERE workspace_id = %s AND run_id = %s
               AND task_revision_id IS NOT DISTINCT FROM %s
               AND workspace_state_id = %s
             ORDER BY created_at DESC, snapshot_id DESC
             LIMIT 1
            """,
            (self.context.workspace_id, run_id, task_revision_id, workspace_state_id),
        ).fetchone()
        return self.get_review_snapshot(run_id, str(row[0])) if row else None

    def add_review_result(self, result: ReviewResult) -> ReviewResult:
        self.connection.execute(
            """
            INSERT INTO omnix_agent_review_results (
                workspace_id, run_id, review_result_id, reviewer_run_id,
                review_snapshot_id, task_revision_id, workspace_state_id,
                verdict, requirements, findings, missing_tests,
                residual_risks, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s)
            ON CONFLICT (workspace_id, run_id, review_result_id) DO NOTHING
            """,
            (
                self.context.workspace_id,
                result.run_id,
                result.review_result_id,
                result.reviewer_run_id,
                result.review_snapshot_id,
                result.task_revision_id,
                result.workspace_state_id,
                result.verdict,
                _json(result.requirements),
                _json(result.findings),
                _json(result.missing_tests),
                _json(result.residual_risks),
                result.created_at,
            ),
        )
        return result

    def list_review_results(
        self,
        run_id: str,
        *,
        task_revision_id: str | None = None,
    ) -> list[ReviewResult]:
        if task_revision_id is None:
            rows = self.connection.execute(
                """
                SELECT review_result_id, reviewer_run_id, review_snapshot_id,
                       task_revision_id, workspace_state_id, verdict,
                       requirements, findings, missing_tests, residual_risks,
                       created_at
                  FROM omnix_agent_review_results
                 WHERE workspace_id = %s AND run_id = %s
                 ORDER BY created_at, review_result_id
                """,
                (self.context.workspace_id, run_id),
            ).fetchall()
        else:
            rows = self.connection.execute(
                """
                SELECT review_result_id, reviewer_run_id, review_snapshot_id,
                       task_revision_id, workspace_state_id, verdict,
                       requirements, findings, missing_tests, residual_risks,
                       created_at
                  FROM omnix_agent_review_results
                 WHERE workspace_id = %s AND run_id = %s AND task_revision_id = %s
                 ORDER BY created_at, review_result_id
                """,
                (self.context.workspace_id, run_id, task_revision_id),
            ).fetchall()
        return [
            ReviewResult(
                review_result_id=str(row[0]),
                run_id=run_id,
                reviewer_run_id=str(row[1]),
                review_snapshot_id=str(row[2]),
                task_revision_id=str(row[3]) if row[3] else None,
                workspace_state_id=str(row[4]),
                verdict=str(row[5]),
                requirements=list(row[6] or []),
                findings=list(row[7] or []),
                missing_tests=list(row[8] or []),
                residual_risks=list(row[9] or []),
                created_at=row[10],
            )
            for row in rows
        ]
