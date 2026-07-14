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
    NarrativeSignificance,
    PresentationProfile,
    SceneChange,
    TurnPresentationRequest,
    WriterResult,
    legacy_response_projection,
)
from app.rpg.narrative_engine.shadow import runtime_evidence
from app.rpg.narrative_engine.writer import DeterministicNarrativeWriter

_SCENE_MODES = {"observation", "investigation", "travel"}
_DIALOGUE_MODES = {"dialogue", "conversation", "social"}
_MODE_ALIASES = {
    "look": "observation",
    "inspect": "observation",
    "move": "travel",
    "service": "transaction",
    "shop": "transaction",
    "trade": "transaction",
    "commerce": "transaction",
    "buy": "transaction",
    "sell": "transaction",
    "fight": "combat",
    "attack": "combat",
    "combat_action": "combat",
    "quest_complete": "major_beat",
    "quest_reward": "major_beat",
    "relationship_change": "action",
    "party": "action",
}
_TRIGGER_KIND = {
    "new_game": "new_game",
    "location_change": "location_changed",
    "location_changed": "location_changed",
    "region_change": "region_changed",
    "region_changed": "region_changed",
    "time_change": "time_changed",
    "time_changed": "time_changed",
    "weather_change": "weather_changed",
    "weather_changed": "weather_changed",
    "major_event": "major_event",
    "activity_change": "nearby_activity_changed",
    "perceptual_change": "perceptual_change",
    "changed_return_visit": "changed_return_visit",
}


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


def _response_mode(result: Mapping[str, Any]) -> str:
    resolved = _mapping(result.get("resolved_result") or result.get("result"))
    mode = _text(
        resolved.get("response_mode")
        or resolved.get("semantic_family")
        or resolved.get("action_type")
        or result.get("response_mode")
        or result.get("action_type")
        or "action"
    ).casefold()
    return _MODE_ALIASES.get(mode, mode)


def _scene_changes(result: Mapping[str, Any], mode: str, evidence: Sequence[EvidenceRecord]) -> tuple[SceneChange, ...]:
    report = _mapping(
        result.get("environmental_narration_report")
        or result.get("environmental_scene_intro")
        or result.get("scene_change_report")
    )
    raw_triggers = report.get("triggers") or report.get("changes") or ()
    if isinstance(raw_triggers, str):
        raw_triggers = [raw_triggers]
    changes: list[SceneChange] = []
    scene_ref = "runtime:scene:current" if any(row.evidence_id == "runtime:scene:current" for row in evidence) else ""
    if isinstance(raw_triggers, list | tuple):
        for row in raw_triggers:
            raw_kind = _text(row.get("kind") if isinstance(row, Mapping) else row).casefold()
            kind = _TRIGGER_KIND.get(raw_kind)
            if kind:
                changes.append(
                    SceneChange(
                        kind=kind,
                        importance="major" if kind in {"new_game", "location_changed", "region_changed", "major_event"} else "notable",
                        evidence_refs=(scene_ref,) if scene_ref else (),
                    )
                )
    if result.get("new_game") is True and not any(change.kind == "new_game" for change in changes):
        changes.append(SceneChange("new_game", "major", (scene_ref,) if scene_ref else ()))
    location_changed = bool(result.get("location_changed") or _mapping(result.get("resolved_result")).get("location_changed"))
    if (mode == "travel" or location_changed) and not any(change.kind == "location_changed" for change in changes):
        changes.append(SceneChange("location_changed", "major", (scene_ref,) if scene_ref else ()))
    unique: dict[str, SceneChange] = {}
    for change in changes:
        unique.setdefault(change.kind, change)
    return tuple(unique.values())


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


def _publish(result: dict[str, Any], generated, source: str) -> dict[str, Any]:
    projection = legacy_response_projection(generated.response)
    result.update(projection)
    result["canonical_narrative_response"] = generated.response.as_dict()
    result["canonical_narrative_source"] = "unified_narrative_engine_v1"
    result["source"] = source
    nested = _mapping(result.get("result"))
    if nested:
        nested.update(projection)
        nested["canonical_narrative_response"] = generated.response.as_dict()
        nested["canonical_narrative_source"] = "unified_narrative_engine_v1"
        result["result"] = nested
    return result


def _request(
    result: Mapping[str, Any],
    *,
    session_id: str,
    player_input: str,
    mode: str,
    evidence: Sequence[EvidenceRecord],
    changes: tuple[SceneChange, ...] = (),
    profile: PresentationProfile = PresentationProfile.IMMERSIVE,
    significance: NarrativeSignificance = NarrativeSignificance.ROUTINE,
    target_actor_id: str | None = None,
) -> TurnPresentationRequest:
    speaker_id, _ = _npc_line(result)
    has_speaker = bool(_text(_mapping(result.get("npc")).get("speaker")))
    turn_token = result.get("turn_id") or result.get("tick") or 0
    actor_ids = (speaker_id,) if has_speaker else ()
    return TurnPresentationRequest(
        request_id=f"{mode}:{session_id}:{turn_token}",
        turn_id=_text(result.get("turn_id")) or f"turn:{result.get('tick') or 0}",
        campaign_id=session_id,
        player_input=player_input,
        authoritative_outcome=_mapping(result.get("resolved_result") or result.get("result")),
        scene_snapshot=_mapping(result.get("scene")),
        actor_ids=actor_ids,
        target_actor_id=target_actor_id,
        scene_changes=changes,
        significance=significance,
        presentation_profile=profile,
        delivery_mode=DeliveryMode.BLOCKING,
        metadata={
            "response_mode": mode,
            "response_id": f"narrative:{session_id}:{turn_token}:1",
            "evidence_limit": max(8, len(evidence)),
        },
    )


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
    request = _request(
        result,
        session_id=session_id,
        player_input=player_input,
        mode="dialogue",
        evidence=evidence,
        profile=PresentationProfile.FAST,
        target_actor_id=speaker_id,
    )
    generated = NarrativeEngineService(
        evidence_broker=EvidenceBroker([InMemoryEvidenceSource(evidence, source_id="direct_dialogue")]),
        writer=_GroundedDialogueWriter(line),
    ).generate(request)
    return _publish(result, generated, "narrative_engine_direct_dialogue_v1")


def canonicalize_scene_turn_result(
    result: dict[str, Any],
    *,
    session_id: str,
    player_input: str,
) -> dict[str, Any]:
    """Publish environment, observation, investigation, and travel through one engine."""

    if not isinstance(result, dict) or result.get("ok") is not True:
        return result
    if isinstance(result.get("canonical_narrative_response"), dict):
        return result
    mode = _response_mode(result)
    evidence = runtime_evidence(result)
    changes = _scene_changes(result, mode, evidence)
    if mode not in _SCENE_MODES and not changes:
        return result
    request = _request(
        result,
        session_id=session_id,
        player_input=player_input,
        mode=mode,
        evidence=evidence,
        changes=changes,
        profile=PresentationProfile.IMMERSIVE,
        significance=NarrativeSignificance.NOTABLE if changes else NarrativeSignificance.ROUTINE,
    )
    generated = NarrativeEngineService(
        evidence_broker=EvidenceBroker([InMemoryEvidenceSource(evidence, source_id="scene_turn")]),
    ).generate(request)
    return _publish(result, generated, "narrative_engine_scene_turn_v1")


def _resolved_significance(result: Mapping[str, Any], mode: str) -> NarrativeSignificance:
    resolved = _mapping(result.get("resolved_result") or result.get("result"))
    if mode in {"major_beat"} or bool(
        resolved.get("quest_completed")
        or resolved.get("defeated")
        or resolved.get("death")
        or resolved.get("major_revelation")
    ):
        return NarrativeSignificance.MAJOR
    if mode in {"combat", "transaction", "failure", "recovery"}:
        return NarrativeSignificance.NOTABLE
    return NarrativeSignificance.ROUTINE


def canonicalize_resolved_turn_result(
    result: dict[str, Any],
    *,
    session_id: str,
    player_input: str,
) -> dict[str, Any]:
    """Publish every remaining resolved gameplay mode through one presentation owner."""

    if not isinstance(result, dict) or result.get("ok") is not True:
        return result
    if isinstance(result.get("canonical_narrative_response"), dict):
        return result
    mode = _response_mode(result)
    if mode in _SCENE_MODES:
        return canonicalize_scene_turn_result(result, session_id=session_id, player_input=player_input)
    if mode in _DIALOGUE_MODES:
        speaker_id, line = _npc_line(result)
        if line:
            return canonicalize_direct_dialogue_result(result, session_id=session_id, player_input=player_input)
        mode = "action"
    evidence = runtime_evidence(result)
    significance = _resolved_significance(result, mode)
    request = _request(
        result,
        session_id=session_id,
        player_input=player_input,
        mode=mode,
        evidence=evidence,
        profile=(PresentationProfile.CINEMATIC if significance is NarrativeSignificance.MAJOR else PresentationProfile.IMMERSIVE),
        significance=significance,
    )
    generated = NarrativeEngineService(
        evidence_broker=EvidenceBroker([InMemoryEvidenceSource(evidence, source_id="resolved_turn")]),
    ).generate(request)
    return _publish(result, generated, "narrative_engine_resolved_turn_v1")
