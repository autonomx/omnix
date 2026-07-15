"""Deterministic World Forge proposal, cross-linking, and approval pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .campaign_bible import CampaignBibleSnapshot
from .contracts import stable_hash


@dataclass(frozen=True)
class WorldForgeIssue:
    code: str
    message: str
    item_id: str = ""
    severity: str = "error"

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "item_id": self.item_id,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class WorldForgeAudit:
    passed: bool
    issues: tuple[WorldForgeIssue, ...] = ()
    cross_links: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "issues": [issue.as_dict() for issue in self.issues],
            "cross_links": {
                key: list(value) for key, value in sorted(self.cross_links.items())
            },
        }


@dataclass(frozen=True)
class WorldForgeProposal:
    proposal_id: str
    campaign_id: str
    base_bible_revision: int
    entities: tuple[Mapping[str, Any], ...] = ()
    facts: tuple[Mapping[str, Any], ...] = ()
    relationships: tuple[Mapping[str, Any], ...] = ()
    retrieval_cards: tuple[Mapping[str, Any], ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "WorldForgeProposal":
        def rows(key: str) -> tuple[Mapping[str, Any], ...]:
            raw = value.get(key)
            return tuple(dict(row) for row in raw if isinstance(row, Mapping)) if isinstance(raw, list | tuple) else ()

        return cls(
            proposal_id=str(value.get("proposal_id") or ""),
            campaign_id=str(value.get("campaign_id") or ""),
            base_bible_revision=int(value.get("base_bible_revision") or 0),
            entities=rows("entities"),
            facts=rows("facts"),
            relationships=rows("relationships"),
            retrieval_cards=rows("retrieval_cards"),
            provenance=dict(value.get("provenance") or {}),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "campaign_id": self.campaign_id,
            "base_bible_revision": self.base_bible_revision,
            "entities": [dict(row) for row in self.entities],
            "facts": [dict(row) for row in self.facts],
            "relationships": [dict(row) for row in self.relationships],
            "retrieval_cards": [dict(row) for row in self.retrieval_cards],
            "provenance": dict(self.provenance),
        }

    @property
    def proposal_hash(self) -> str:
        return stable_hash(self.as_dict())


def _item_id(row: Mapping[str, Any], prefix: str, index: int) -> str:
    return str(row.get("id") or row.get("evidence_id") or f"{prefix}:{index}")


def _entity_ids(document: Mapping[str, Any]) -> set[str]:
    raw = document.get("entities")
    if isinstance(raw, Mapping):
        return {str(key) for key in raw}
    if isinstance(raw, list | tuple):
        return {
            str(row.get("id"))
            for row in raw
            if isinstance(row, Mapping) and row.get("id")
        }
    return set()


def _fact_identity(row: Mapping[str, Any], prefix: str, index: int) -> str:
    explicit = str(row.get("id") or row.get("evidence_id") or "").strip()
    if explicit:
        return explicit
    subject = str(row.get("subject") or "").strip()
    predicate = str(row.get("predicate") or "").strip()
    return f"{prefix}:{subject}:{predicate}" if subject and predicate else f"{prefix}:{index}"


def _meaning(row: Mapping[str, Any]) -> str:
    return str(
        row.get("object")
        or row.get("content")
        or row.get("statement")
        or row.get("summary")
        or ""
    ).strip().casefold()


def audit_world_forge_proposal(
    snapshot: CampaignBibleSnapshot,
    proposal: WorldForgeProposal,
) -> WorldForgeAudit:
    issues: list[WorldForgeIssue] = []
    if proposal.campaign_id != snapshot.campaign_id:
        issues.append(WorldForgeIssue("campaign_mismatch", "Proposal campaign does not match the Campaign Bible."))
    if proposal.base_bible_revision != snapshot.revision:
        issues.append(
            WorldForgeIssue(
                "stale_bible_revision",
                f"Proposal targets revision {proposal.base_bible_revision}; current is {snapshot.revision}.",
            )
        )

    known_entities = _entity_ids(snapshot.document)
    proposed_entities: set[str] = set()
    for index, row in enumerate(proposal.entities, start=1):
        entity_id = _item_id(row, "entity", index)
        if entity_id in proposed_entities or entity_id in known_entities:
            issues.append(WorldForgeIssue("duplicate_entity", "Entity already exists or is duplicated.", entity_id))
        proposed_entities.add(entity_id)

    existing: dict[str, str] = {}
    for key in ("facts", "relationships"):
        rows = snapshot.document.get(key)
        if isinstance(rows, list | tuple):
            for index, row in enumerate(rows, start=1):
                if isinstance(row, Mapping):
                    existing[_fact_identity(row, key[:-1], index)] = _meaning(row)

    seen: set[str] = set()
    cross_links: dict[str, tuple[str, ...]] = {}
    for group, rows in (("fact", proposal.facts), ("relationship", proposal.relationships), ("card", proposal.retrieval_cards)):
        for index, row in enumerate(rows, start=1):
            item_id = _fact_identity(row, group, index)
            if item_id in seen:
                issues.append(WorldForgeIssue("duplicate_item", "Proposal item identifier is duplicated.", item_id))
            seen.add(item_id)
            meaning = _meaning(row)
            if not meaning:
                issues.append(WorldForgeIssue("empty_meaning", "Proposal item has no narrative meaning.", item_id))
            prior = existing.get(item_id)
            if prior is not None and prior != meaning:
                issues.append(WorldForgeIssue("contradiction", "Proposal conflicts with existing Campaign Bible meaning.", item_id))
            refs = tuple(
                str(ref)
                for ref in (row.get("entity_refs") or row.get("entities") or ())
                if str(ref).strip()
            )
            cross_links[item_id] = refs
            for ref in refs:
                if ref not in known_entities and ref not in proposed_entities:
                    issues.append(WorldForgeIssue("dangling_entity_ref", f"Unknown entity reference: {ref}", item_id))
            if group != "card" and str(row.get("authority") or "generated_proposal") != "generated_proposal":
                issues.append(
                    WorldForgeIssue(
                        "proposal_claims_authority",
                        "Unapproved World Forge items must use generated_proposal authority.",
                        item_id,
                    )
                )
    return WorldForgeAudit(passed=not issues, issues=tuple(issues), cross_links=cross_links)


def apply_world_forge_proposal(
    snapshot: CampaignBibleSnapshot,
    proposal: WorldForgeProposal,
) -> tuple[dict[str, Any], WorldForgeAudit]:
    audit = audit_world_forge_proposal(snapshot, proposal)
    if not audit.passed:
        return dict(snapshot.document), audit

    document = dict(snapshot.document)
    entities = document.get("entities")
    entity_map = dict(entities) if isinstance(entities, Mapping) else {}
    for index, row in enumerate(proposal.entities, start=1):
        entity_id = _item_id(row, "entity", index)
        entity_map[entity_id] = {**dict(row), "id": entity_id}
    document["entities"] = entity_map

    for key, rows in (
        ("facts", proposal.facts),
        ("relationships", proposal.relationships),
        ("retrieval_cards", proposal.retrieval_cards),
    ):
        existing_rows = [dict(row) for row in document.get(key, ()) if isinstance(row, Mapping)]
        approved: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            if key != "retrieval_cards":
                item["authority"] = str(item.pop("approved_authority", "objective_canon"))
            item["approved_from_proposal"] = proposal.proposal_id
            item["proposal_hash"] = proposal.proposal_hash
            approved.append(item)
        document[key] = existing_rows + approved

    provenance = dict(document.get("generation_provenance") or {})
    provenance[proposal.proposal_id] = {
        "proposal_hash": proposal.proposal_hash,
        "base_bible_revision": proposal.base_bible_revision,
        **dict(proposal.provenance),
    }
    document["generation_provenance"] = provenance
    return document, audit
