"""PostgreSQL authority for Assist Core house state."""
from __future__ import annotations

from typing import Any

from app.persistence.document_store import PostgresDocumentStore


def load_house_state_postgres() -> dict[str, Any]:
    from app.assist_core.house_state import DEFAULT_HOUSE_STATE

    payload = PostgresDocumentStore().read(
        module="assist-core",
        record_type="house-state",
        default=DEFAULT_HOUSE_STATE,
    )
    return dict(payload) if isinstance(payload, dict) else dict(DEFAULT_HOUSE_STATE)


def save_house_state_postgres(payload: dict[str, Any]) -> None:
    PostgresDocumentStore().write(
        dict(payload),
        module="assist-core",
        record_type="house-state",
    )
