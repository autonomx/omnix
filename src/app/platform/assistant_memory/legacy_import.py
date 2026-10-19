"""Restoring a legacy curated memory record into Memory v2 (WP-8.5).

It lives outside ``declarations.py``, which may import only kernel modules
(PA-2.2): the declaration names it with ``deferred_restore``, so this module
loads only when a legacy import runs.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.conversation.memory_contracts import MemoryRecord
from app.platform.assistant_memory.v2.curated_records import PostgresMemoryV2CuratedRecords


_SCOPES = {"global", "workspace", "project", "session"}
_CATEGORIES = {"preference", "fact", "project", "relationship", "instruction"}
_SOURCES = {"user_saved", "assistant_suggested", "imported", "hermes"}
_TRUST = {"user_approved", "system_trusted", "unverified_import", "unverified_agent", "external_untrusted"}


def _choice(value: Any, allowed: set[str], default: str) -> Any:
    return value if value in allowed else default


def restore_memory_record(work: Any, context: Any, stable_id: str, item: dict[str, Any]) -> None:
    """A legacy curated memory record, into Memory v2 (WP-8.5).

    Memory v1 is retired, so the record becomes a v2 curated record of the
    tenant workspace; a resumed import returns the same record (idempotency
    key). Pre-owner records (owned by a scope) belong to the System Assistant
    in that scope. A trust level the current contract does not know is an
    unverified import, which needs approval before it reaches a prompt. The
    scheduler's convergence task derives and indexes it.
    """
    owner_type = str(item.get("owner_type") or "system")
    owned = owner_type in {"system", "character"}
    scope = str(item.get("scope") or (owner_type if owner_type in _SCOPES else "workspace"))
    scope_id = str(item.get("scope_id") or (item.get("owner_id") if owner_type in _SCOPES else context.workspace_id))
    content = str(item["content"]).strip()
    now = datetime.now(timezone.utc).isoformat()
    record = MemoryRecord(
        id=stable_id,
        owner_type="character" if owner_type == "character" else "system",
        owner_id=str(item.get("owner_id")) if owned and item.get("owner_id") else "system-assistant",
        scope=_choice(scope, _SCOPES, "workspace"),
        scope_id=scope_id,
        category=_choice(item.get("category"), _CATEGORIES, "fact"),
        source=_choice(item.get("source"), _SOURCES, "imported"),
        content=content,
        normalized_content=str(item.get("normalized_content") or content.lower()),
        confidence=float(item.get("confidence", 1.0)),
        pinned=bool(item.get("pinned", False)),
        trust_level=_choice(item.get("trust_level"), _TRUST, "unverified_import"),
        sensitivity=_choice(item.get("sensitivity"), {"normal", "sensitive", "secret"}, "normal"),
        provenance_type="import",
        provenance_id=str(item.get("provenance_id") or f"legacy:{stable_id}")[:240],
        status=_choice(item.get("status"), {"active", "superseded", "archived"}, "active"),
        created_at=str(item.get("created_at") or now),
        updated_at=str(item.get("updated_at") or item.get("created_at") or now),
        expires_at=item.get("expires_at"),
    )
    PostgresMemoryV2CuratedRecords(work.database).create(
        context.workspace_id, record, idempotency_key=f"legacy-import:{stable_id}",
    )
