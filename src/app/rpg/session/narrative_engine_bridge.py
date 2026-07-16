"""One-way migration bridges from authoritative turns into the Narrative Engine."""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping, Sequence

from app.rpg.narrative_engine import (
    DeliveryMode,
    EvidenceBroker,
    EvidenceRecord,
    InMemoryEvidenceSource,
    NarrativeEngineService,
    NarrativeSignificance,
    PresentationProfile,
    SceneChange,
    TurnPresentationRequest,
    legacy_response_projection,
)
from app.rpg.narrative_engine.serialization import canonical_response_from_dict
from app.rpg.session.genesis.turn_grounding import (
    TurnGroundingPacket,
    build_turn_grounding_packet,
    narrative_grounding_footer,
)

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


def _npc_identity(result: Mapping[str, Any]) -> tuple[str, str]:
    npc = _mapping(result.get("npc"))
    visible = _mapping(result.get("visible_response"))
    visible_npc = _mapping(visible.get("npc"))
    resolved = _mapping(result.get("resolved_result") or result.get("result"))
    raw_id = _text(
        npc.get("speaker_id")
        or visible_npc.get("speaker_id")
        or resolved.get("target_id")
    )
    name = _text(
        npc.get("speaker")
        or visible_npc.get("speaker")
        or resolved.get("target_name")
        or "NPC"
    )
    if raw_id and not raw_id.startswith("npc:"):
        raw_id = f"npc:{raw_id.casefold().replace(' ', '_')}"
    if not raw_id:
        raw_id = f"npc:{name.casefold().replace(' ', '_')}"
    return raw_id, name


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


def _profile(result: Mapping[str, Any], default: PresentationProfile) -> PresentationProfile:
    session = _mapping(result.get("session"))
    runtime = _mapping(session.get("runtime_state") or result.get("runtime_state"))
    settings = _mapping(runtime.get("runtime_settings") or runtime.get("settings"))
    value = _text(
        result.get("presentation_profile")
        or runtime.get("presentation_profile")
        or settings.get("presentation_profile")
    ).casefold()
    try:
        return PresentationProfile(value) if value else default
    except ValueError:
        return default


def _scene_changes(
    result: Mapping[str, Any],
    mode: str,
    evidence: Sequence[EvidenceRecord],
) -> tuple[SceneChange, ...]:
    report = _mapping(
        result.get("environmental_narration_report")
        or result.get("environmental_scene_intro")
        or result.get("scene_change_report")
    )
    raw_triggers = report.get("triggers") or report.get("changes") or ()
    if isinstance(raw_triggers, str):
        raw_triggers = [raw_triggers]
    changes: list[SceneChange] = []
    scene_ref = (
        "runtime:scene:current"
        if any(row.evidence_id == "runtime:scene:current" for row in evidence)
        else ""
    )
    if isinstance(raw_triggers, list | tuple):
        for row in raw_triggers:
            raw_kind = _text(
                row.get("kind") if isinstance(row, Mapping) else row
            ).casefold()
            kind = _TRIGGER_KIND.get(raw_kind)
            if kind:
                changes.append(
                    SceneChange(
                        kind=kind,
                        importance=(
                            "major"
                            if kind in {
                                "new_game",
                                "location_changed",
                                "region_changed",
                                "major_event",
                            }
                            else "notable"
                        ),
                        evidence_refs=(scene_ref,) if scene_ref else (),
                    )
                )
    if result.get("new_game") is True and not any(
        change.kind == "new_game" for change in changes
    ):
        changes.append(
            SceneChange(
                "new_game",
                "major",
                (scene_ref,) if scene_ref else (),
            )
        )
    location_changed = bool(
        result.get("location_changed")
        or _mapping(result.get("resolved_result")).get("location_changed")
    )
    if (mode == "travel" or location_changed) and not any(
        change.kind == "location_changed" for change in changes
    ):
        changes.append(
            SceneChange(
                "location_changed",
                "major",
                (scene_ref,) if scene_ref else (),
            )
        )
    unique: dict[str, SceneChange] = {}
    for change in changes:
        unique.setdefault(change.kind, change)
    return tuple(unique.values())


def _publish(
    result: dict[str, Any],
    generated: Any,
    source: str,
    grounding: TurnGroundingPacket,
) -> dict[str, Any]:
    projection = legacy_response_projection(generated.response)
    provider_authored = generated.response.generation.source == "structured_provider"
    footer = narrative_grounding_footer(
        grounding.metadata,
        block_count=len(generated.response.blocks),
    )
    result.update(projection)
    result["canonical_visible_response"] = dict(projection["visible_response"])
    result["first_call_visible_response"] = {
        "canonical_visible_response": dict(projection["visible_response"]),
        "visible_response": dict(projection["visible_response"]),
    }
    result["canonical_narrative_response"] = generated.response.as_dict()
    result["canonical_narrative_source"] = "unified_narrative_engine_v1"
    result["source"] = source
    result["legacy_visible_prose_consumed"] = False
    if provider_authored:
        result["llm_called"] = True
        result["llm_purpose"] = "canonical_dialogue_generation"
    result["narrative_grounding"] = {
        **dict(grounding.metadata),
        "footer": footer,
        "research": (
            grounding.research.as_dict()
            if grounding.research is not None
            else None
        ),
    }
    result["narrative_grounding_footer"] = footer
    nested = _mapping(result.get("result"))
    if nested:
        nested.update(projection)
        nested["canonical_visible_response"] = dict(projection["visible_response"])
        nested["first_call_visible_response"] = {
            "canonical_visible_response": dict(projection["visible_response"]),
            "visible_response": dict(projection["visible_response"]),
        }
        nested["canonical_narrative_response"] = generated.response.as_dict()
        nested["canonical_narrative_source"] = "unified_narrative_engine_v1"
        nested["legacy_visible_prose_consumed"] = False
        if provider_authored:
            nested["llm_called"] = True
            nested["llm_purpose"] = "canonical_dialogue_generation"
        nested["narrative_grounding"] = result["narrative_grounding"]
        nested["narrative_grounding_footer"] = footer
        result["result"] = nested
    return result


def _dialogue_quality_context(
    result: Mapping[str, Any],
    *,
    player_input: str,
) -> dict[str, Any]:
    from app.rpg.presentation.dialogue_quality import (
        build_canonical_dialogue_quality_context,
    )

    return build_canonical_dialogue_quality_context(
        dict(result),
        player_input=player_input,
    )


def _request(
    result: Mapping[str, Any],
    *,
    session_id: str,
    player_input: str,
    mode: str,
    evidence: Sequence[EvidenceRecord],
    grounding_metadata: Mapping[str, Any],
    changes: tuple[SceneChange, ...] = (),
    profile: PresentationProfile = PresentationProfile.IMMERSIVE,
    significance: NarrativeSignificance = NarrativeSignificance.ROUTINE,
    target_actor_id: str | None = None,
    dialogue_quality_context: Mapping[str, Any] | None = None,
) -> TurnPresentationRequest:
    speaker_id, _ = _npc_identity(result)
    has_speaker = bool(target_actor_id or _text(_mapping(result.get("npc")).get("speaker")))
    interaction_token = _text(result.get("interaction_id"))
    turn_token = (
        interaction_token
        or result.get("turn_id")
        or result.get("interaction_seq")
        or result.get("sequence")
        or result.get("tick")
        or 0
    )
    quality_context = (
        dict(dialogue_quality_context)
        if dialogue_quality_context is not None
        else _dialogue_quality_context(result, player_input=player_input)
    )
    dialogue_speaker_ids = tuple(
        dict.fromkeys(
            _text(value)
            for value in quality_context.get("speaker_ids") or ()
            if _text(value)
        )
    )
    actor_ids = dialogue_speaker_ids or ((speaker_id,) if has_speaker else ())
    return TurnPresentationRequest(
        request_id=f"{mode}:{session_id}:{turn_token}",
        turn_id=(
            interaction_token
            or _text(result.get("turn_id"))
            or f"turn:{result.get('interaction_seq') or result.get('sequence') or result.get('tick') or 0}"
        ),
        campaign_id=session_id,
        player_input=player_input,
        authoritative_outcome=_mapping(
            result.get("resolved_result") or result.get("result")
        ),
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
            "evidence_limit": max(12, min(len(evidence), 50)),
            "dialogue_quality_context": quality_context,
            "llm_prose_required": quality_context.get("llm_prose_required") is True,
            "dialogue_speaker_ids": list(dialogue_speaker_ids),
            **dict(grounding_metadata),
        },
    )


def _generate(
    grounding: TurnGroundingPacket,
    request: TurnPresentationRequest,
) -> Any:
    return NarrativeEngineService(
        evidence_broker=EvidenceBroker(
            [
                InMemoryEvidenceSource(
                    grounding.evidence,
                    source_id="turn_grounding",
                )
            ]
        ),
    ).generate(request)


def canonicalize_direct_dialogue_result(
    result: dict[str, Any],
    *,
    session_id: str,
    player_input: str,
) -> dict[str, Any]:
    """Generate all direct-dialogue prose through the canonical writer."""

    if not isinstance(result, dict) or result.get("ok") is not True:
        return result
    if isinstance(result.get("canonical_narrative_response"), dict):
        return result
    speaker_id, _ = _npc_identity(result)
    quality_context = _dialogue_quality_context(
        result,
        player_input=player_input,
    )
    quality_speaker_ids = tuple(
        _text(value)
        for value in quality_context.get("speaker_ids") or ()
        if _text(value)
    )
    if quality_speaker_ids:
        speaker_id = quality_speaker_ids[0]
    grounding_result = dict(result)
    grounding_result["dialogue_speaker_ids"] = list(quality_speaker_ids)
    grounding = build_turn_grounding_packet(
        grounding_result,
        campaign_id=session_id,
        player_input=player_input,
        speaker_id=speaker_id,
        actor_ids=(speaker_id,),
        runtime_only=quality_context.get("fast_path") is True,
    )
    request = _request(
        result,
        session_id=session_id,
        player_input=player_input,
        mode="dialogue",
        evidence=grounding.evidence,
        grounding_metadata=grounding.metadata,
        profile=_profile(result, PresentationProfile.FAST),
        target_actor_id=speaker_id,
        dialogue_quality_context=quality_context,
    )
    generated = _generate(grounding, request)
    return _publish(
        result,
        generated,
        "narrative_engine_direct_dialogue_v2",
        grounding,
    )


def canonicalize_scene_turn_result(
    result: dict[str, Any],
    *,
    session_id: str,
    player_input: str,
) -> dict[str, Any]:
    if not isinstance(result, dict) or result.get("ok") is not True:
        return result
    if isinstance(result.get("canonical_narrative_response"), dict):
        return result
    mode = _response_mode(result)
    speaker_id, _ = _npc_identity(result)
    grounding = build_turn_grounding_packet(
        result,
        campaign_id=session_id,
        player_input=player_input,
        speaker_id=speaker_id if speaker_id != "npc:npc" else None,
    )
    changes = _scene_changes(result, mode, grounding.evidence)
    if mode not in _SCENE_MODES and not changes:
        return result
    request = _request(
        result,
        session_id=session_id,
        player_input=player_input,
        mode=mode,
        evidence=grounding.evidence,
        grounding_metadata=grounding.metadata,
        changes=changes,
        profile=_profile(result, PresentationProfile.IMMERSIVE),
        significance=(
            NarrativeSignificance.NOTABLE
            if changes
            else NarrativeSignificance.ROUTINE
        ),
    )
    generated = _generate(grounding, request)
    return _publish(
        result,
        generated,
        "narrative_engine_scene_turn_v1",
        grounding,
    )


def _resolved_significance(
    result: Mapping[str, Any],
    mode: str,
) -> NarrativeSignificance:
    resolved = _mapping(result.get("resolved_result") or result.get("result"))
    if mode == "major_beat" or bool(
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
    if not isinstance(result, dict) or result.get("ok") is not True:
        return result
    if isinstance(result.get("canonical_narrative_response"), dict):
        interaction_id = _text(result.get("interaction_id"))
        if not interaction_id:
            return result
        response = canonical_response_from_dict(
            result["canonical_narrative_response"]
        )
        if response.turn_id == interaction_id:
            return result
        request_kind = _text(response.request_id).split(":", 1)[0] or _response_mode(result)
        rebound = replace(
            response,
            response_id=(
                f"narrative:{session_id}:{interaction_id}:{response.revision}"
            ),
            request_id=f"{request_kind}:{session_id}:{interaction_id}",
            turn_id=interaction_id,
            content_hash="",
        ).with_content_hash()
        canonical = rebound.as_dict()
        result["canonical_narrative_response"] = canonical
        nested = result.get("result")
        if isinstance(nested, dict):
            nested["canonical_narrative_response"] = canonical
        return result
    mode = _response_mode(result)
    if mode in _SCENE_MODES:
        return canonicalize_scene_turn_result(
            result,
            session_id=session_id,
            player_input=player_input,
        )
    if mode in _DIALOGUE_MODES:
        return canonicalize_direct_dialogue_result(
            result,
            session_id=session_id,
            player_input=player_input,
        )
    speaker_id, _ = _npc_identity(result)
    grounding = build_turn_grounding_packet(
        result,
        campaign_id=session_id,
        player_input=player_input,
        speaker_id=speaker_id if speaker_id != "npc:npc" else None,
    )
    request = _request(
        result,
        session_id=session_id,
        player_input=player_input,
        mode=mode,
        evidence=grounding.evidence,
        grounding_metadata=grounding.metadata,
        profile=_profile(result, PresentationProfile.IMMERSIVE),
        significance=_resolved_significance(result, mode),
        target_actor_id=(
            speaker_id
            if _text(_mapping(result.get("npc")).get("speaker"))
            else None
        ),
    )
    generated = _generate(grounding, request)
    return _publish(
        result,
        generated,
        "narrative_engine_resolved_turn_v1",
        grounding,
    )
