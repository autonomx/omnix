from __future__ import annotations

import json
from typing import Any


class CutoverTransitionError(RuntimeError):
    pass


_ALLOWED_TRANSITIONS = {
    "legacy_preflight": {"imported_unverified", "rollback_recorded"},
    "imported_unverified": {"imported_verified", "rollback_recorded"},
    "imported_verified": {"postgresql_activated_frozen", "rollback_recorded"},
    "postgresql_activated_frozen": {"postgresql_open_for_writes", "rollback_recorded"},
    "postgresql_open_for_writes": {"postgresql_stabilized", "rollback_recorded"},
    "postgresql_stabilized": {"rollback_recorded"},
    "rollback_recorded": set(),
}


class PostgresCutoverStateRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def current(self, *, for_update: bool = False) -> dict[str, Any]:
        suffix = " FOR UPDATE" if for_update else ""
        row = self.connection.execute(
            """
            SELECT mode, authority_state, import_run_id, source_hash,
                   backup_generation_id, activated_at, opened_for_writes_at,
                   stabilized_at, rollback_recorded_at,
                   latest_authoritative_revision, destructive_override_at,
                   metadata
              FROM omnix_persistence_cutover
             WHERE singleton = TRUE
            """ + suffix
        ).fetchone()
        if row is None:
            raise CutoverTransitionError("cutover singleton is missing")
        return {
            "mode": str(row[0]),
            "authority_state": str(row[1]),
            "import_run_id": str(row[2]) if row[2] is not None else None,
            "source_hash": str(row[3]) if row[3] is not None else None,
            "backup_generation_id": str(row[4]) if row[4] is not None else None,
            "activated_at": row[5].isoformat() if row[5] is not None else None,
            "opened_for_writes_at": row[6].isoformat() if row[6] is not None else None,
            "stabilized_at": row[7].isoformat() if row[7] is not None else None,
            "rollback_recorded_at": row[8].isoformat() if row[8] is not None else None,
            "latest_authoritative_revision": str(row[9]) if row[9] is not None else None,
            "destructive_override_at": row[10].isoformat() if row[10] is not None else None,
            "metadata": dict(row[11]),
        }

    def transition(
        self,
        *,
        to_state: str,
        software_revision: str,
        schema_version: str,
        import_run_id: str | None = None,
        backup_generation_id: str | None = None,
        latest_authoritative_revision: str | None = None,
        operator_note: str | None = None,
        write_reopen_acknowledged: bool = False,
        destructive_acknowledgement: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        current = self.current(for_update=True)
        from_state = current["authority_state"]
        if to_state not in _ALLOWED_TRANSITIONS.get(from_state, set()):
            raise CutoverTransitionError(f"invalid cutover transition: {from_state} -> {to_state}")
        if to_state == "imported_verified":
            run_id = import_run_id or current["import_run_id"]
            row = self.connection.execute(
                "SELECT status, verification FROM omnix_legacy_import_runs WHERE id = %s",
                (run_id,),
            ).fetchone()
            if row is None or str(row[0]) != "completed" or not bool(dict(row[1]).get("ok")):
                raise CutoverTransitionError("imported_verified requires a clean completed import")
        if to_state == "postgresql_activated_frozen":
            generation_id = backup_generation_id or current["backup_generation_id"]
            row = self.connection.execute(
                "SELECT status FROM omnix_backup_generations WHERE id = %s",
                (generation_id,),
            ).fetchone()
            if row is None or str(row[0]) != "verified":
                raise CutoverTransitionError("authority activation requires a verified recovery generation")
        if to_state == "postgresql_open_for_writes" and not write_reopen_acknowledged:
            raise CutoverTransitionError(
                "opening writes requires acknowledgement that legacy rollback is no longer lossless"
            )
        if to_state == "rollback_recorded" and from_state in {
            "postgresql_open_for_writes",
            "postgresql_stabilized",
        } and not destructive_acknowledgement:
            raise CutoverTransitionError(
                "legacy rollback after PostgreSQL writes requires destructive acknowledgement"
            )

        mode = "postgresql" if to_state.startswith("postgresql_") else (
            "rollback_recorded" if to_state == "rollback_recorded" else "legacy_preflight"
        )
        resolved_import = import_run_id or current["import_run_id"]
        resolved_backup = backup_generation_id or current["backup_generation_id"]
        payload = metadata or {}
        row = self.connection.execute(
            """
            UPDATE omnix_persistence_cutover
               SET mode = %s,
                   authority_state = %s,
                   import_run_id = COALESCE(%s, import_run_id),
                   backup_generation_id = COALESCE(%s, backup_generation_id),
                   activated_at = CASE WHEN %s = 'postgresql_activated_frozen'
                                       THEN CURRENT_TIMESTAMP ELSE activated_at END,
                   opened_for_writes_at = CASE WHEN %s = 'postgresql_open_for_writes'
                                               THEN CURRENT_TIMESTAMP ELSE opened_for_writes_at END,
                   stabilized_at = CASE WHEN %s = 'postgresql_stabilized'
                                        THEN CURRENT_TIMESTAMP ELSE stabilized_at END,
                   rollback_recorded_at = CASE WHEN %s = 'rollback_recorded'
                                               THEN CURRENT_TIMESTAMP ELSE rollback_recorded_at END,
                   destructive_override_at = CASE WHEN %s THEN CURRENT_TIMESTAMP
                                                  ELSE destructive_override_at END,
                   latest_authoritative_revision = COALESCE(%s, latest_authoritative_revision),
                   updated_at = CURRENT_TIMESTAMP,
                   metadata = metadata || %s::jsonb
             WHERE singleton = TRUE
            RETURNING mode, authority_state, import_run_id, source_hash,
                      backup_generation_id, activated_at, opened_for_writes_at,
                      stabilized_at, rollback_recorded_at,
                      latest_authoritative_revision, destructive_override_at,
                      metadata
            """,
            (
                mode,
                to_state,
                resolved_import,
                resolved_backup,
                to_state,
                to_state,
                to_state,
                to_state,
                destructive_acknowledgement,
                latest_authoritative_revision,
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
            ),
        ).fetchone()
        self.connection.execute(
            """
            INSERT INTO omnix_cutover_transitions (
                from_state, to_state, import_run_id, backup_generation_id,
                software_revision, schema_version, operator_note,
                destructive_acknowledgement, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                from_state,
                to_state,
                resolved_import,
                resolved_backup,
                software_revision,
                schema_version,
                (operator_note or "")[:2000] or None,
                destructive_acknowledgement,
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
            ),
        )
        return {
            "mode": str(row[0]),
            "authority_state": str(row[1]),
            "import_run_id": str(row[2]) if row[2] is not None else None,
            "backup_generation_id": str(row[4]) if row[4] is not None else None,
            "latest_authoritative_revision": str(row[9]) if row[9] is not None else None,
            "metadata": dict(row[11]),
        }
