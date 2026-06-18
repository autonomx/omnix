"""Passive ability hooks and grounded narrative trait helpers.

N124 rule: passive abilities and narrative traits may influence gameplay only
through saved deterministic hooks, tags, affordance candidates, or validated
ability effect operations. Freeform AI text must not mutate mechanics.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.rpg.session.ability_system import execute_effect_ops

SUPPORTED_PASSIVE_HOOKS = {
    "on_turn_start",
    "on_turn_end",
    "on_enter_location",
    "on_investigation_check",
    "on_social_check",
    "on_combat_start",
    "on_trade",
    "on_rest",
    "on_quest_update",
}


class RpgPassiveHookResult(BaseModel):
    ok: bool
    hook: str
    detail: str
    error: str | None = None
    applied: list[dict[str, Any]] = Field(default_factory=list)
    effects: list[dict[str, Any]] = Field(default_factory=list)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _norm(value: Any) -> str:
    return str(value or "").strip().casefold().replace(" ", "_")


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _append(target: dict[str, Any], key: str, value: dict[str, Any], limit: int = 40) -> None:
    values = _safe_list(target.get(key))
    values.insert(0, value)
    target[key] = values[:limit]


def _ability_records(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [_safe_dict(ability) for ability in _safe_list(_safe_dict(state.get("ability_tree")).get("abilities"))]


def _unlocked_records(state: dict[str, Any], *, kind: str | None = None) -> list[dict[str, Any]]:
    ability_state = _safe_dict(state.get("ability_state"))
    unlocked = {str(value) for value in _safe_list(ability_state.get("unlocked"))}
    records: list[dict[str, Any]] = []
    for ability in _ability_records(state):
        ability_id = str(ability.get("ability_id") or "")
        if not ability_id or ability_id not in unlocked:
            continue
        if kind is not None and ability.get("kind") != kind:
            continue
        records.append(ability)
    return records


def _rank_for_ability(state: dict[str, Any], ability: dict[str, Any]) -> int:
    ability_state = _safe_dict(state.get("ability_state"))
    ranks = _safe_dict(ability_state.get("ranks"))
    ability_id = str(ability.get("ability_id") or "")
    rank = max(1, _safe_int(ranks.get(ability_id), _safe_int(ability.get("rank"), 1)))
    max_rank = max(1, _safe_int(ability.get("max_rank"), 1))
    return min(rank, max_rank)


def _record_passive_modifier(
    state: dict[str, Any],
    ability: dict[str, Any],
    *,
    hook: str,
    context: dict[str, Any],
    rank: int,
) -> dict[str, Any] | None:
    check = str(context.get("check") or "").strip()
    if not check and not hook.endswith("_check"):
        return None
    modifier = {
        "source": ability.get("name"),
        "ability_id": ability.get("ability_id"),
        "hook": hook,
        "check": check or hook.replace("on_", "").replace("_check", ""),
        "amount": rank,
        "capability": ability.get("capability"),
        "dimensions": list(_safe_list(ability.get("dimensions"))),
        "created_at": _utc_now(),
    }
    runtime = _safe_dict(state.get("runtime"))
    _append(runtime, "passive_modifiers", modifier, limit=80)
    state["runtime"] = runtime
    return modifier


def _record_passive_affordance(
    state: dict[str, Any],
    ability: dict[str, Any],
    *,
    hook: str,
    context: dict[str, Any],
    rank: int,
) -> dict[str, Any]:
    tag = f"{ability.get('ability_id')}:{hook}"
    record = {
        "source": ability.get("name"),
        "ability_id": ability.get("ability_id"),
        "hook": hook,
        "tag": tag,
        "rank": rank,
        "capability": ability.get("capability"),
        "dimensions": list(_safe_list(ability.get("dimensions"))),
        "context_tags": list(_safe_list(context.get("tags"))) or list(_safe_list(context.get("scene_tags"))),
        "created_at": _utc_now(),
    }
    affordances = _safe_dict(state.get("narrative_affordances"))
    _append(affordances, "passive", record, limit=80)
    state["narrative_affordances"] = affordances
    return record


def apply_passive_hooks_to_state(
    state: dict[str, Any],
    hook: str,
    context: dict[str, Any] | None = None,
) -> RpgPassiveHookResult:
    """Apply unlocked passive abilities for a deterministic gameplay hook.

    Hook-only passives write traceable modifier and affordance candidates.
    Passives with effect_ops execute those validated operations through the
    same deterministic executor used by active abilities.
    """
    hook_key = _norm(hook)
    if hook_key not in SUPPORTED_PASSIVE_HOOKS:
        return RpgPassiveHookResult(ok=False, hook=hook_key, detail=f"Unsupported passive hook: {hook}", error="unsupported_passive_hook")

    context_payload = deepcopy(_safe_dict(context))
    applied: list[dict[str, Any]] = []
    effects: list[dict[str, Any]] = []
    for ability in _unlocked_records(state, kind="passive"):
        ability_hooks = {_norm(value) for value in _safe_list(ability.get("hooks"))}
        if hook_key not in ability_hooks:
            continue
        rank = _rank_for_ability(state, ability)
        ranked_ability = deepcopy(ability)
        ranked_ability["rank"] = rank
        modifier = _record_passive_modifier(state, ranked_ability, hook=hook_key, context=context_payload, rank=rank)
        affordance = _record_passive_affordance(state, ranked_ability, hook=hook_key, context=context_payload, rank=rank)
        ability_effects: list[dict[str, Any]] = []
        if _safe_list(ranked_ability.get("effect_ops")):
            ability_effects = execute_effect_ops(
                state,
                ranked_ability,
                target=str(context_payload.get("target") or "the current situation"),
            )
            effects.extend(ability_effects)
        trace = {
            "ability_id": ranked_ability.get("ability_id"),
            "ability_name": ranked_ability.get("name"),
            "hook": hook_key,
            "rank": rank,
            "capability": ranked_ability.get("capability"),
            "dimensions": list(_safe_list(ranked_ability.get("dimensions"))),
            "context": context_payload,
            "modifier": modifier,
            "affordance": affordance,
            "effects": ability_effects,
            "created_at": _utc_now(),
        }
        mechanics = _safe_dict(state.get("mechanics"))
        _append(mechanics, "passive_hook_trace", trace, limit=80)
        state["mechanics"] = mechanics
        applied.append(trace)

    detail = f"Applied {len(applied)} passive hook(s) for {hook_key}."
    return RpgPassiveHookResult(ok=True, hook=hook_key, detail=detail, applied=applied, effects=effects)


def collect_narrative_trait_context(state: dict[str, Any]) -> dict[str, Any]:
    """Return grounded context for unlocked narrative traits without mutation."""
    traits: list[dict[str, Any]] = []
    influence_tags: list[str] = []
    affordance_candidates: list[dict[str, Any]] = []
    for ability in _unlocked_records(state, kind="narrative_trait"):
        tags = [str(value) for value in _safe_list(ability.get("influence_tags")) if str(value).strip()]
        hooks = [str(value) for value in _safe_list(ability.get("hooks")) if str(value).strip()]
        trait = {
            "trait_id": ability.get("ability_id"),
            "ability_id": ability.get("ability_id"),
            "name": ability.get("name"),
            "description": ability.get("description"),
            "dimensions": list(_safe_list(ability.get("dimensions"))),
            "capability": ability.get("capability"),
            "power_source": ability.get("power_source"),
            "purpose": ability.get("purpose"),
            "influence_tags": tags,
            "hooks": hooks,
            "source": "unlocked_narrative_trait",
        }
        traits.append(trait)
        for tag in tags:
            if tag not in influence_tags:
                influence_tags.append(tag)
            affordance_candidates.append(
                {
                    "tag": tag,
                    "trait_id": ability.get("ability_id"),
                    "source": ability.get("name"),
                    "dimensions": list(_safe_list(ability.get("dimensions"))),
                }
            )
    return {
        "traits": traits,
        "influence_tags": influence_tags,
        "affordance_candidates": affordance_candidates,
        "count": len(traits),
    }
