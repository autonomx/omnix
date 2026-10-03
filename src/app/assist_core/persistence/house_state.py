"""PostgreSQL authority for Assist Core house state."""
from __future__ import annotations

from typing import Any

from app.persistence.document_store import PostgresDocumentStore
from pydantic import BaseModel, ConfigDict, Field

from app.assist_core.core import ActionLogEntry, ConfirmationRequest
from app.persistence.document_schemas import register_document_schema


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


class HouseStateDocument(BaseModel):
    """The ``assist-core/house-state`` document."""

    model_config = ConfigDict(extra="allow")

    rooms: dict[str, dict[str, Any]] = Field(default_factory=dict)
    thermostat: dict[str, Any] = Field(default_factory=dict)
    reminders: list[Any] = Field(default_factory=list)


# Document shapes (WP-5.9).
register_document_schema("assist-core", "house-state", HouseStateDocument)
register_document_schema("assist-core", "pending-reviews", dict[str, ConfirmationRequest])
register_document_schema("assist-core", "action-log", ActionLogEntry)
