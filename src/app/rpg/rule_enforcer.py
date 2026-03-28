"""
Rule Enforcer for the AI Role-Playing System.

Handles both pre-validation (reject invalid actions) and post-validation
(ensure LLM output consistency). Includes hard-coded checks that don't
require LLM calls for common violations.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.rpg.models import GameSession, PlayerIntent

logger = logging.getLogger(__name__)


def _check_forbidden_items(text: str, forbidden: List[str]) -> Optional[str]:
    """Check if text references any forbidden items."""
    text_lower = text.lower()
    for item in forbidden:
        item_lower = item.lower()
        # Check the item as-is and common singular/plural variations
        forms = {item_lower}
        if item_lower.endswith("es") and len(item_lower) > 3:
            forms.add(item_lower[:-2])  # "explosives" -> "explosiv" (approximate)
        if item_lower.endswith("s") and not item_lower.endswith("ss"):
            forms.add(item_lower[:-1])  # "guns" -> "gun", but not "glass" -> "glas"
        if not item_lower.endswith("s"):
            forms.add(item_lower + "s")  # "gun" -> "guns"
        for form in forms:
            if form in text_lower:
                return f"'{item}' does not exist in this world"
    return None


def _check_location_valid(session: GameSession, target_location: str) -> Optional[str]:
    """Check if a location move is valid (connected to current location)."""
    current_loc = session.world.get_location(session.player.location)
    if not current_loc:
        return None  # Can't validate if current location unknown

    target_lower = target_location.lower()
    connected_lower = [c.lower() for c in current_loc.connected_to]
    if target_lower not in connected_lower:
        available = ", ".join(current_loc.connected_to)
        return f"Cannot reach '{target_location}' from '{current_loc.name}'. Available exits: {available}"
    return None


def _check_inventory_has_item(inventory: List[str], item: str) -> Optional[str]:
    """Check if an item exists in inventory."""
    item_lower = item.lower()
    for inv_item in inventory:
        if inv_item.lower() == item_lower:
            return None
    return f"You don't have '{item}' in your inventory"


def _check_economy(intent: Dict[str, Any], session: GameSession) -> Optional[str]:
    """Check if a transaction is economically feasible."""
    if intent.get("intent") == "buy_item":
        offer = intent.get("details", {}).get("offer", 0)
        if isinstance(offer, (int, float)) and offer > session.player.stats.wealth:
            return f"You only have {session.player.stats.wealth} gold but offered {offer}"
    return None


def _check_npc_present(session: GameSession, npc_name: str) -> Optional[str]:
    """Check if an NPC is at the player's current location."""
    npcs_here = session.get_npcs_at_location(session.player.location)
    npc_names_lower = [npc.name.lower() for npc in npcs_here]
    if npc_name.lower() not in npc_names_lower:
        present = ", ".join(npc.name for npc in npcs_here) if npcs_here else "no one"
        return f"'{npc_name}' is not here. Present: {present}"
    return None


# Hard constraint patterns that are always rejected (no LLM needed)
EXPLOIT_PATTERNS = [
    (re.compile(r"\bignore\b.*\brules?\b", re.IGNORECASE), "Cannot override world rules"),
    (re.compile(r"\byou are now\b", re.IGNORECASE), "Cannot redefine game entities"),
    (re.compile(r"\bforget\b.*\binstructions?\b", re.IGNORECASE), "Cannot override system instructions"),
    (re.compile(r"\bsystem\b.*\bprompt\b", re.IGNORECASE), "Cannot access system configuration"),
    (re.compile(r"\bteleport\b", re.IGNORECASE), "Teleportation is not available unless magic permits"),
]


def pre_validate_hard(raw_input: str, intent: Dict[str, Any], session: GameSession) -> Tuple[bool, Optional[str]]:
    """
    Hard pre-validation that doesn't require LLM.
    Returns (is_valid, error_message).
    """
    # Check for prompt injection / exploit attempts
    for pattern, message in EXPLOIT_PATTERNS:
        if pattern.search(raw_input):
            return False, message

    # Check forbidden items
    forbidden = session.world.rules.forbidden_items
    item_err = _check_forbidden_items(raw_input, forbidden)
    if item_err:
        return False, item_err

    intent_type = intent.get("intent", "")
    target = intent.get("target", "")

    # Location checks for movement
    if intent_type == "move" and target:
        loc_err = _check_location_valid(session, target)
        if loc_err:
            return False, loc_err

    # Economy checks
    econ_err = _check_economy(intent, session)
    if econ_err:
        return False, econ_err

    # NPC presence checks for interaction intents
    if intent_type in ("talk", "buy_item", "sell_item", "persuade", "attack") and target:
        npc_err = _check_npc_present(session, target)
        if npc_err:
            return False, npc_err

    # Inventory checks for item usage
    if intent_type in ("use_item", "sell_item", "drop") and target:
        inv_err = _check_inventory_has_item(session.player.inventory, target)
        if inv_err:
            return False, inv_err

    return True, None


def post_validate_hard(event_outcome: Dict[str, Any], session: GameSession) -> Tuple[bool, List[str]]:
    """
    Hard post-validation of event outcomes.
    Returns (is_valid, list_of_issues).
    """
    issues = []

    # Check forbidden items in outcome
    outcome_text = event_outcome.get("outcome", "")
    forbidden = session.world.rules.forbidden_items
    item_err = _check_forbidden_items(outcome_text, forbidden)
    if item_err:
        issues.append(f"Outcome references forbidden content: {item_err}")

    # Verify stat check consistency
    stat_check = event_outcome.get("stat_check", {})
    if stat_check:
        stat_name = stat_check.get("stat_used", "")
        difficulty = stat_check.get("difficulty", 0)
        player_value = stat_check.get("player_value", 0)
        passed = stat_check.get("passed", False)

        if stat_name and isinstance(difficulty, (int, float)) and isinstance(player_value, (int, float)):
            expected_pass = player_value >= difficulty
            if passed != expected_pass:
                issues.append(
                    f"Stat check inconsistency: {stat_name} {player_value} vs difficulty {difficulty} "
                    f"should {'pass' if expected_pass else 'fail'}"
                )

    return len(issues) == 0, issues
