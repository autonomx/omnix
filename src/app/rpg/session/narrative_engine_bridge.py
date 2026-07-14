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
    SceneChange,
    TurnPresentationRequest,
    WriterResult,
    legacy_response_projection,
)
from app.rpg.narrative_engine.shadow import runtime_evidence
from app.rpg.narrative_engine.writer import DeterministicNarrativeWriter

_SCENE_MODES = {"observation", "investigation", "travel"}
_MODE_ALIASES = {
    "look": "observation",
    "inspect": "observation",
    "move": "travel",
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
    speaker_id, _ = _npc_line(result)
    has_speaker = bool(_text(_mapping(result.get("npc")).get("speaker")))
    turn_token = result.get("turn_id") or result.get("tick") or 0
    request = TurnPresentationRequest(
        request_id=f"scene:{session_id}:{turn_token}",
        turn_id=_text(result.get("turn_id")) or f"turn:{result.get('tick') or 0}",
        campaign_id=session_id,
        player_input=player_input,
        authoritative_outcome=_mapping(result.get("resolved_result") or result.get("result")),
        scene_snapshot=_mapping(result.get("scene")),
        actor_ids=(speaker_id,) if has_speaker else (),
        target_actor_id=speaker_id if has_speaker and mode == "dialogue" else None,
        scene_changes=changes,
        presentation_profile=PresentationProfile.IMMERSIVE,
        delivery_mode=DeliveryMode.BLOCKING,
        metadata={
            "response_mode": mode,
            "response_id": f"narrative:{session_id}:{turn_token}:1",
        },
    )
    generated = NarrativeEngineService(
        evidence_broker=EvidenceBroker([InMemoryEvidenceSource(evidence, source_id="scene_turn")]),
    ).generate(request)
    return _publish(result, generated, "narrative_engine_scene_turn_v1")
