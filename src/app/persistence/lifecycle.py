from __future__ import annotations

import json
from typing import Any


class PostgresLifecycleRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def capacity_report(self) -> dict[str, Any]:
        row = self.connection.execute(
            """
            SELECT
                pg_database_size(current_database()),
                (SELECT COUNT(*) FROM omnix_outbox_events),
                (SELECT COUNT(*) FROM omnix_outbox_consumer_inbox),
                (SELECT COUNT(*) FROM omnix_outbox_dead_letters),
                (SELECT COUNT(*) FROM omnix_job_events),
                (SELECT COUNT(*) FROM omnix_audit_events),
                (SELECT COUNT(*) FROM omnix_rpg_turns),
                (SELECT COALESCE(MAX(pg_column_size(payload)), 0) FROM omnix_outbox_events)
            """
        ).fetchone()
        policy = self.connection.execute(
            """
            SELECT max_outbox_payload_bytes, max_jsonb_record_bytes,
                   disk_warning_percent, disk_hard_stop_percent, cleanup_batch_size
              FROM omnix_capacity_policy WHERE singleton = TRUE
            """
        ).fetchone()
        return {
            "database_bytes": int(row[0]),
            "counts": {
                "outbox_events": int(row[1]),
                "outbox_consumer_inbox": int(row[2]),
                "outbox_dead_letters": int(row[3]),
                "job_events": int(row[4]),
                "audit_events": int(row[5]),
                "rpg_turns": int(row[6]),
            },
            "max_outbox_payload_bytes_observed": int(row[7]),
            "policy": {
                "max_outbox_payload_bytes": int(policy[0]),
                "max_jsonb_record_bytes": int(policy[1]),
                "disk_warning_percent": int(policy[2]),
                "disk_hard_stop_percent": int(policy[3]),
                "cleanup_batch_size": int(policy[4]),
            },
        }

    def cleanup(self, *, batch_size: int | None = None) -> dict[str, Any]:
        before = self.capacity_report()
        resolved_batch = max(
            1,
            min(
                int(batch_size or before["policy"]["cleanup_batch_size"]),
                100_000,
            ),
        )
        run_id = int(
            self.connection.execute(
                """
                INSERT INTO omnix_lifecycle_cleanup_runs (
                    status, capacity_before
                ) VALUES ('running', %s::jsonb)
                RETURNING id
                """,
                (json.dumps(before, sort_keys=True, separators=(",", ":")),),
            ).fetchone()[0]
        )
        deleted: dict[str, int] = {}
        try:
            deleted["consumer_inbox"] = self._delete_with_policy(
                record_type="outbox_consumer_inbox",
                sql="""
                    DELETE FROM omnix_outbox_consumer_inbox
                     WHERE (consumer_id, event_key) IN (
                         SELECT consumer_id, event_key
                           FROM omnix_outbox_consumer_inbox
                          WHERE status IN ('completed', 'dead_letter')
                            AND updated_at < CURRENT_TIMESTAMP - (%s * INTERVAL '1 day')
                          ORDER BY updated_at, consumer_id, event_key
                          LIMIT %s
                     )
                """,
                batch_size=resolved_batch,
            )
            deleted["outbox_events"] = self._delete_with_policy(
                record_type="outbox_events",
                sql="""
                    DELETE FROM omnix_outbox_events
                     WHERE id IN (
                         SELECT id
                           FROM omnix_outbox_events
                          WHERE status = 'published'
                            AND published_at < CURRENT_TIMESTAMP - (%s * INTERVAL '1 day')
                            AND NOT EXISTS (
                                SELECT 1 FROM omnix_outbox_consumer_inbox AS inbox
                                 WHERE inbox.event_key = omnix_outbox_events.event_key
                            )
                          ORDER BY published_at, id
                          LIMIT %s
                     )
                """,
                batch_size=resolved_batch,
            )
            deleted["dead_letters"] = self._delete_with_policy(
                record_type="outbox_dead_letters",
                sql="""
                    DELETE FROM omnix_outbox_dead_letters
                     WHERE id IN (
                         SELECT id
                           FROM omnix_outbox_dead_letters
                          WHERE resolved_at IS NOT NULL
                            AND resolved_at < CURRENT_TIMESTAMP - (%s * INTERVAL '1 day')
                          ORDER BY resolved_at, id
                          LIMIT %s
                     )
                """,
                batch_size=resolved_batch,
            )
            deleted["runtime_failure_evidence"] = self._delete_with_policy(
                record_type="runtime_failure_evidence",
                sql="""
                    DELETE FROM omnix_runtime_failure_evidence
                     WHERE id IN (
                         SELECT id
                           FROM omnix_runtime_failure_evidence
                          WHERE created_at < CURRENT_TIMESTAMP - (%s * INTERVAL '1 day')
                          ORDER BY created_at, id
                          LIMIT %s
                     )
                """,
                batch_size=resolved_batch,
            )
            after = self.capacity_report()
            self.connection.execute(
                """
                UPDATE omnix_lifecycle_cleanup_runs
                   SET status = 'completed', completed_at = CURRENT_TIMESTAMP,
                       deleted_counts = %s::jsonb, capacity_after = %s::jsonb
                 WHERE id = %s
                """,
                (
                    json.dumps(deleted, sort_keys=True, separators=(",", ":")),
                    json.dumps(after, sort_keys=True, separators=(",", ":")),
                    run_id,
                ),
            )
            return {"ok": True, "run_id": run_id, "deleted": deleted, "before": before, "after": after}
        except Exception as exc:
            self.connection.execute(
                """
                UPDATE omnix_lifecycle_cleanup_runs
                   SET status = 'failed', completed_at = CURRENT_TIMESTAMP,
                       error = %s
                 WHERE id = %s
                """,
                (f"{exc.__class__.__name__}: {exc}"[:2000], run_id),
            )
            raise

    def _delete_with_policy(self, *, record_type: str, sql: str, batch_size: int) -> int:
        policy = self.connection.execute(
            "SELECT retention_days, enabled FROM omnix_retention_policies WHERE record_type = %s",
            (record_type,),
        ).fetchone()
        if policy is None or not bool(policy[1]):
            return 0
        cursor = self.connection.execute(sql, (int(policy[0]), batch_size))
        return int(cursor.rowcount)
