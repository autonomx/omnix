from __future__ import annotations

from typing import Any, Callable, Mapping

from app.rpg.ai.world_scene_narrator_runtime import (
    SceneNarrator,
    apply_legacy_narration_emphasis,
    narrate_scene as _legacy_narrate_scene,
    play_scene,
)

from .contracts import ResponseRequest
from .profiled_generator import ProfiledRpgResponseGenerator
from .validated_delivery import ValidatedDeliverySession


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
    """Compatibility entry point with canonical validation-first publication.

    The legacy narrator may generate provider text, but its raw tokens are never
    player-visible. The complete candidate is adapted, hard-gated, ranked,
    quality-checked, and rerendered before approved sentence or audio-phrase units
    are delivered through ``on_chunk``. Authoritative deltas remain metadata only.
    """
    context = dict(narration_context or {})
    legacy = _legacy_narrate_scene(
        dict(scene or {}),
        context,
        llm_gateway=llm_gateway,
        tone=tone,
        retry_on_invalid=retry_on_invalid,
        debug_logging=debug_logging,
        on_chunk=None,
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
        "strict_claim_refs": False,
        "mechanic_resolved": bool(context.get("mechanic_resolved")),
        "recovery_needed": bool(context.get("recovery_needed")),
        "resolver_status": context.get("resolver_status"),
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
        runtime_mode=str(context.get("runtime_mode") or "legacy_world_scene_compatibility"),
        provider_policy=_mapping(
            context.get("provider_policy") or context.get("response_profile")
        ),
        legacy_payload=legacy_payload,
    )
    generator = ProfiledRpgResponseGenerator()
    rendered = generator.generate(request)
    profile = generator.resolve_profile(request, rendered.mode)
    delivery = ValidatedDeliverySession.prepare(rendered, profile)
    if on_chunk is not None:
        while (unit := delivery.next_unit()) is not None:
            on_chunk(unit.text)
            delivery.acknowledge(unit)
    checkpoint = delivery.checkpoint()
    if rendered.text.strip():
        payload["narration"] = rendered.text
    payload["canonical_response"] = {
        "source": CANONICAL_NARRATION_SOURCE,
        "mode": rendered.mode.value,
        "approved_section_ids": list(rendered.approved_section_ids),
        "resolved_claim_refs": list(rendered.resolved_claim_refs),
        "quality_report": dict(rendered.quality_report),
        "repair_history": list(rendered.repair_history),
        "delivery_units": [unit.text for unit in delivery.units],
        "delivery_checkpoint": {
            "state": checkpoint.state.value,
            "prepared_unit_ids": list(checkpoint.prepared_unit_ids),
            "delivered_unit_ids": list(checkpoint.delivered_unit_ids),
            "next_index": checkpoint.next_index,
            "interruption_reason": checkpoint.interruption_reason,
            "validation_token": checkpoint.validation_token,
        },
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
