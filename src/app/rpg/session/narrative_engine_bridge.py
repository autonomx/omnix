"""One-way migration bridges from legacy turn execution into the Narrative Engine."""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping, Sequence

from app.rpg.narrative_engine import (
    BeatPurpose,
    DeliveryMode,
    EvidenceBroker,
    EvidenceRecord,
    InMemoryEvidenceSource,
    NarrativeEngineService,
    PresentationProfile,
    TurnPresentationRequest,
    WriterResult,
    legacy_response_projection,
)
from app.rpg.narrative_engine.shadow import runtime_evidence
from app.rpg.narrative_engine.writer import DeterministicNarrativeWriter


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _npc_line(result: Mapping[str, Any]) -> tuple[str, str]:
    npc = _mapping(result.get("npc"))
    visible = _mapping(result.get("visible_response"))
    visible_npc = _mapping(visible.get("npc"))
    speaker = _text(
        npc.get("speaker_id")
        or npc.get("speaker")
        or visible_npc.get("speaker_id")
        or visible_npc.get("speaker")
        or "NPC"
    )
    line = _text(npc.get("line") or npc.get("text") or visible_npc.get("line") or visible_npc.get("text"))
    speaker_id = speaker if speaker.startswith("npc:") else f"npc:{speaker.casefold().replace(' ', '_')}"
    return speaker_id, line


class _GroundedDialogueWriter:
    """Use the already-grounded first-call line inside the new ordered contract."""

    def __init__(self, line: str) -> None:
        self.line = line
        self._fallback = DeterministicNarrativeWriter()

    def write(self, request, plan, evidence: Sequence[EvidenceRecord]) -> WriterResult:
        base = self._fallback.write(request, plan, evidence)
        blocks = tuple(
            replace(block, text=self.line, metadata={**dict(block.metadata), "source": "grounded_first_call"})
            if block.purpose is BeatPurpose.DIRECT_ANSWER and self.line
            else block
            for block in base.blocks
        )
        return replace(base, blocks=blocks, source="narrative_engine_grounded_dialogue")


def canonicalize_direct_dialogue_result(
    result: dict[str, Any],
    *,
    session_id: str,
    player_input: str,
) -> dict[str, Any]:
    """Replace direct-dialogue publication fields with canonical block projections."""

    if not isinstance(result, dict) or result.get("ok") is not True:
        return result
    speaker_id, line = _npc_line(result)
    evidence = runtime_evidence(result)
    request = TurnPresentationRequest(
        request_id=f"direct:{session_id}:{result.get('turn_id') or result.get('tick') or 0}",
        turn_id=_text(result.get("turn_id")) or f"turn:{result.get('tick') or 0}",
        campaign_id=session_id,
        player_input=player_input,
        authoritative_outcome=_mapping(result.get("resolved_result") or result.get("result")),
        scene_snapshot=_mapping(result.get("scene")),
        actor_ids=(speaker_id,),
        target_actor_id=speaker_id,
        presentation_profile=PresentationProfile.FAST,
        delivery_mode=DeliveryMode.BLOCKING,
        metadata={
            "response_mode": "dialogue",
            "response_id": f"narrative:{session_id}:{result.get('turn_id') or result.get('tick') or 0}:1",
        },
    )
    generated = NarrativeEngineService(
        evidence_broker=EvidenceBroker([InMemoryEvidenceSource(evidence, source_id="direct_dialogue")]),
        writer=_GroundedDialogueWriter(line),
    ).generate(request)
    projection = legacy_response_projection(generated.response)
    result.update(projection)
    result["canonical_narrative_response"] = generated.response.as_dict()
    result["canonical_narrative_source"] = "unified_narrative_engine_v1"
    result["source"] = "narrative_engine_direct_dialogue_v1"
    nested = _mapping(result.get("result"))
    if nested:
        nested.update(projection)
        nested["canonical_narrative_response"] = generated.response.as_dict()
        nested["canonical_narrative_source"] = "unified_narrative_engine_v1"
        result["result"] = nested
    return result
