"""
Rule Enforcer for the AI Role-Playing System.

Handles both pre-validation (reject invalid actions) and post-validation
(ensure LLM output consistency). Includes hard-coded checks that don't
require LLM calls for common violations.

Enhanced with: trust-based NPC gating, time-based shop validation,
meta-gaming prevention, and economy price enforcement.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.rpg.models import GameSession, PlayerIntent

logger = logging.getLogger(__name__)

# Trust threshold: NPCs with relationship below this refuse favors/trades
NPC_TRUST_THRESHOLD = -30


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


def _check_npc_trust(session: GameSession, npc_name: str, intent_type: str) -> Optional[str]:
    """Check if NPC trusts the player enough for the requested interaction."""
    npc = session.get_npc(npc_name)
    if not npc:
        return None
    relationship = npc.relationships.get("player", 0)
    # Trust-gated actions: buy, sell, persuade, quest interactions
    if intent_type in ("buy_item", "sell_item", "persuade") and relationship < NPC_TRUST_THRESHOLD:
        return f"{npc.name} does not trust you enough (relationship: {relationship}). Improve your standing first."
    return None


def _check_shop_hours(session: GameSession, intent_type: str) -> Optional[str]:
    """Check if shops/merchants are open at the current time."""
    if intent_type not in ("buy_item", "sell_item"):
        return None
    current_hour = session.world.world_time.hour
    loc = session.world.get_location(session.player.location)
    if loc and current_hour not in loc.shop_open_hours:
        return f"Shops at {loc.name} are closed at this hour ({current_hour:02d}:00). Try during business hours."
    return None


def _check_fail_state(session: GameSession) -> Optional[str]:
    """Check if the player is in a fail state."""
    if not session.player.is_alive:
        return "You are dead. The adventure is over."
    if session.player.fail_state:
        return f"Game over: {session.player.fail_state}"
    return None


# Hard constraint patterns that are always rejected (no LLM needed)
EXPLOIT_PATTERNS = [
    (re.compile(r"\bignore\b.*\brules?\b", re.IGNORECASE), "Cannot override world rules"),
    (re.compile(r"\byou are now\b", re.IGNORECASE), "Cannot redefine game entities"),
    (re.compile(r"\bforget\b.*\binstructions?\b", re.IGNORECASE), "Cannot override system instructions"),
    (re.compile(r"\bsystem\b.*\bprompt\b", re.IGNORECASE), "Cannot access system configuration"),
    (re.compile(r"\bteleport\b", re.IGNORECASE), "Teleportation is not available unless magic permits"),
    # Enhanced anti-prompt-injection patterns
    (re.compile(r"\byou are not bound\b", re.IGNORECASE), "Cannot alter system constraints"),
    (re.compile(r"\bthis is just a game\b", re.IGNORECASE), "Your character doesn't understand that concept."),
    (re.compile(r"\brewrite\b.*\b(lore|world|rules?|history)\b", re.IGNORECASE), "Cannot modify world canon"),
    (re.compile(r"\bpretend\b.*\byou are\b", re.IGNORECASE), "Cannot redefine system entities"),
    (re.compile(r"\bignore\b.*\b(previous|all|your)\b", re.IGNORECASE), "Cannot override system directives"),
    (re.compile(r"\boverride\b.*\b(system|rules?|constraints?)\b", re.IGNORECASE), "Cannot override system"),
    (re.compile(r"\bact as\b.*\b(if|though)\b", re.IGNORECASE), "Cannot redefine system behavior"),
]

# Meta-gaming patterns (player using out-of-character knowledge)
META_GAMING_PATTERNS = [
    (re.compile(r"\bi know\b.*\bsecretly?\b", re.IGNORECASE), "meta_knowledge"),
    (re.compile(r"\bin the game\b", re.IGNORECASE), "meta_reference"),
    (re.compile(r"\bthe (ai|llm|system|algorithm)\b", re.IGNORECASE), "meta_reference"),
]


def _check_meta_gaming(raw_input: str, session: GameSession) -> Optional[str]:
    """Detect meta-gaming attempts where player uses out-of-character knowledge."""
    for pattern, category in META_GAMING_PATTERNS:
        if pattern.search(raw_input):
            if category == "meta_knowledge":
                return "You can only act on knowledge your character has discovered in-game."
            if category == "meta_reference":
                return "Your character doesn't understand that concept."
    return None


def detect_prompt_injection(text: str) -> bool:
    """
    Detect prompt injection attempts in player input.

    Returns True if the text appears to contain a prompt injection.
    """
    # Check against exploit patterns
    for pattern, _ in EXPLOIT_PATTERNS:
        if pattern.search(text):
            return True
    # Check meta-gaming patterns
    for pattern, _ in META_GAMING_PATTERNS:
        if pattern.search(text):
            return True
    return False


def _check_faction_reputation(session: GameSession, npc_name: str) -> Optional[str]:
    """Check if faction reputation blocks interaction with an NPC."""
    npc = session.get_npc(npc_name)
    if not npc:
        return None
    # Find which faction(s) the NPC belongs to
    for faction in session.world.factions:
        if npc_name in faction.members or npc.role in [m.lower() for m in faction.members]:
            faction_rep = session.player.reputation_factions.get(faction.name, 0)
            if faction_rep <= -50:
                return (f"The {faction.name} faction is hostile toward you "
                        f"(reputation: {faction_rep}). {npc.name} refuses to interact.")
    return None


def pre_validate_hard(raw_input: str, intent: Dict[str, Any], session: GameSession) -> Tuple[bool, Optional[str]]:
    """
    Hard pre-validation that doesn't require LLM.
    Returns (is_valid, error_message).
    """
    # Check fail states first
    fail_err = _check_fail_state(session)
    if fail_err:
        return False, fail_err

    # Check for prompt injection / exploit attempts
    for pattern, message in EXPLOIT_PATTERNS:
        if pattern.search(raw_input):
            return False, message

    # Check for meta-gaming
    meta_err = _check_meta_gaming(raw_input, session)
    if meta_err:
        return False, meta_err

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

    # Shop hours check
    shop_err = _check_shop_hours(session, intent_type)
    if shop_err:
        return False, shop_err

    # NPC presence checks for interaction intents
    if intent_type in ("talk", "buy_item", "sell_item", "persuade", "attack") and target:
        npc_err = _check_npc_present(session, target)
        if npc_err:
            return False, npc_err

    # NPC trust checks
    if intent_type in ("buy_item", "sell_item", "persuade") and target:
        trust_err = _check_npc_trust(session, target, intent_type)
        if trust_err:
            return False, trust_err

    # Faction reputation checks
    if intent_type in ("talk", "buy_item", "sell_item", "persuade") and target:
        faction_err = _check_faction_reputation(session, target)
        if faction_err:
            return False, faction_err

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

    # Verify stat check consistency (legacy support for old-style stat checks)
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

    # World consistency: check creatures/entities against lore
    existing = session.world.rules.existing_creatures
    if existing:
        outcome_lower = outcome_text.lower()
        # Only flag if the outcome introduces something clearly new and major
        for creature_indicator in ["dragon", "demon", "angel", "undead", "ghost"]:
            if creature_indicator in outcome_lower:
                creature_in_lore = any(creature_indicator in c.lower() for c in existing)
                if not creature_in_lore:
                    lore_lower = session.world.lore.lower()
                    if creature_indicator not in lore_lower:
                        issues.append(
                            f"Outcome mentions '{creature_indicator}' which is not established in world lore"
                        )

    return len(issues) == 0, issues
