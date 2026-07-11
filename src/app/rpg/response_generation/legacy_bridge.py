from __future__ import annotations

from typing import Any, Callable, Mapping

from app.rpg.ai.world_scene_narrator_runtime import (
    SceneNarrator,
    apply_legacy_narration_emphasis,
    narrate_scene as _legacy_narrate_scene,
    play_scene,
)

from .contracts import ResponseRequest
from .orchestration import RpgResponseGenerator


CANONICAL_NARRATION_SOURCE = "rpg_response_generator_v1"


def narrate_scene_canonical(
    scene: Mapping[str, Any],
    narration_context: Mapping[str, Any],
    llm_gateway: Any | None = None,
    tone: str = "dramatic",
    retry_on_invalid: bool = True,
    debug_logging: bool = False,
    on_chunk: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Compatibility entry point with canonical final-response ownership.

    The legacy narrator still performs provider generation and its existing
    simulation-safe sanitization. The result is then adapted into the canonical
    semantic envelope, selected, quality-checked, rendered, and published by
    ``RpgResponseGenerator``. Authoritative deltas are copied into metadata only.
    """
    context = dict(narration_context or {})
    legacy = _legacy_narrate_scene(
        dict(scene or {}),
        context,
        llm_gateway=llm_gateway,
        tone=tone,
        retry_on_invalid=retry_on_invalid,
        debug_logging=debug_logging,
        on_chunk=on_chunk,
    )
    if not isinstance(legacy, Mapping):
        legacy = {"narration": str(legacy or "")}
    payload = dict(legacy)
    narration_json = _mapping(payload.get("narration_json"))
    npc = _mapping(narration_json.get("npc"))
    response_mode = _response_mode(context, narration_json)
    legacy_payload = {
        "source": "legacy_world_scene",
        "response_mode": response_mode,
        "narration": narration_json.get("narration") or payload.get("narration") or "",
        "action": narration_json.get("action") or "",
        "npc": {
            "speaker": npc.get("speaker") or npc.get("name") or "",
            "line": npc.get("line") or npc.get("text") or "",
        },
        "forward_strategy": context.get("forward_strategy") or "answer_directly",
        "agency_effect": context.get("agency_effect") or "none",
        "reversibility": context.get("reversibility") or "fully_reversible",
    }
    authoritative_result = {
        "state_delta": _mapping(
            context.get("state_delta")
            or _mapping(context.get("turn_contract")).get("state_delta")
        ),
        "response_mode": response_mode,
        "production_rpg_response": True,
        # Legacy payloads are not yet claim-ref annotated. The canonical hard
        # gates still enforce visibility, speakers, proposals, agency, and no
        # direct mutation while Phase 3+ paths can opt into strict references.
        "strict_claim_refs": False,
    }
    request = ResponseRequest(
        turn_id=str(
            context.get("turn_id")
            or _mapping(context.get("turn_contract")).get("turn_id")
            or "legacy-scene"
        ),
        player_input=str(context.get("player_input") or ""),
        authoritative_turn_result=authoritative_result,
        session_id=str(context.get("session_id") or ""),
        scene_id=str(_mapping(scene).get("scene_id") or _mapping(scene).get("id") or ""),
        speaker_id=str(npc.get("speaker") or ""),
        runtime_mode="legacy_world_scene_compatibility",
        legacy_payload=legacy_payload,
    )
    rendered = RpgResponseGenerator().generate(request)
    if rendered.text.strip():
        payload["narration"] = rendered.text
    payload["canonical_response"] = {
        "source": CANONICAL_NARRATION_SOURCE,
        "mode": rendered.mode.value,
        "approved_section_ids": list(rendered.approved_section_ids),
        "resolved_claim_refs": list(rendered.resolved_claim_refs),
        "quality_report": dict(rendered.quality_report),
        "repair_history": list(rendered.repair_history),
        "delivery_units": list(rendered.delivery_units),
        "metadata": dict(rendered.metadata),
    }
    payload["canonical_response_source"] = CANONICAL_NARRATION_SOURCE
    return payload


def _response_mode(
    context: Mapping[str, Any],
    narration_json: Mapping[str, Any],
) -> str:
    resolved = _mapping(context.get("resolved_result"))
    contract = _mapping(context.get("turn_contract"))
    return str(
        narration_json.get("response_mode")
        or context.get("response_mode")
        or resolved.get("response_mode")
        or resolved.get("semantic_family")
        or contract.get("semantic_family")
        or resolved.get("action_type")
        or "action"
    )


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


__all__ = [
    "CANONICAL_NARRATION_SOURCE",
    "SceneNarrator",
    "apply_legacy_narration_emphasis",
    "narrate_scene_canonical",
    "play_scene",
]
