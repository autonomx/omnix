"""What each speaker may use: the System Assistant and every character, ability by ability.

Owner decision 2026-11-07: an ability is granted by the person, never inferred from the model or a story. Read-only
lookups (web search) are on for the System Assistant and off for a character until turned on for it; actions (lights,
calendar, email) are the assistant's, unless one group is given to a character explicitly. A character in role-play
reads "blow up the lights" as a line, so real-world actions stay out of its reach unless granted.

The model only proposes a use; ``authorize`` decides, from the grant and the ability's kind. A lookup runs when
granted. An action, once there are actions, also needs the person's confirmation (``confirm``).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from app.persistence.document_schemas import register_document_schema
from app.persistence.document_store import PostgresDocumentStore

SYSTEM_OWNER_ID = "system-assistant"
AbilityKind = Literal["lookup", "action"]


class Ability(BaseModel):
    id: str
    label: str
    kind: AbilityKind
    default_system: bool
    default_character: bool


ABILITIES: dict[str, Ability] = {
    "web_search": Ability(
        id="web_search", label="Look things up on the web", kind="lookup", default_system=True,
        default_character=False,
    ),
}


class OwnerGrantsDocument(BaseModel):
    """The ``assistant-tools/owner-grants`` document: per owner (a character id or the System Assistant), the
    abilities set by the person. An ability not set follows its default."""

    owners: dict[str, dict[str, bool]] = Field(default_factory=dict)


register_document_schema("assistant-tools", "owner-grants", OwnerGrantsDocument)


@dataclass(frozen=True)
class Decision:
    allowed: bool
    confirm: bool = False
    reason: str = ""


def _default(owner_id: str, ability: Ability) -> bool:
    return ability.default_system if owner_id == SYSTEM_OWNER_ID else ability.default_character


def _stored() -> OwnerGrantsDocument:
    payload = PostgresDocumentStore().read(module="assistant-tools", record_type="owner-grants", default=None)
    return OwnerGrantsDocument.model_validate(payload or {})


def owner_grants(owner_id: str) -> dict[str, bool]:
    """Every ability and whether this owner has it: what the person set, else the ability's default."""
    stored = _stored().owners.get(owner_id, {})
    return {ability_id: bool(stored.get(ability_id, _default(owner_id, ability)))
            for ability_id, ability in ABILITIES.items()}


def set_owner_grant(owner_id: str, ability_id: str, allowed: bool) -> dict[str, bool]:
    if ability_id not in ABILITIES:
        raise KeyError(ability_id)
    documents = PostgresDocumentStore()
    with documents.lock(module="assistant-tools", record_type="owner-grants") as lock:
        document = OwnerGrantsDocument.model_validate(lock.read(default=None) or {})
        document.owners.setdefault(owner_id, {})[ability_id] = bool(allowed)
        lock.write(document.model_dump(mode="json"))
    return owner_grants(owner_id)


def authorize(owner_id: str, ability_id: str, *, grants: dict[str, bool] | None = None) -> Decision:
    """Whether the owner may use an ability now. The model's proposal never decides this."""
    ability = ABILITIES.get(ability_id)
    if ability is None:
        return Decision(False, reason="unknown_ability")
    granted = (grants if grants is not None else owner_grants(owner_id)).get(ability_id, False)
    if not granted:
        return Decision(False, reason="not_granted")
    return Decision(True, confirm=ability.kind == "action", reason="granted")


__all__ = [
    "ABILITIES", "Ability", "Decision", "OwnerGrantsDocument", "SYSTEM_OWNER_ID", "authorize", "owner_grants",
    "set_owner_grant",
]
