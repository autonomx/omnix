from __future__ import annotations

import os

import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.errors import RevisionConflict
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.migrations import apply_migrations
from app.persistence.unit_of_work import unit_of_work


pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


def _database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=6,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-module-tests",
        )
    )


def _reset(database: PostgresDatabase) -> None:
    apply_migrations(database)
    with database.transaction() as connection:
        connection.execute(
            "TRUNCATE omnix_runtime_projections, omnix_module_records, "
            "omnix_reports, omnix_research_records, omnix_prompt_templates, "
            "omnix_provider_status_projections, omnix_provider_configs, "
            "omnix_rpg_participants, omnix_rpg_snapshots, omnix_rpg_interactions, "
            "omnix_rpg_turns, omnix_rpg_campaigns, "
            "omnix_rpg_foreground_submissions, omnix_outbox_events, "
            "omnix_dead_letters, omnix_job_events, omnix_job_attempts, omnix_jobs, "
            "omnix_chat_messages, omnix_chat_sessions, omnix_memory_snapshot_items, "
            "omnix_memory_snapshots, omnix_memory_candidates, omnix_memory_events, "
            "omnix_memory_records, omnix_conversation_segments, "
            "omnix_character_versions, omnix_characters, omnix_asset_versions, "
            "omnix_assets, omnix_settings, omnix_secret_references, "
            "omnix_audit_events, omnix_idempotency_keys, "
            "omnix_workspace_memberships, omnix_workspaces, omnix_users CASCADE"
        )


def test_generic_module_records_are_revisioned_and_expiry_aware() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            created = work.module_records.put(
                context,
                module="rpg",
                record_type="npc-evolution-profile",
                record_id="npc:bran",
                payload={"trust": 4},
            )
            updated = work.module_records.put(
                context,
                module="rpg",
                record_type="npc-evolution-profile",
                record_id="npc:bran",
                payload={"trust": 5},
                expected_revision=created["revision"],
            )
            expiring = work.module_records.put(
                context,
                module="research",
                record_type="cache-entry",
                record_id="expired",
                payload={"value": 1},
                expires_at="2000-01-01T00:00:00+00:00",
            )
            work.commit()
        assert updated["revision"] == 2
        assert expiring["revision"] == 1
        with unit_of_work(database) as work:
            assert work.module_records.get(
                context,
                module="research",
                record_type="cache-entry",
                record_id="expired",
            ) is None
            included = work.module_records.get(
                context,
                module="research",
                record_type="cache-entry",
                record_id="expired",
                include_expired=True,
            )
            with pytest.raises(RevisionConflict):
                work.module_records.put(
                    context,
                    module="rpg",
                    record_type="npc-evolution-profile",
                    record_id="npc:bran",
                    payload={"trust": 6},
                    expected_revision=1,
                )
            work.rollback()
        assert included is not None
    finally:
        database.close()


def test_provider_configs_use_secret_references_and_expiring_status() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            secret = work.secret_references.register(
                context,
                reference="secret:openai",
                provider="os-credential-store",
                purpose="provider-api-key",
            )
            provider = work.providers.create(
                context,
                provider_id="provider:openai-compatible",
                provider_type="openai-compatible",
                display_name="Local OpenAI Compatible",
                config={"base_url": "http://127.0.0.1:1234/v1", "model": "local"},
                secret_reference=secret["reference"],
            )
            status = work.providers.put_status(
                context,
                provider_id=provider["id"],
                status={"reachable": True, "models": 1},
                expires_at="2999-01-01T00:00:00+00:00",
            )
            work.commit()
        assert provider["secret_reference"] == "secret:openai"
        assert status["status"]["reachable"] is True

        with unit_of_work(database) as work:
            with pytest.raises(ValueError, match="SecretStore"):
                work.providers.create(
                    context,
                    provider_id="provider:unsafe",
                    provider_type="unsafe",
                    display_name="Unsafe",
                    config={"api_key": "must-not-store"},
                )
            changed = work.providers.update(
                context,
                provider_id=provider["id"],
                display_name="Updated Local Provider",
                config={"base_url": "http://127.0.0.1:1234/v1", "model": "local-v2"},
                secret_reference=secret["reference"],
                enabled=True,
                expected_revision=1,
            )
            work.commit()
        assert changed["revision"] == 2
        with database.connection() as connection:
            encoded = connection.execute(
                "SELECT config::text FROM omnix_provider_configs "
                "WHERE id = 'provider:openai-compatible'"
            ).fetchone()[0]
        assert "must-not-store" not in encoded
    finally:
        database.close()


def test_prompt_templates_are_tenant_scoped_and_revisioned() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            prompt = work.prompts.create(
                context,
                prompt_id="prompt:rpg-narration",
                name="RPG narration",
                template_type="system",
                content="Narrate {{event}} without changing simulation truth.",
                variables=["event"],
            )
            updated = work.prompts.update(
                context,
                prompt_id=prompt["id"],
                content="Present {{event}} without inventing state.",
                variables=["event"],
                expected_revision=1,
            )
            work.commit()
        assert updated["revision"] == 2
        with unit_of_work(database) as work:
            with pytest.raises(RevisionConflict):
                work.prompts.update(
                    context,
                    prompt_id=prompt["id"],
                    content="stale",
                    variables=[],
                    expected_revision=1,
                )
            work.rollback()
    finally:
        database.close()


def test_research_reports_and_runtime_projections_are_durable_or_rebuildable() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        with unit_of_work(database) as work:
            asset = work.assets.create(
                context,
                {
                    "id": "asset:report",
                    "module": "reports",
                    "asset_type": "report",
                    "mime_type": "application/json",
                    "byte_size": 2,
                    "checksum_sha256": "0" * 64,
                    "storage_provider": "local-filesystem",
                    "storage_key": "reports/report.json",
                },
            )
            job = work.jobs.create_job(
                context,
                {
                    "id": "job:report",
                    "module": "reports",
                    "job_type": "report.generate",
                    "resource_class": "cpu",
                },
            )
            research = work.research_reports.put_research(
                context,
                record_id="research:1",
                research_type="web",
                query_text="centralized persistence",
                result={"citations": 3},
                source_fingerprint="sha256:source",
            )
            research_updated = work.research_reports.put_research(
                context,
                record_id="research:1",
                research_type="web",
                query_text="centralized persistence",
                result={"citations": 4},
                source_fingerprint="sha256:source-v2",
            )
            report = work.research_reports.create_report(
                context,
                report_id="report:1",
                report_type="architecture",
                title="Persistence report",
                summary={"decision": "postgresql"},
                blob_asset_id=asset["id"],
                generated_by_job_id=job["id"],
            )
            projection = work.projections.put(
                context,
                projection_type="provider-health",
                projection_key="provider:local",
                payload={"reachable": True},
                source_revision=2,
                expires_at="2999-01-01T00:00:00+00:00",
            )
            work.commit()
        assert research["revision"] == 1
        assert research_updated["revision"] == 2
        assert report["blob_asset_id"] == "asset:report"
        assert report["generated_by_job_id"] == "job:report"
        assert projection["source_revision"] == 2
        with unit_of_work(database) as work:
            loaded = work.projections.get(
                context,
                projection_type="provider-health",
                projection_key="provider:local",
            )
            work.rollback()
        assert loaded is not None and loaded["payload"] == {"reachable": True}
    finally:
        database.close()


def test_remaining_module_writes_share_unit_of_work_rollback() -> None:
    database = _database()
    try:
        _reset(database)
        context = bootstrap_local_tenant(database)
        with pytest.raises(RuntimeError, match="rollback modules"):
            with unit_of_work(database) as work:
                work.module_records.put(
                    context,
                    module="live-chat",
                    record_type="evaluation",
                    record_id="eval:1",
                    payload={"score": 1.0},
                )
                work.prompts.create(
                    context,
                    prompt_id="prompt:rollback",
                    name="Rollback",
                    template_type="system",
                    content="rollback",
                )
                raise RuntimeError("rollback modules")
        with unit_of_work(database) as work:
            assert work.module_records.get(
                context,
                module="live-chat",
                record_type="evaluation",
                record_id="eval:1",
            ) is None
            assert work.prompts.get(context, "prompt:rollback") is None
            work.rollback()
    finally:
        database.close()
