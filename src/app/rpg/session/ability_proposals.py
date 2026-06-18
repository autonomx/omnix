"""AI ability-tree proposal compiler for RPG sessions.

The AI may propose fiction: class names, category names, ability names,
descriptions, and flavor tags. The deterministic engine keeps ownership of
mechanics: costs, cooldowns, level gates, prerequisites, resources, status
rules, and effect operations.

This module compiles AI-proposed fiction onto validated template mechanics so
custom genres can feel bespoke without letting freeform output mutate gameplay
rules.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import BaseModel, Field

from app.rpg.session.ability_system import (
    ALLOWED_CAPABILITIES,
    ALLOWED_PURPOSES,
    build_ability_tree,
    infer_character_identity,
    normalize_capability,
    validate_ability_tree,
)

ENGINE_OWNED_PROPOSAL_FIELDS = {
    "effect_ops",
    "resource_cost",
    "cooldown_turns",
    "level_required",
    "rank",
    "max_rank",
    "prerequisites",
    "targeting",
}
MAX_GENERATED_TEXT_LENGTH = 320


class RpgAbilityTreeProposalResult(BaseModel):
    ok: bool
    source: str
    tree: dict[str, Any]
    fallback_used: bool = False
    accepted_fiction_count: int = 0
    repairs: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _clean_text(value: Any, *, max_length: int = MAX_GENERATED_TEXT_LENGTH) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = " ".join(value.strip().split())
    return cleaned[:max_length]


def _clean_tags(value: Any) -> list[str]:
    tags: list[str] = []
    for item in _safe_list(value):
        tag = _clean_text(item, max_length=64).casefold().replace(" ", "_")
        if tag and tag not in tags:
            tags.append(tag)
    return tags[:12]


def _ability_index(tree: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(ability.get("ability_id")): ability for ability in _safe_list(tree.get("abilities")) if isinstance(ability, dict)}


def _category_by_capability(tree: dict[str, Any], capability: str, used_categories: set[str]) -> dict[str, Any] | None:
    for category in _safe_list(tree.get("categories")):
        if not isinstance(category, dict):
            continue
        category_id = str(category.get("category_id") or category.get("capability") or "")
        if category_id == capability and category_id not in used_categories:
            return category
    return None


def _category_by_position(tree: dict[str, Any], index: int, used_categories: set[str]) -> dict[str, Any] | None:
    categories = [category for category in _safe_list(tree.get("categories")) if isinstance(category, dict)]
    if index < len(categories):
        category = categories[index]
        category_id = str(category.get("category_id") or category.get("capability") or index)
        if category_id not in used_categories:
            return category
    for category in categories:
        category_id = str(category.get("category_id") or category.get("capability") or "")
        if category_id not in used_categories:
            return category
    return None


def _target_category(tree: dict[str, Any], proposed_category: dict[str, Any], index: int, used_categories: set[str]) -> dict[str, Any] | None:
    raw_capability = proposed_category.get("capability")
    capability = normalize_capability(raw_capability, "custom") if raw_capability else None
    if capability and capability in ALLOWED_CAPABILITIES:
        category = _category_by_capability(tree, capability, used_categories)
        if category:
            return category
    return _category_by_position(tree, index, used_categories)


def _target_abilities(category: dict[str, Any], abilities_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for ability_id in _safe_list(category.get("abilities")):
        ability = abilities_by_id.get(str(ability_id))
        if ability:
            targets.append(ability)
    return targets


def _apply_ability_fiction(target: dict[str, Any], proposal: dict[str, Any], repairs: list[str]) -> int:
    accepted = 0
    ability_id = str(target.get("ability_id") or "unknown_ability")
    for field in sorted(ENGINE_OWNED_PROPOSAL_FIELDS):
        if field in proposal:
            repairs.append(f"ignored engine-owned field {field} on {ability_id}")
    name = _clean_text(proposal.get("name"), max_length=72)
    if name:
        target["name"] = name
        accepted += 1
    description = _clean_text(proposal.get("description"), max_length=MAX_GENERATED_TEXT_LENGTH)
    if description:
        target["description"] = description
        accepted += 1
    icon = _clean_text(proposal.get("icon"), max_length=4)
    if icon:
        target["icon"] = icon
        accepted += 1
    purpose = _clean_text(proposal.get("purpose"), max_length=64).casefold().replace(" ", "_")
    if purpose:
        if purpose in ALLOWED_PURPOSES:
            target["purpose"] = purpose
            accepted += 1
        else:
            repairs.append(f"ignored unsupported purpose {purpose} on {ability_id}")
    flavor_tags = _clean_tags(proposal.get("flavor_tags"))
    if flavor_tags:
        current_tags = [str(tag) for tag in _safe_list(target.get("flavor_tags"))]
        for tag in flavor_tags:
            if tag not in current_tags:
                current_tags.append(tag)
        target["flavor_tags"] = current_tags[:16]
        accepted += 1
    return accepted


def _apply_category_fiction(tree: dict[str, Any], proposal: dict[str, Any]) -> tuple[int, list[str]]:
    repairs: list[str] = []
    accepted = 0
    abilities_by_id = _ability_index(tree)
    used_categories: set[str] = set()
    for category_index, proposed_category_raw in enumerate(_safe_list(proposal.get("categories"))):
        proposed_category = _safe_dict(proposed_category_raw)
        if not proposed_category:
            continue
        category = _target_category(tree, proposed_category, category_index, used_categories)
        if not category:
            repairs.append(f"ignored category proposal at index {category_index}: no template category available")
            continue
        category_id = str(category.get("category_id") or category.get("capability") or category_index)
        used_categories.add(category_id)
        category_name = _clean_text(proposed_category.get("name"), max_length=72)
        if category_name:
            category["name"] = category_name
            accepted += 1
        target_abilities = _target_abilities(category, abilities_by_id)
        used_ability_ids: set[str] = set()
        for ability_index, proposed_ability_raw in enumerate(_safe_list(proposed_category.get("abilities"))):
            proposed_ability = _safe_dict(proposed_ability_raw)
            if not proposed_ability:
                continue
            anchor = _clean_text(proposed_ability.get("anchor_ability_id"), max_length=120)
            target = abilities_by_id.get(anchor) if anchor else None
            if not target:
                available = [ability for ability in target_abilities if str(ability.get("ability_id")) not in used_ability_ids]
                target = available[0] if ability_index < len(available) else None
            if not target:
                repairs.append(f"ignored ability proposal at category {category_id} index {ability_index}: no template mechanic available")
                continue
            used_ability_ids.add(str(target.get("ability_id")))
            accepted += _apply_ability_fiction(target, proposed_ability, repairs)
    return accepted, repairs


def compile_ai_ability_tree_proposal(identity: dict[str, Any], proposal: dict[str, Any], *, seed: int | None = None) -> RpgAbilityTreeProposalResult:
    """Compile AI-proposed fiction onto deterministic template mechanics.

    A successful result may use AI fiction, but it never accepts AI-owned
    mechanics. Engine-owned fields in the proposal are ignored and reported in
    repairs. If there is no usable fiction or validation fails, the deterministic
    template tree is returned as a safe fallback.
    """

    fallback_tree = build_ability_tree(identity, seed=seed)
    proposed = _safe_dict(proposal)
    if not proposed:
        return RpgAbilityTreeProposalResult(
            ok=True,
            source=str(fallback_tree.get("source") or "template_fallback"),
            tree=fallback_tree,
            fallback_used=True,
            errors=["empty proposal; used deterministic template fallback"],
        )

    tree = deepcopy(fallback_tree)
    repairs: list[str] = []
    accepted = 0
    class_name = _clean_text(proposed.get("class_name") or proposed.get("generated_class_name"), max_length=72)
    if class_name:
        tree["class_name"] = class_name
        accepted += 1
    class_summary = _clean_text(proposed.get("class_summary") or proposed.get("generated_class_summary"), max_length=MAX_GENERATED_TEXT_LENGTH)
    if class_summary:
        tree["class_summary"] = class_summary
        accepted += 1
    for field in sorted(ENGINE_OWNED_PROPOSAL_FIELDS):
        if field in proposed:
            repairs.append(f"ignored engine-owned field {field} on proposal root")
    category_accepts, category_repairs = _apply_category_fiction(tree, proposed)
    accepted += category_accepts
    repairs.extend(category_repairs)

    if accepted == 0:
        return RpgAbilityTreeProposalResult(
            ok=True,
            source=str(fallback_tree.get("source") or "template_fallback"),
            tree=fallback_tree,
            fallback_used=True,
            repairs=repairs,
            errors=["proposal contained no usable fiction; used deterministic template fallback"],
        )

    tree["source"] = "ai_proposal_validated_v1"
    tree["proposal_trace"] = {
        "accepted_fiction_count": accepted,
        "repairs": repairs,
        "mechanics_source": str(fallback_tree.get("source") or "template"),
        "design_rule": "AI fiction is compiled onto deterministic template mechanics; engine-owned fields are ignored.",
    }
    validation = validate_ability_tree(tree)
    if not validation.ok:
        return RpgAbilityTreeProposalResult(
            ok=True,
            source=str(fallback_tree.get("source") or "template_fallback"),
            tree=fallback_tree,
            fallback_used=True,
            accepted_fiction_count=accepted,
            repairs=repairs,
            errors=["compiled proposal failed validation; used deterministic template fallback", *validation.errors],
        )
    return RpgAbilityTreeProposalResult(ok=True, source="ai_proposal_validated_v1", tree=tree, accepted_fiction_count=accepted, repairs=repairs)


def build_progression_package_from_ai_proposal(request_payload: dict[str, Any], proposal: dict[str, Any], *, build_id: str, level: int = 1, seed: int | None = None) -> dict[str, Any]:
    """Build a progression package from a saved/validated AI proposal.

    This helper is intentionally separate from normal New Game templates. A
    caller must explicitly opt in after obtaining a proposal from an LLM or
    editor. The returned tree is already validated or safely falls back.
    """

    from app.rpg.session.ability_system import build_initial_ability_state  # local import avoids expanding the public surface above

    identity = infer_character_identity(request_payload, build_id=build_id)
    compiled = compile_ai_ability_tree_proposal(identity, proposal, seed=seed)
    tree = compiled.tree
    ability_state = build_initial_ability_state(tree, level=level)
    package = {"character_identity": identity, "ability_tree": tree, "ability_state": ability_state, "hotbar": ability_state["hotbar"]}
    package["ability_tree_proposal_result"] = compiled.model_dump(mode="json", exclude={"tree"})
    return package
