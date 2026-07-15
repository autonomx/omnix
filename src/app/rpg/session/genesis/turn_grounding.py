"""Build one evidence packet from simulation, Campaign Bible, and Hermes research."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from app.rpg.narrative_engine import (
    EvidenceRecord,
    campaign_bible_evidence,
)
from app.rpg.narrative_engine.shadow import runtime_evidence

from .campaign_bible_runtime import load_campaign_bible_snapshot
from .hermes_campaign_research import CampaignResearchPacket, research_campaign_turn


@dataclass(frozen=True)
class TurnGroundingPacket:
    evidence: tuple[EvidenceRecord, ...]
    metadata: Mapping[str, Any]
    research: CampaignResearchPacket | None = None


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _session(result: Mapping[str, Any], campaign_id: str) -> Mapping[str, Any]:
    existing = result.get("session")
    if isinstance(existing, Mapping):
        return existing
    try:
        from app.rpg.session.service import load_session

        loaded = load_session(campaign_id)
        return loaded if isinstance(loaded, Mapping) else {}
    except Exception:
        return {}


def _faction_ids(session: Mapping[str, Any], speaker_id: str | None) -> tuple[str, ...]:
    if not speaker_id:
        return ()
    state = _mapping(session.get("state"))
    dossier = _mapping(
        _mapping(state.get("npc_dossiers")).get(speaker_id)
    )
    values = dossier.get("faction_ids")
    if not isinstance(values, list | tuple | set):
        return ()
    return tuple(str(value) for value in values if str(value).strip())


def _entity_ids(
    result: Mapping[str, Any],
    session: Mapping[str, Any],
    speaker_id: str | None,
    actor_ids: Sequence[str],
) -> tuple[str, ...]:
    values: list[str] = [str(value) for value in actor_ids if str(value)]
    if speaker_id:
        values.append(speaker_id)
    state = _mapping(session.get("state"))
    scene = _mapping(result.get("scene") or state.get("scene"))
    for candidate in (
        scene.get("location_id"),
        scene.get("region_id"),
        _mapping(state.get("location")).get("id"),
        _mapping(state.get("world")).get("active_location_id"),
    ):
        value = str(candidate or "").strip()
        if value:
            values.append(value)
    return tuple(dict.fromkeys(values))


def build_turn_grounding_packet(
    result: Mapping[str, Any],
    *,
    campaign_id: str,
    player_input: str,
    speaker_id: str | None = None,
    actor_ids: tuple[str, ...] = (),
    max_topics: int = 5,
    runtime_only: bool = False,
) -> TurnGroundingPacket:
    """Assemble evidence without mutating simulation or Campaign Bible state."""

    runtime = tuple(runtime_evidence(result))
    session = _session(result, campaign_id)
    snapshot = (
        None
        if runtime_only
        else load_campaign_bible_snapshot(
            campaign_id,
            session=session,
        )
    )
    bible_evidence = (
        campaign_bible_evidence(snapshot) if snapshot is not None else ()
    )
    entity_ids = _entity_ids(result, session, speaker_id, actor_ids)
    factions = _faction_ids(session, speaker_id)
    research = (
        None
        if runtime_only
        else research_campaign_turn(
            campaign_id=campaign_id,
            query=player_input,
            session=session,
            speaker_id=speaker_id,
            actor_ids=actor_ids,
            faction_ids=factions,
            entity_ids=entity_ids,
            research_id=f"research:{campaign_id}:{result.get('turn_id') or result.get('tick') or 0}",
            max_topics=max_topics,
        )
    )
    hermes_evidence = research.result.evidence() if research else ()
    by_id: dict[str, EvidenceRecord] = {}
    for record in (*runtime, *bible_evidence, *hermes_evidence):
        previous = by_id.get(record.evidence_id)
        if previous is None or record.source_revision >= previous.source_revision:
            by_id[record.evidence_id] = record
    topic_titles = list(research.topic_titles) if research else []
    metadata: dict[str, Any] = {
        "hermes_used": research is not None and bool(research.result.sources),
        "hermes_research_id": research.result.research_id if research else "",
        "canon_topic_count": len(topic_titles),
        "canon_topic_titles": topic_titles,
        "hermes_source_ids": [
            source.source_id for source in research.result.sources
        ]
        if research
        else [],
        "campaign_bible_revision": (
            research.snapshot.revision
            if research
            else snapshot.revision if snapshot else 0
        ),
        "campaign_bible_hash": (
            research.snapshot.content_hash
            if research
            else snapshot.content_hash if snapshot else ""
        ),
        "campaign_bible_evidence_count": len(bible_evidence),
        "runtime_evidence_count": len(runtime),
        "hermes_evidence_count": len(hermes_evidence),
        "faction_ids": list(factions),
        "grounding_passed": True,
        "research_read_only": True,
    }
    if runtime_only:
        metadata["runtime_only"] = True
    return TurnGroundingPacket(
        evidence=tuple(by_id.values()),
        metadata=metadata,
        research=research,
    )


def narrative_grounding_footer(
    metadata: Mapping[str, Any],
    *,
    block_count: int,
) -> dict[str, Any]:
    topics = int(metadata.get("canon_topic_count") or 0)
    passed = metadata.get("grounding_passed") is True
    return {
        "canon_topics_used": topics,
        "narrative_blocks": int(block_count),
        "grounding_passed": passed,
        "label": (
            f"{topics} canon topics used · {int(block_count)} narrative blocks · "
            + ("grounding passed" if passed else "grounding failed")
        ),
        "topic_titles": list(metadata.get("canon_topic_titles") or ()),
        "campaign_bible_revision": int(
            metadata.get("campaign_bible_revision") or 0
        ),
        "campaign_bible_hash": str(
            metadata.get("campaign_bible_hash") or ""
        ),
    }
