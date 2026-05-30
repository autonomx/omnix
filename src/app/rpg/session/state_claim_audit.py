from __future__ import annotations

import re
from typing import Any, Dict, List


def _d(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _l(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _s(value: Any) -> str:
    return "" if value is None else str(value)


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", _s(value)).strip()


def _first_dict(*values: Any) -> Dict[str, Any]:
    for value in values:
        candidate = _d(value)
        if candidate:
            return candidate
    return {}


def _collect_text(result: Dict[str, Any]) -> str:
    result = _d(result)
    nested = _d(result.get("result"))
    payload = _first_dict(
        result.get("narration_payload"),
        result.get("structured_narration"),
        result.get("combat_narration_payload"),
        nested.get("narration_payload"),
        nested.get("structured_narration"),
        nested.get("combat_narration_payload"),
    )
    npc = _first_dict(result.get("npc"), nested.get("npc"), payload.get("npc"))
    parts = [
        result.get("final_narration"),
        result.get("narration"),
        result.get("summary"),
        nested.get("final_narration"),
        nested.get("narration"),
        nested.get("summary"),
        payload.get("narration"),
        npc.get("line"),
    ]
    return _norm("\n".join(_s(part) for part in parts if _s(part).strip()))


def _combat_state(result: Dict[str, Any]) -> Dict[str, Any]:
    result = _d(result)
    nested = _d(result.get("result"))
    session = _first_dict(result.get("session"), nested.get("session"))
    runtime_state = _first_dict(
        result.get("runtime_state"),
        nested.get("runtime_state"),
        session.get("runtime_state"),
    )
    return _first_dict(
        result.get("combat_state"),
        nested.get("combat_state"),
        runtime_state.get("combat_state"),
    )


def _inventory_state(result: Dict[str, Any]) -> Dict[str, Any]:
    result = _d(result)
    nested = _d(result.get("result"))
    player = _first_dict(
        result.get("player_state"),
        nested.get("player_state"),
        _d(result.get("simulation_state")).get("player_state"),
        _d(nested.get("simulation_state")).get("player_state"),
    )
    return _first_dict(
        result.get("inventory_state"),
        nested.get("inventory_state"),
        player.get("inventory_state"),
        player.get("inventory"),
    )


def _location_id(result: Dict[str, Any]) -> str:
    result = _d(result)
    nested = _d(result.get("result"))
    player = _first_dict(
        result.get("player_state"),
        nested.get("player_state"),
        _d(result.get("simulation_state")).get("player_state"),
        _d(nested.get("simulation_state")).get("player_state"),
    )
    return _s(
        result.get("location_id")
        or nested.get("location_id")
        or player.get("location_id")
        or _d(result.get("current_location")).get("id")
        or _d(nested.get("current_location")).get("id")
    ).strip()


def _has_inventory_items(inventory: Dict[str, Any]) -> bool:
    items = inventory.get("items")
    if isinstance(items, dict):
        return bool(items)
    return bool(_l(items))


def _combat_defeat_contradiction(text: str, combat: Dict[str, Any]) -> str:
    if not combat:
        return ""
    lowered = text.casefold()
    claims_defeat = any(
        phrase in lowered
        for phrase in (
            "defeated",
            "slain",
            "killed",
            "dead",
            "falls dead",
            "is down",
            "drops to the ground",
        )
    )
    if not claims_defeat:
        return ""
    defeated = bool(
        combat.get("defeated")
        or combat.get("enemy_defeated")
        or combat.get("combat_ended")
        or combat.get("ended")
    )
    active = bool(combat.get("active"))
    enemy_hp = combat.get("enemy_hp") or combat.get("target_hp") or combat.get("hp")
    if defeated:
        return ""
    if active or (isinstance(enemy_hp, (int, float)) and enemy_hp > 0):
        return "narration_claims_defeat_but_combat_state_does_not"
    return ""


def audit_final_result_hard_state_claims(result: Dict[str, Any]) -> Dict[str, Any]:
    """Best-effort hard state claim audit for final visible RPG output.

    This is intentionally conservative. It is Phase 0 scaffolding, not a full NLP
    validator. It extracts obvious hard-state claim categories from visible text
    and reports contradictions only when deterministic state clearly disagrees.
    """

    result = _d(result)
    text = _collect_text(result)
    lowered = text.casefold()
    combat = _combat_state(result)
    inventory = _inventory_state(result)
    location_id = _location_id(result)

    claims: List[Dict[str, Any]] = []
    warnings: List[str] = []
    critical: List[str] = []

    def add_claim(category: str, evidence: str) -> None:
        claims.append({"category": category, "evidence": evidence})

    if any(term in lowered for term in ("gold", "silver", "copper", "coins", "paid", "spend", "spent")):
        add_claim("currency", "visible_text_mentions_currency_or_payment")
    if any(term in lowered for term in ("you receive", "you take", "you gain", "added to your pack", "inventory")):
        add_claim("inventory", "visible_text_mentions_inventory_gain_or_item_state")
        if not _has_inventory_items(inventory):
            warnings.append("inventory_claim_present_without_visible_inventory_evidence")
    if any(term in lowered for term in ("arrive", "travel", "road", "location", "old mill", "tavern")):
        add_claim("location", "visible_text_mentions_location_or_travel")
        if not location_id:
            warnings.append("location_claim_present_without_visible_location_evidence")
    if any(term in lowered for term in ("quest", "objective", "reward", "contract", "job")):
        add_claim("quest", "visible_text_mentions_quest_or_reward")
    if any(term in lowered for term in ("defeated", "slain", "killed", "dead", "damage", "wound")):
        add_claim("combat", "visible_text_mentions_combat_state")
    if any(term in lowered for term in ("joins you", "companion", "party", "follows you")):
        add_claim("party", "visible_text_mentions_party_or_companion_state")

    contradiction = _combat_defeat_contradiction(text, combat)
    if contradiction:
        critical.append(contradiction)

    return {
        "source": "phase0_hard_state_claim_audit_v1",
        "ok": not critical,
        "claim_count": len(claims),
        "claims": claims,
        "warnings": warnings,
        "critical": critical,
        "visible_text_present": bool(text),
        "audited_categories": ["currency", "inventory", "location", "quest", "combat", "party"],
    }
