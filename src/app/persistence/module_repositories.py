from __future__ import annotations

import json
from typing import Any

from .errors import EntityNotFound, RevisionConflict
from .tenant import TenantContext


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class PostgresModuleRecordRepository:
    """Tenant-scoped durable records for small modules without bespoke schemas."""

    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def get(
        self,
        context: TenantContext,
        *,
        module: str,
        record_type: str,
        record_id: str,
        include_expired: bool = False,
    ) -> dict[str, Any] | None:
        expiry = "" if include_expired else " AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)"
        row = self.connection.execute(
            """
            SELECT module, record_type, record_id, owner_user_id, payload,
                   status, revision, expires_at, created_at, updated_at
              FROM omnix_module_records
             WHERE workspace_id = %s AND module = %s AND record_type = %s
               AND record_id = %s
            """
            + expiry,
            (context.workspace_id, module, record_type, record_id),
        ).fetchone()
        return self._record(row) if row is not None else None

    def put(
        self,
        context: TenantContext,
        *,
        module: str,
        record_type: str,
        record_id: str,
        payload: dict[str, Any],
        status: str = "active",
        expires_at: str | None = None,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        if expected_revision is None:
            row = self.connection.execute(
                """
                INSERT INTO omnix_module_records (
                    workspace_id, module, record_type, record_id, owner_user_id,
                    payload, status, expires_at
                ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s::timestamptz)
                ON CONFLICT DO NOTHING
                RETURNING module, record_type, record_id, owner_user_id, payload,
                          status, revision, expires_at, created_at, updated_at
                """,
                (
                    context.workspace_id,
                    module,
                    record_type,
                    record_id,
                    context.user_id,
                    _json(payload),
                    status,
                    expires_at,
                ),
            ).fetchone()
            if row is None:
                raise RevisionConflict(
                    f"module record already exists: {module}/{record_type}/{record_id}"
                )
        else:
            row = self.connection.execute(
                """
                UPDATE omnix_module_records
                   SET payload = %s::jsonb, status = %s,
                       expires_at = %s::timestamptz,
                       revision = revision + 1,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE workspace_id = %s AND module = %s AND record_type = %s
                   AND record_id = %s AND revision = %s
                RETURNING module, record_type, record_id, owner_user_id, payload,
                          status, revision, expires_at, created_at, updated_at
                """,
                (
                    _json(payload),
                    status,
                    expires_at,
                    context.workspace_id,
                    module,
                    record_type,
                    record_id,
                    expected_revision,
                ),
            ).fetchone()
            if row is None:
                raise RevisionConflict(
                    f"module record expected revision {expected_revision}: "
                    f"{module}/{record_type}/{record_id}"
                )
        return self._record(row)

    def list(
        self,
        context: TenantContext,
        *,
        module: str,
        record_type: str,
        status: str = "active",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT module, record_type, record_id, owner_user_id, payload,
                   status, revision, expires_at, created_at, updated_at
              FROM omnix_module_records
             WHERE workspace_id = %s AND module = %s AND record_type = %s
               AND status = %s AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
             ORDER BY updated_at DESC, record_id LIMIT %s
            """,
            (
                context.workspace_id,
                module,
                record_type,
                status,
                max(1, min(int(limit), 500)),
            ),
        ).fetchall()
        return [self._record(row) for row in rows]

    @staticmethod
    def _record(row: Any) -> dict[str, Any]:
        return {
            "module": str(row[0]),
            "record_type": str(row[1]),
            "record_id": str(row[2]),
            "owner_user_id": str(row[3]) if row[3] is not None else None,
            "payload": dict(row[4]),
            "status": str(row[5]),
            "revision": int(row[6]),
            "expires_at": row[7].isoformat() if row[7] is not None else None,
            "created_at": row[8].isoformat(),
            "updated_at": row[9].isoformat(),
        }


class PostgresProjectionRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def put(
        self,
        context: TenantContext,
        *,
        projection_type: str,
        projection_key: str,
        payload: dict[str, Any],
        source_revision: int | None = None,
        expires_at: str | None = None,
    ) -> dict[str, Any]:
        row = self.connection.execute(
            """
            INSERT INTO omnix_runtime_projections (
                workspace_id, projection_type, projection_key, payload,
                source_revision, expires_at
            ) VALUES (%s, %s, %s, %s::jsonb, %s, %s::timestamptz)
            ON CONFLICT (workspace_id, projection_type, projection_key)
            DO UPDATE SET payload = EXCLUDED.payload,
                          source_revision = EXCLUDED.source_revision,
                          observed_at = CURRENT_TIMESTAMP,
                          expires_at = EXCLUDED.expires_at
            RETURNING projection_type, projection_key, payload, source_revision,
                      observed_at, expires_at
            """,
            (
                context.workspace_id,
                projection_type,
                projection_key,
                _json(payload),
                source_revision,
                expires_at,
            ),
        ).fetchone()
        return self._record(row)

    def get(
        self,
        context: TenantContext,
        *,
        projection_type: str,
        projection_key: str,
    ) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT projection_type, projection_key, payload, source_revision,
                   observed_at, expires_at
              FROM omnix_runtime_projections
             WHERE workspace_id = %s AND projection_type = %s AND projection_key = %s
               AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
            """,
            (context.workspace_id, projection_type, projection_key),
        ).fetchone()
        return self._record(row) if row is not None else None

    @staticmethod
    def _record(row: Any) -> dict[str, Any]:
        return {
            "projection_type": str(row[0]),
            "projection_key": str(row[1]),
            "payload": dict(row[2]),
            "source_revision": int(row[3]) if row[3] is not None else None,
            "observed_at": row[4].isoformat(),
            "expires_at": row[5].isoformat() if row[5] is not None else None,
        }


class PostgresProviderRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def create(
        self,
        context: TenantContext,
        *,
        provider_id: str,
        provider_type: str,
        display_name: str,
        config: dict[str, Any],
        secret_reference: str | None = None,
        enabled: bool = True,
    ) -> dict[str, Any]:
        self._reject_secret_values(config)
        row = self.connection.execute(
            """
            INSERT INTO omnix_provider_configs (
                id, workspace_id, provider_type, display_name, config,
                secret_reference, enabled
            ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)
            RETURNING id, provider_type, display_name, config, secret_reference,
                      enabled, revision, created_at, updated_at
            """,
            (
                provider_id,
                context.workspace_id,
                provider_type,
                display_name,
                _json(config),
                secret_reference,
                enabled,
            ),
        ).fetchone()
        return self._record(row)

    def get(self, context: TenantContext, provider_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT id, provider_type, display_name, config, secret_reference,
                   enabled, revision, created_at, updated_at
              FROM omnix_provider_configs
             WHERE workspace_id = %s AND id = %s
            """,
            (context.workspace_id, provider_id),
        ).fetchone()
        return self._record(row) if row is not None else None

    def update(
        self,
        context: TenantContext,
        *,
        provider_id: str,
        display_name: str,
        config: dict[str, Any],
        secret_reference: str | None,
        enabled: bool,
        expected_revision: int,
    ) -> dict[str, Any]:
        self._reject_secret_values(config)
        row = self.connection.execute(
            """
            UPDATE omnix_provider_configs
               SET display_name = %s, config = %s::jsonb,
                   secret_reference = %s, enabled = %s,
                   revision = revision + 1, updated_at = CURRENT_TIMESTAMP
             WHERE workspace_id = %s AND id = %s AND revision = %s
            RETURNING id, provider_type, display_name, config, secret_reference,
                      enabled, revision, created_at, updated_at
            """,
            (
                display_name,
                _json(config),
                secret_reference,
                enabled,
                context.workspace_id,
                provider_id,
                expected_revision,
            ),
        ).fetchone()
        if row is None:
            raise RevisionConflict(
                f"provider {provider_id} expected revision {expected_revision}"
            )
        return self._record(row)

    def put_status(
        self,
        context: TenantContext,
        *,
        provider_id: str,
        status: dict[str, Any],
        expires_at: str | None = None,
    ) -> dict[str, Any]:
        row = self.connection.execute(
            """
            INSERT INTO omnix_provider_status_projections
                (workspace_id, provider_id, status, expires_at)
            VALUES (%s, %s, %s::jsonb, %s::timestamptz)
            ON CONFLICT (workspace_id, provider_id) DO UPDATE SET
                status = EXCLUDED.status,
                observed_at = CURRENT_TIMESTAMP,
                expires_at = EXCLUDED.expires_at
            RETURNING provider_id, status, observed_at, expires_at
            """,
            (context.workspace_id, provider_id, _json(status), expires_at),
        ).fetchone()
        return {
            "provider_id": str(row[0]),
            "status": dict(row[1]),
            "observed_at": row[2].isoformat(),
            "expires_at": row[3].isoformat() if row[3] is not None else None,
        }

    @staticmethod
    def _reject_secret_values(config: dict[str, Any]) -> None:
        forbidden = {"api_key", "token", "secret", "password", "credential"}
        matches = sorted(forbidden.intersection(str(key).lower() for key in config))
        if matches:
            raise ValueError(
                f"provider config contains secret-bearing keys; use SecretStore reference: {matches}"
            )

    @staticmethod
    def _record(row: Any) -> dict[str, Any]:
        return {
            "id": str(row[0]),
            "provider_type": str(row[1]),
            "display_name": str(row[2]),
            "config": dict(row[3]),
            "secret_reference": str(row[4]) if row[4] is not None else None,
            "enabled": bool(row[5]),
            "revision": int(row[6]),
            "created_at": row[7].isoformat(),
            "updated_at": row[8].isoformat(),
        }


class PostgresPromptRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def create(
        self,
        context: TenantContext,
        *,
        prompt_id: str,
        name: str,
        template_type: str,
        content: str,
        variables: list[str] | None = None,
    ) -> dict[str, Any]:
        row = self.connection.execute(
            """
            INSERT INTO omnix_prompt_templates (
                id, workspace_id, owner_user_id, name, template_type,
                content, variables
            ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING id, name, template_type, content, variables, status,
                      revision, created_at, updated_at
            """,
            (
                prompt_id,
                context.workspace_id,
                context.user_id,
                name,
                template_type,
                content,
                _json(variables or []),
            ),
        ).fetchone()
        return self._record(row)

    def get(self, context: TenantContext, prompt_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT id, name, template_type, content, variables, status,
                   revision, created_at, updated_at
              FROM omnix_prompt_templates
             WHERE workspace_id = %s AND id = %s
            """,
            (context.workspace_id, prompt_id),
        ).fetchone()
        return self._record(row) if row is not None else None

    def update(
        self,
        context: TenantContext,
        *,
        prompt_id: str,
        content: str,
        variables: list[str],
        expected_revision: int,
    ) -> dict[str, Any]:
        row = self.connection.execute(
            """
            UPDATE omnix_prompt_templates
               SET content = %s, variables = %s::jsonb,
                   revision = revision + 1, updated_at = CURRENT_TIMESTAMP
             WHERE workspace_id = %s AND id = %s AND revision = %s
            RETURNING id, name, template_type, content, variables, status,
                      revision, created_at, updated_at
            """,
            (
                content,
                _json(variables),
                context.workspace_id,
                prompt_id,
                expected_revision,
            ),
        ).fetchone()
        if row is None:
            raise RevisionConflict(
                f"prompt {prompt_id} expected revision {expected_revision}"
            )
        return self._record(row)

    @staticmethod
    def _record(row: Any) -> dict[str, Any]:
        return {
            "id": str(row[0]),
            "name": str(row[1]),
            "template_type": str(row[2]),
            "content": str(row[3]),
            "variables": list(row[4]),
            "status": str(row[5]),
            "revision": int(row[6]),
            "created_at": row[7].isoformat(),
            "updated_at": row[8].isoformat(),
        }


class PostgresResearchReportRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def put_research(
        self,
        context: TenantContext,
        *,
        record_id: str,
        research_type: str,
        query_text: str | None,
        result: dict[str, Any],
        source_fingerprint: str | None = None,
        expires_at: str | None = None,
    ) -> dict[str, Any]:
        row = self.connection.execute(
            """
            INSERT INTO omnix_research_records (
                id, workspace_id, owner_user_id, research_type, query_text,
                result_jsonb, source_fingerprint, expires_at
            ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s::timestamptz)
            ON CONFLICT (id) DO UPDATE SET
                result_jsonb = EXCLUDED.result_jsonb,
                source_fingerprint = EXCLUDED.source_fingerprint,
                expires_at = EXCLUDED.expires_at,
                revision = omnix_research_records.revision + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE omnix_research_records.workspace_id = EXCLUDED.workspace_id
            RETURNING id, research_type, query_text, result_jsonb,
                      source_fingerprint, status, expires_at, revision,
                      created_at, updated_at
            """,
            (
                record_id,
                context.workspace_id,
                context.user_id,
                research_type,
                query_text,
                _json(result),
                source_fingerprint,
                expires_at,
            ),
        ).fetchone()
        if row is None:
            raise EntityNotFound(record_id)
        return {
            "id": str(row[0]),
            "research_type": str(row[1]),
            "query_text": str(row[2]) if row[2] is not None else None,
            "result": dict(row[3]),
            "source_fingerprint": str(row[4]) if row[4] is not None else None,
            "status": str(row[5]),
            "expires_at": row[6].isoformat() if row[6] is not None else None,
            "revision": int(row[7]),
            "created_at": row[8].isoformat(),
            "updated_at": row[9].isoformat(),
        }

    def create_report(
        self,
        context: TenantContext,
        *,
        report_id: str,
        report_type: str,
        title: str,
        summary: dict[str, Any],
        blob_asset_id: str | None = None,
        generated_by_job_id: str | None = None,
    ) -> dict[str, Any]:
        row = self.connection.execute(
            """
            INSERT INTO omnix_reports (
                id, workspace_id, owner_user_id, report_type, title,
                summary, blob_asset_id, generated_by_job_id
            ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)
            RETURNING id, report_type, title, status, summary, blob_asset_id,
                      generated_by_job_id, revision, created_at, updated_at
            """,
            (
                report_id,
                context.workspace_id,
                context.user_id,
                report_type,
                title,
                _json(summary),
                blob_asset_id,
                generated_by_job_id,
            ),
        ).fetchone()
        return {
            "id": str(row[0]),
            "report_type": str(row[1]),
            "title": str(row[2]),
            "status": str(row[3]),
            "summary": dict(row[4]),
            "blob_asset_id": str(row[5]) if row[5] is not None else None,
            "generated_by_job_id": str(row[6]) if row[6] is not None else None,
            "revision": int(row[7]),
            "created_at": row[8].isoformat(),
            "updated_at": row[9].isoformat(),
        }
