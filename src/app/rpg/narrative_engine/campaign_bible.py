"""Campaign Bible aggregate contracts and evidence projection."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence, TypeVar

from .authority import AuthorityClass, EvidenceLifetime, VisibilityClass
from .contracts import EvidenceRecord
from .evidence import EvidenceQuery


_EnumT = TypeVar("_EnumT")


def _enum(enum_type: type[_EnumT], value: Any, default: _EnumT) -> _EnumT:
    try:
        return enum_type(str(value))
    except (TypeError, ValueError):
        return default


def _visibility(value: Any) -> VisibilityClass:
    normalized = str(value or "public").strip().casefold()
    aliases = {
        "public": VisibilityClass.PUBLIC,
        "player_known": VisibilityClass.PLAYER_KNOWN,
        "learned": VisibilityClass.PLAYER_KNOWN,
        "partially_known": VisibilityClass.PLAYER_KNOWN,
        "disputed": VisibilityClass.PLAYER_KNOWN,
        "npc_private": VisibilityClass.NPC_PRIVATE,
        "faction_private": VisibilityClass.FACTION_PRIVATE,
        "narrator_only": VisibilityClass.NARRATOR_ONLY,
        "hidden_from_player": VisibilityClass.GAME_MASTER_ONLY,
        "game_master_canon": VisibilityClass.GAME_MASTER_ONLY,
        "game_master_only": VisibilityClass.GAME_MASTER_ONLY,
    }
    return aliases.get(normalized, VisibilityClass.GAME_MASTER_ONLY)


def _strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list | tuple | set):
        return ()
    return tuple(str(item) for item in value if str(item).strip())


@dataclass(frozen=True)
class CampaignBibleSnapshot:
    campaign_id: str
    revision: int
    content_hash: str
    document: Mapping[str, Any]
    provenance: Mapping[str, Any]
    consistency_report: Mapping[str, Any]
    completeness: Mapping[str, Any]

    @classmethod
    def from_record(cls, value: Mapping[str, Any]) -> "CampaignBibleSnapshot":
        return cls(
            campaign_id=str(value.get("campaign_id") or ""),
            revision=int(value.get("revision") or 0),
            content_hash=str(value.get("content_hash") or ""),
            document=dict(value.get("document") or {}),
            provenance=dict(value.get("provenance") or {}),
            consistency_report=dict(value.get("consistency_report") or {}),
            completeness=dict(value.get("completeness") or {}),
        )


def campaign_bible_evidence(snapshot: CampaignBibleSnapshot) -> tuple[EvidenceRecord, ...]:
    raw_records: list[Mapping[str, Any]] = []
    for key in ("facts", "relationships", "retrieval_cards", "knowledge_rules"):
        value = snapshot.document.get(key)
        if isinstance(value, list):
            raw_records.extend(item for item in value if isinstance(item, Mapping))

    records: list[EvidenceRecord] = []
    for index, raw in enumerate(raw_records, start=1):
        content = str(
            raw.get("content")
            or raw.get("summary")
            or raw.get("statement")
            or ""
        ).strip()
        if not content:
            continue
        evidence_id = str(
            raw.get("evidence_id")
            or raw.get("id")
            or f"bible:{snapshot.campaign_id}:{index}"
        )
        records.append(
            EvidenceRecord(
                evidence_id=evidence_id,
                content=content,
                authority=_enum(
                    AuthorityClass,
                    raw.get("authority"),
                    AuthorityClass.OBJECTIVE_CANON,
                ),
                visibility=_visibility(raw.get("visibility")),
                known_by=_strings(raw.get("known_by")),
                entity_refs=_strings(
                    raw.get("entity_refs") or raw.get("entities")
                ),
                source_revision=snapshot.revision,
                confidence=max(
                    0.0,
                    min(float(raw.get("confidence") or 1.0), 1.0),
                ),
                lifetime=_enum(
                    EvidenceLifetime,
                    raw.get("lifetime"),
                    EvidenceLifetime.CAMPAIGN,
                ),
                claim_refs=_strings(raw.get("claim_refs")),
                metadata={
                    "source": "postgresql_campaign_bible",
                    "campaign_id": snapshot.campaign_id,
                    "campaign_bible_hash": snapshot.content_hash,
                    "category": str(raw.get("category") or "fact"),
                    "document_id": str(raw.get("document_id") or ""),
                    "title": str(raw.get("title") or ""),
                    "fact_id": str(raw.get("fact_id") or ""),
                    "keywords": list(raw.get("keywords") or ()),
                    "canon_revision": int(
                        raw.get("canon_revision") or snapshot.revision
                    ),
                },
            )
        )
    return tuple(records)


class CampaignBibleEvidenceSource:
    source_id = "postgresql_campaign_bible"

    def __init__(self, snapshot: CampaignBibleSnapshot) -> None:
        self.snapshot = snapshot
        self._records = campaign_bible_evidence(snapshot)

    def records(self, query: EvidenceQuery) -> Sequence[EvidenceRecord]:
        return self._records
