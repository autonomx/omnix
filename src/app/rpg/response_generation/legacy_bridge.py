from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable, Mapping

from app.rpg.ai.world_scene_narrator_runtime import (
    SceneNarrator as _LegacySceneNarrator,
    apply_legacy_narration_emphasis,
    narrate_scene as _legacy_narrate_scene,
)

from .contracts import ResponseMode, coerce_response_mode
from .production_pipeline import CANONICAL_NARRATION_SOURCE, ProfileBoundProvider
from .profiles import ResponseProfileRegistry
from .strict_pipeline import StrictRpgProductionResponsePipeline


def _pipeline() -> StrictRpgProductionResponsePipeline:
    return StrictRpgProductionResponsePipeline()


def narrate_scene_canonical(
    scene: Mapping[str, Any],
    narration_context: Mapping[str, Any],
    llm_gateway: Any | None = None,
    tone: str = "dramatic",
    retry_on_invalid: bool = True,
    debug_logging: bool = False,
    on_chunk: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Compatibility entry point with strict canonical publication ownership."""

    scene_payload = dict(scene or {})
    context = dict(narration_context or {})
    mode = _response_mode(context, {})
    recovery_needed = bool(
        context.get("recovery_needed")
        or str(context.get("resolver_status") or "").casefold()
        in {"unresolved", "partial", "unsupported", "no_match"}
        or mode in {ResponseMode.RECOVERY, ResponseMode.INVESTIGATION}
    )
    profile, ignored = ResponseProfileRegistry().resolve_from_request(
        mode,
        _mapping(context.get("provider_policy") or context.get("response_profile")),
        recovery_needed=recovery_needed,
    )
    profile_gateway = (
        ProfileBoundProvider(llm_gateway, profile)
        if llm_gateway is not None and profile.use_provider
        else None
    )
    legacy = _legacy_narrate_scene(
        scene_payload,
        context,
        llm_gateway=profile_gateway,
        tone=tone,
        retry_on_invalid=bool(profile.retry_count and retry_on_invalid),
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
        "legacy_visible_text": str(payload.get("narration") or ""),
        "response_mode": response_mode.value,
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
    turn_contract = _mapping(context.get("turn_contract"))
    state = _mapping(
        context.get("simulation_state")
        or context.get("state_snapshot")
        or context.get("state")
    )
    authoritative_result = {
        **turn_contract,
        "turn_id": context.get("turn_id") or turn_contract.get("turn_id"),
        "state_delta": _mapping(
            context.get("state_delta") or turn_contract.get("state_delta")
        ),
        "resolved_result": _mapping(
            context.get("resolved_result")
            or turn_contract.get("resolved_result")
            or turn_contract.get("resolved_action")
        ),
        "response_mode": response_mode.value,
        "production_rpg_response": True,
        "strict_claim_refs": True,
        "grounding_required": True,
        "mechanic_resolved": bool(context.get("mechanic_resolved")),
        "recovery_needed": recovery_needed,
        "resolver_status": context.get("resolver_status"),
        "speaker_id": npc.get("speaker") or "",
        "provider_policy": _mapping(
            context.get("provider_policy") or context.get("response_profile")
        ),
    }
    canonical = _pipeline().finalize_payload(
        legacy_payload,
        player_input=str(context.get("player_input") or ""),
        authoritative_turn_result=authoritative_result,
        simulation_state=state,
        turn_contract=turn_contract,
        profile=profile,
        ignored_profile_overrides=ignored,
        provider_profile_applied=(
            dict(profile_gateway.applied) if profile_gateway is not None else {}
        ),
        runtime_mode=(
            "legacy_world_scene_recovery"
            if recovery_needed
            else "legacy_world_scene_compatibility"
        ),
        on_chunk=on_chunk,
    )
    payload.update(canonical)
    payload["canonical_response_source"] = CANONICAL_NARRATION_SOURCE
    return payload


class SceneNarrator(_LegacySceneNarrator):
    """Public scene narrator whose visible narrative is canonically validated."""

    def narrate_scene(
        self,
        scene: dict[str, Any],
        state: dict[str, Any],
        *,
        tone: str | None = None,
    ):
        mode = _response_mode(state, {})
        recovery_needed = bool(
            state.get("recovery_needed")
            or mode in {ResponseMode.RECOVERY, ResponseMode.INVESTIGATION}
        )
        profile, ignored = ResponseProfileRegistry().resolve_from_request(
            mode,
            _mapping(state.get("provider_policy") or state.get("response_profile")),
            recovery_needed=recovery_needed,
        )
        original_gateway = self.llm_gateway
        profile_gateway = None
        if original_gateway is not None and profile.use_provider:
            profile_gateway = ProfileBoundProvider(original_gateway, profile)
            self.llm_gateway = profile_gateway
        try:
            result = super().narrate_scene(scene, state, tone=tone)
        finally:
            self.llm_gateway = original_gateway
        canonical = _pipeline().finalize_payload(
            {
                "source": "legacy_scene_narrator",
                "legacy_visible_text": result.narrative,
                "response_mode": mode.value,
                "narration": result.narrative,
                "npc": {},
            },
            player_input=str(state.get("player_input") or ""),
            authoritative_turn_result={
                **dict(state),
                "turn_id": state.get("turn_id"),
                "response_mode": mode.value,
                "production_rpg_response": True,
                "strict_claim_refs": True,
                "grounding_required": True,
            },
            simulation_state=state,
            profile=profile,
            ignored_profile_overrides=ignored,
            provider_profile_applied=(
                dict(profile_gateway.applied) if profile_gateway is not None else {}
            ),
            runtime_mode="public_scene_narrator",
        )
        metadata = {
            **dict(result.metadata),
            "canonical_response": canonical["canonical_response"],
            "canonical_response_source": CANONICAL_NARRATION_SOURCE,
        }
        return replace(result, narrative=canonical["narration"], metadata=metadata)


def play_scene(
    scene: dict[str, Any],
    state: dict[str, Any],
    *,
    llm_gateway: Any | None = None,
    tone: str = "dramatic",
) -> dict[str, Any]:
    """Play a scene through the public canonical narrator wrapper."""

    narrator = SceneNarrator(
        llm_gateway=llm_gateway,
        default_tone=tone,
        simulate_mode=not bool(llm_gateway),
    )
    result = narrator.narrate_scene(scene, state, tone=tone)
    return {
        "narrative": result.narrative,
        "choices": result.choices,
        "npc_reactions": [
            {
                "npc_id": row.npc_id,
                "npc_name": row.npc_name,
                "dialogue": row.dialogue,
                "emotion": row.emotion,
                "intent": row.intent,
            }
            for row in result.npc_reactions
        ],
        "dialogue_blocks": result.dialogue_blocks,
        "metadata": result.metadata,
    }


def _response_mode(
    context: Mapping[str, Any],
    narration_json: Mapping[str, Any],
) -> ResponseMode:
    resolved = _mapping(context.get("resolved_result"))
    contract = _mapping(context.get("turn_contract"))
    return coerce_response_mode(
        narration_json.get("response_mode")
        or context.get("response_mode")
        or resolved.get("response_mode")
        or resolved.get("semantic_family")
        or contract.get("semantic_family")
        or resolved.get("action_type")
        or contract.get("action_type"),
        ResponseMode.RECOVERY
        if str(context.get("resolver_status") or "").casefold()
        in {"unresolved", "partial", "unsupported", "no_match"}
        else ResponseMode.ACTION,
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
