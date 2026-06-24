"""Runtime narration quality and prompt profile metadata for RPG Phase 18."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.rpg.narration_quality import build_safe_rewrite_contract, evaluate_narration_quality
from app.rpg.prompt_profiles import (
    RpgPromptProfile,
    RpgPromptTask,
    default_rpg_prompt_profile_registry,
    rpg_prompt_profile_debug_payload,
)

PHASE18_NARRATION_PROMPT_SOURCE = "phase18_narration_prompt_runtime_v1"
_ACTION_PROMPT_TASKS: Mapping[str, RpgPromptTask] = {
    "talk": "npc_dialogue",
    "dialogue": "npc_dialogue",
    "conversation": "npc_dialogue",
    "memory": "memory_summary",
    "journal": "journal_recap",
    "combat": "combat_narration",
}


def build_narration_prompt_runtime_metadata(
    *,
    narration: str,
    action_kind: str,
    state_facts: Mapping[str, object] | None = None,
    recent_texts: Sequence[str] = (),
    prompt_registry: Mapping[RpgPromptTask, RpgPromptProfile] | None = None,
) -> dict[str, object]:
    """Build runtime-safe prompt and narration metadata for one resolved turn."""

    registry = prompt_registry or default_rpg_prompt_profile_registry()
    quality = evaluate_narration_quality(narration, recent_texts=recent_texts)
    narration_task = prompt_task_for_action(action_kind)
    profiles = [
        rpg_prompt_profile_debug_payload("intent_classification", registry=registry, status="runtime_selected"),
        rpg_prompt_profile_debug_payload(narration_task, registry=registry, status="runtime_selected"),
    ]
    rewrite_contract = None
    if quality.should_request_rewrite:
        rewrite_contract = build_safe_rewrite_contract(
            narration,
            state_facts=state_facts,
            quality_report=quality,
        )
        profiles.append(rpg_prompt_profile_debug_payload("quality_rewrite", registry=registry, status="rewrite_recommended"))
    profiles.append(rpg_prompt_profile_debug_payload("grounding_audit", registry=registry, status="background_audit"))
    return {
        "source": PHASE18_NARRATION_PROMPT_SOURCE,
        "action_kind": action_kind,
        "narration_task": narration_task,
        "narration_quality": quality.as_dict(),
        "rewrite_contract": rewrite_contract,
        "rewrite_recommended": quality.should_request_rewrite,
        "selected_prompt_profiles": profiles,
        "provider_dispatch_ready": all(profile.get("provider") and profile.get("model") for profile in profiles),
        "state_mutation_allowed": False,
    }


def prompt_task_for_action(action_kind: str) -> RpgPromptTask:
    normalized = (action_kind or "").strip().lower()
    return _ACTION_PROMPT_TASKS.get(normalized, "narration")
