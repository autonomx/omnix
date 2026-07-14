"""Deterministic evidence retrieval and pre-generation knowledge filtering."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Protocol, Sequence

from .authority import VisibilityClass
from .contracts import EvidenceRecord

_TOKEN_PATTERN = re.compile(r"[a-z0-9']+", re.IGNORECASE)


@dataclass(frozen=True)
class EvidenceAccessContext:
    player_id: str = "player"
    speaker_id: str | None = None
    actor_ids: tuple[str, ...] = ()
    faction_ids: tuple[str, ...] = ()
    narrator_mode: bool = False


@dataclass(frozen=True)
class EvidenceQuery:
    text: str
    entity_ids: tuple[str, ...] = ()
    limit: int = 12
    access: EvidenceAccessContext = field(default_factory=EvidenceAccessContext)


@dataclass(frozen=True)
class RetrievalTrace:
    query: str
    selected_ids: tuple[str, ...]
    excluded: tuple[tuple[str, str], ...]
    candidate_count: int


@dataclass(frozen=True)
class EvidenceRetrievalResult:
    evidence: tuple[EvidenceRecord, ...]
    trace: RetrievalTrace


class EvidenceSource(Protocol):
    source_id: str

    def records(self, query: EvidenceQuery) -> Sequence[EvidenceRecord]: ...


class InMemoryEvidenceSource:
    def __init__(self, records: Iterable[EvidenceRecord], *, source_id: str = "memory") -> None:
        self.source_id = source_id
        self._records = tuple(records)

    def records(self, query: EvidenceQuery) -> Sequence[EvidenceRecord]:
        return self._records


def _visible(record: EvidenceRecord, access: EvidenceAccessContext) -> tuple[bool, str]:
    visibility = record.visibility
    if visibility in {VisibilityClass.PUBLIC, VisibilityClass.PLAYER_KNOWN}:
        return True, "visible"
    if visibility is VisibilityClass.NPC_PRIVATE:
        if access.speaker_id and access.speaker_id in record.known_by:
            return True, "speaker_knows"
        return False, "npc_private"
    if visibility is VisibilityClass.FACTION_PRIVATE:
        if set(access.faction_ids).intersection(record.known_by):
            return True, "faction_knows"
        return False, "faction_private"
    if visibility is VisibilityClass.NARRATOR_ONLY:
        return (access.narrator_mode, "narrator_only" if not access.narrator_mode else "narrator")
    return False, "game_master_only"


def _tokens(value: str) -> set[str]:
    return set(_TOKEN_PATTERN.findall(value.casefold()))


def _score(record: EvidenceRecord, query: EvidenceQuery) -> tuple[float, int, int, str]:
    query_tokens = _tokens(query.text)
    content_tokens = _tokens(record.content)
    overlap = len(query_tokens.intersection(content_tokens))
    entity_overlap = len(set(query.entity_ids).intersection(record.entity_refs))
    score = float(overlap * 3 + entity_overlap * 8) + max(0.0, min(record.confidence, 1.0))
    return (score, entity_overlap, record.source_revision, record.evidence_id)


class EvidenceBroker:
    """Collect, filter, rank, and trace evidence before planning or writing."""

    def __init__(self, sources: Iterable[EvidenceSource]) -> None:
        self._sources = tuple(sources)

    def retrieve(self, query: EvidenceQuery) -> EvidenceRetrievalResult:
        by_id: dict[str, EvidenceRecord] = {}
        for source in self._sources:
            for record in source.records(query):
                previous = by_id.get(record.evidence_id)
                if previous is None or record.source_revision > previous.source_revision:
                    by_id[record.evidence_id] = record

        eligible: list[EvidenceRecord] = []
        excluded: list[tuple[str, str]] = []
        for record in by_id.values():
            allowed, reason = _visible(record, query.access)
            if allowed:
                eligible.append(record)
            else:
                excluded.append((record.evidence_id, reason))

        ranked = sorted(
            eligible,
            key=lambda record: (
                -_score(record, query)[0],
                -_score(record, query)[1],
                -_score(record, query)[2],
                _score(record, query)[3],
            ),
        )
        selected = tuple(ranked[: max(1, min(int(query.limit), 50))])
        return EvidenceRetrievalResult(
            evidence=selected,
            trace=RetrievalTrace(
                query=query.text,
                selected_ids=tuple(record.evidence_id for record in selected),
                excluded=tuple(sorted(excluded)),
                candidate_count=len(by_id),
            ),
        )
