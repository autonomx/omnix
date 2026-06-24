"""Phase 16 integration hardening helpers for RPG parity foundations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from app.rpg.narration_quality import build_safe_rewrite_contract, evaluate_narration_quality
from app.rpg.performance_paths import (
    blocking_tasks,
    classify_turn_task,
    deferred_tasks,
    fast_action_response,
)
from app.rpg.prompt_profiles import (
    RpgPromptProfile,
    RpgPromptTask,
    default_rpg_prompt_profile_registry,
    rpg_prompt_profile_debug_payload,
    validate_rpg_prompt_profile_registry,
)
from app.rpg.replay_contracts import ReplaySnapshot, validate_snapshot
from app.rpg.world_director import DirectorState, director_report_payload, grounded_director_suggestions
from app.rpg.world_packs import FORBIDDEN_OVERLAY_KEYS, ModOverlay, WorldPack, validate_world_pack

REQUIRED_RUNTIME_STATE_KEYS: tuple[str, ...] = (
    "world",
    "player",
    "party",
    "npcs",
    "quests",
    "map",
    "inventory",
    "combat",
    "memory",
)
DEFAULT_INTEGRATION_TASKS: tuple[RpgPromptTask, ...] = (
    "intent_classification",
    "narration",
    "quality_rewrite",
    "grounding_audit",
)
DEFAULT_TURN_TASKS: tuple[str, ...] = (
    "intent_classification",
    "simulation_resolution",
    "grounded_response",
    "memory_summary",
    "journal_recap",
    "visual_prompt",
    "soft_audit",
)


@dataclass(frozen=True)
class Phase16IntegrationInput:
    """Inputs needed to audit one RPG turn without mutating state."""

    narration: str
    action_kind: str
    state_facts: Mapping[str, object] = field(default_factory=dict)
    recent_texts: tuple[str, ...] = ()
    snapshot: ReplaySnapshot | None = None
    world_pack: WorldPack | None = None
    director_state: DirectorState | None = None
    valid_actions: tuple[str, ...] = ()
    prompt_registry: Mapping[RpgPromptTask, RpgPromptProfile] | None = None
    prompt_tasks: tuple[RpgPromptTask, ...] = DEFAULT_INTEGRATION_TASKS
    turn_tasks: tuple[str, ...] = DEFAULT_TURN_TASKS


@dataclass(frozen=True)
class Phase16IntegrationReport:
    """Stable audit payload for connecting Phase 1-15 helper outputs."""

    narration_quality: Mapping[str, object]
    rewrite_contract: Mapping[str, object] | None
    prompt_profiles: tuple[Mapping[str, object], ...]
    prompt_profile_issues: tuple[str, ...]
    fast_action: Mapping[str, object]
    path_report: Mapping[str, object]
    replay_issues: tuple[str, ...]
    world_pack_issues: tuple[str, ...]
    director_payload: Mapping[str, object]
    readiness_issues: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "narration_quality": dict(self.narration_quality),
            "rewrite_contract": dict(self.rewrite_contract) if self.rewrite_contract else None,
            "prompt_profiles": [dict(profile) for profile in self.prompt_profiles],
            "prompt_profile_issues": list(self.prompt_profile_issues),
            "fast_action": dict(self.fast_action),
            "path_report": dict(self.path_report),
            "replay_issues": list(self.replay_issues),
            "world_pack_issues": list(self.world_pack_issues),
            "director_payload": dict(self.director_payload),
            "readiness_issues": list(self.readiness_issues),
        }


def build_phase16_integration_report(payload: Phase16IntegrationInput) -> Phase16IntegrationReport:
    """Build a pure integration-readiness report for one resolved RPG turn."""

    quality = evaluate_narration_quality(payload.narration, recent_texts=payload.recent_texts)
    rewrite = None
    if quality.should_request_rewrite:
        rewrite = build_safe_rewrite_contract(
            payload.narration,
            state_facts=payload.state_facts,
            quality_report=quality,
        )
    registry = payload.prompt_registry or default_rpg_prompt_profile_registry()
    prompt_issues = validate_rpg_prompt_profile_registry(registry)
    profile_payloads = tuple(
        rpg_prompt_profile_debug_payload(task, registry=registry, status="phase16_audit") for task in payload.prompt_tasks
    )
    path_decisions = tuple(classify_turn_task(task) for task in payload.turn_tasks)
    replay_issues = strict_validate_snapshot(payload.snapshot) if payload.snapshot else ("missing_snapshot",)
    pack_issues = strict_validate_world_pack(payload.world_pack) if payload.world_pack else ("missing_world_pack",)
    director_payload, director_issues = _director_readiness(payload.director_state, payload.valid_actions)
    readiness = tuple(
        issue
        for group in (quality_guard_issues(quality.as_dict()), prompt_issues, replay_issues, pack_issues, director_issues)
        for issue in group
    )
    return Phase16IntegrationReport(
        narration_quality=quality.as_dict(),
        rewrite_contract=rewrite,
        prompt_profiles=profile_payloads,
        prompt_profile_issues=prompt_issues,
        fast_action=fast_action_response(payload.action_kind),
        path_report={
            "decisions": [decision.as_dict() for decision in path_decisions],
            "blocking_tasks": list(blocking_tasks(path_decisions)),
            "deferred_tasks": list(deferred_tasks(path_decisions)),
        },
        replay_issues=replay_issues,
        world_pack_issues=pack_issues,
        director_payload=director_payload,
        readiness_issues=readiness,
    )


def strict_validate_snapshot(snapshot: ReplaySnapshot) -> tuple[str, ...]:
    """Require all runtime state groups promised by the parity roadmap."""

    issues = list(validate_snapshot(snapshot))
    for key in REQUIRED_RUNTIME_STATE_KEYS:
        if key not in snapshot.state:
            marker = f"missing_state:{key}"
            if marker not in issues:
                issues.append(marker)
    if snapshot.seed is None:
        issues.append("missing_seed")
    if not snapshot.counters:
        issues.append("missing_rng_counters")
    return tuple(issues)


def strict_validate_world_pack(pack: WorldPack) -> tuple[str, ...]:
    """Validate pack basics plus nested overlay state-mutation guardrails."""

    issues = list(validate_world_pack(pack))
    for overlay in pack.overlays:
        issues.extend(_deep_overlay_issues(overlay))
    return tuple(dict.fromkeys(issues))


def quality_guard_issues(quality_payload: Mapping[str, object]) -> tuple[str, ...]:
    if quality_payload.get("should_request_rewrite"):
        return ("narration_rewrite_required",)
    return ()


def _director_readiness(
    state: DirectorState | None,
    valid_actions: Sequence[str],
) -> tuple[Mapping[str, object], tuple[str, ...]]:
    if state is None:
        return {"suggested_actions": []}, ("missing_director_state",)
    payload = director_report_payload(state, valid_actions)
    valid_set = set(valid_actions)
    raw_suggestions = grounded_director_suggestions(state, valid_actions)
    invalid = tuple(item for item in raw_suggestions if item not in valid_set and not item.startswith(("Address ", "Advance ")))
    issues = tuple(f"invalid_director_suggestion:{item}" for item in invalid)
    return payload, issues


def _deep_overlay_issues(overlay: ModOverlay) -> tuple[str, ...]:
    hits = _forbidden_paths(overlay.payload)
    return tuple(f"forbidden_overlay_path:{overlay.overlay_id}:{path}" for path in hits)


def _forbidden_paths(value: object, prefix: str = "payload") -> tuple[str, ...]:
    if isinstance(value, Mapping):
        found: list[str] = []
        for key, item in value.items():
            path = f"{prefix}.{key}"
            if str(key) in FORBIDDEN_OVERLAY_KEYS:
                found.append(path)
            found.extend(_forbidden_paths(item, path))
        return tuple(found)
    if isinstance(value, (list, tuple)):
        found = []
        for index, item in enumerate(value):
            found.extend(_forbidden_paths(item, f"{prefix}[{index}]"))
        return tuple(found)
    return ()
