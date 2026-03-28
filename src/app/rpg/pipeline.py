"""
Turn Execution Pipeline for the AI Role-Playing System.

Orchestrates the turn execution with integrated systems:
1. Fail state check
2. Input Normalization
3. Rule Validation (Pre-LLM)
4. Dice Roll (skill check)
5. Context Assembly
6. Event Generation
7. State Update + NPC Autonomy
8. Memory Update (with importance scoring)
9. Narrative Direction
10. Narration Output
11. Fail State Detection
"""

import logging
import random
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.rpg import agents
from app.rpg.memory_manager import build_context
from app.rpg.models import (
    AgentProfile,
    Faction,
    GameSession,
    HistoryEvent,
    Item,
    Location,
    NPCCharacter,
    PlayerIntent,
    PlayerState,
    Quest,
    TurnResult,
    WorldRules,
    WorldState,
    WorldTime,
    skill_check,
)
from app.rpg.persistence import save_game
from app.rpg.rule_enforcer import post_validate_hard, pre_validate_hard

logger = logging.getLogger(__name__)

# Mapping of intents to the stat used for skill checks
INTENT_STAT_MAP = {
    "attack": "strength",
    "persuade": "charisma",
    "sneak": "intelligence",
    "pick_up": "strength",
    "use_item": "intelligence",
}

# Difficulty defaults for common actions
INTENT_DIFFICULTY_MAP = {
    "attack": 6,
    "persuade": 6,
    "sneak": 7,
    "pick_up": 3,
    "use_item": 4,
}

# Fail state thresholds
BANKRUPTCY_THRESHOLD = -100
REPUTATION_COLLAPSE_THRESHOLD = -50


def create_new_game(seed: Optional[int] = None, genre: str = "medieval fantasy",
                    player_name: str = "Player") -> Optional[GameSession]:
    """
    Create a new game session with a freshly generated world.

    Uses the World Builder agent to generate the world, then initializes
    the game session with all state.
    """
    if seed is None:
        seed = random.randint(1, 999999)

    logger.info("Creating new game with seed=%d, genre=%s", seed, genre)

    # Step 1: Generate world via World Builder agent
    world_data = agents.build_world(seed, genre)
    if not world_data:
        logger.error("World Builder agent failed to generate world")
        return None

    # Build world state from LLM output
    world = WorldState(
        seed=seed,
        genre=genre,
        name=world_data.get("name", f"World-{seed}"),
        description=world_data.get("description", "A mysterious world awaits..."),
        lore=world_data.get("lore", ""),
        rules=WorldRules.from_dict(world_data.get("rules", {})),
        locations=[Location.from_dict(loc) for loc in world_data.get("locations", [])],
        world_time=WorldTime(hour=8, day=1, season="spring"),
    )

    # Build factions
    world.factions = [Faction.from_dict(fac) for fac in world_data.get("factions", [])]

    # Build items catalog
    world.items_catalog = [Item.from_dict(i) for i in world_data.get("items_catalog", [])]

    # Build agent profiles for consistent tone
    for key, profile_data in world_data.get("agent_profiles", {}).items():
        world.agent_profiles[key] = AgentProfile.from_dict(profile_data)

    # Build NPCs
    npcs = [NPCCharacter.from_dict(npc) for npc in world_data.get("npcs", [])]

    # Determine starting location
    starting_location = world_data.get("starting_location", "")
    if not starting_location and world.locations:
        starting_location = world.locations[0].name

    # Create player
    player = PlayerState(
        name=player_name,
        location=starting_location,
    )

    # Create session
    session = GameSession(
        world=world,
        player=player,
        npcs=npcs,
    )

    # Save immediately
    save_game(session)

    logger.info("New game created: session_id=%s, world=%s", session.session_id, world.name)
    return session


def execute_turn(session: GameSession, raw_input: str) -> TurnResult:
    """
    Execute a single turn of the game.

    Enhanced pipeline with dice rolls, NPC autonomy, narrative direction, and fail states.
    """
    session.turn_count += 1
    logger.info("Turn %d: player input='%s'", session.turn_count, raw_input)

    # -----------------------------------------------------------------------
    # Step 1: Input Normalization
    # -----------------------------------------------------------------------
    context = build_context(session)
    intent_data = agents.normalize_input(raw_input, context)

    if not intent_data:
        return TurnResult(
            narration="Narrator: The world seems to pause, unsure of your intentions. Please try again.",
            error="Failed to understand your action. Try being more specific.",
        )

    intent = PlayerIntent(
        raw_input=raw_input,
        intent=intent_data.get("intent", "other"),
        target=intent_data.get("target", ""),
        details=intent_data.get("details", {}),
    )
    logger.info("Intent: %s -> %s", intent.intent, intent.target)

    # -----------------------------------------------------------------------
    # Step 2: Rule Validation (Pre-LLM hard checks)
    # -----------------------------------------------------------------------
    is_valid, error_msg = pre_validate_hard(raw_input, intent_data, session)
    if not is_valid:
        logger.info("Pre-validation failed: %s", error_msg)
        return TurnResult(
            narration=f"Narrator: {error_msg}",
            error=error_msg,
        )

    # LLM-based pre-validation for edge cases
    validation = agents.validate_pre(intent_data, context)
    if validation and not validation.get("valid", True):
        reason = validation.get("reason", "Action not permitted")
        corrections = validation.get("corrections", [])
        msg = reason
        if corrections:
            msg += " " + "; ".join(corrections)
        logger.info("LLM pre-validation failed: %s", msg)
        return TurnResult(
            narration=f"Narrator: {msg}",
            error=msg,
        )

    # -----------------------------------------------------------------------
    # Step 3: Dice Roll (skill check for applicable actions)
    # -----------------------------------------------------------------------
    dice_result = None
    stat_name = INTENT_STAT_MAP.get(intent.intent)
    if stat_name:
        stat_value = getattr(session.player.stats, stat_name, 5)
        difficulty = INTENT_DIFFICULTY_MAP.get(intent.intent, 5)
        dice_result = skill_check(stat_value, difficulty)
        intent_data["skill_check"] = dice_result
        logger.info("Dice roll: d20=%d + %s(%d) = %d vs DC %d -> %s",
                     dice_result["roll"], stat_name, stat_value,
                     dice_result["total"], dice_result["dc"],
                     "PASS" if dice_result["passed"] else "FAIL")

    # -----------------------------------------------------------------------
    # Step 4: Context Assembly (refresh with latest)
    # -----------------------------------------------------------------------
    context = build_context(session)
    intent_data["player_stats"] = session.player.stats.to_dict()

    # -----------------------------------------------------------------------
    # Step 5: Event Generation
    # -----------------------------------------------------------------------
    agent_profiles = {k: v.to_dict() for k, v in session.world.agent_profiles.items()}
    event_outcome = agents.generate_event(intent_data, context, agent_profiles)
    if not event_outcome:
        return TurnResult(
            narration="Narrator: Something unexpected happens... the moment passes without consequence.",
            error="Event generation failed",
        )

    # -----------------------------------------------------------------------
    # Post-validation of event outcome
    # -----------------------------------------------------------------------
    post_valid, post_issues = post_validate_hard(event_outcome, session)
    if not post_valid:
        logger.warning("Post-validation issues: %s", post_issues)

    # -----------------------------------------------------------------------
    # Step 6: State Update
    # -----------------------------------------------------------------------
    state_changes = _apply_state_updates(session, intent, event_outcome, context)

    # -----------------------------------------------------------------------
    # Step 7: NPC Autonomy Simulation
    # -----------------------------------------------------------------------
    _simulate_npcs(session)

    # -----------------------------------------------------------------------
    # Step 8: Memory Update (with importance scoring)
    # -----------------------------------------------------------------------
    event_description = event_outcome.get("outcome", raw_input)
    importance = event_outcome.get("importance", 0.5)
    tags = event_outcome.get("tags", [])
    _update_memory(session, event_description)

    # -----------------------------------------------------------------------
    # Step 9: Narrative Direction
    # -----------------------------------------------------------------------
    _update_narrative(session)

    # -----------------------------------------------------------------------
    # Step 10: Narration Output
    # -----------------------------------------------------------------------
    narration_context = build_context(session)
    narration = agents.narrate(event_outcome, narration_context, agent_profiles)
    if not narration:
        narration = f"Narrator: {event_outcome.get('outcome', 'Something happens...')}"
        npc_reactions = event_outcome.get("npc_reactions", [])
        for reaction in npc_reactions:
            narration += f"\n\n{reaction.get('name', 'Someone')}: {reaction.get('reaction', '...')}"

    # Add dice roll info to narration if applicable
    if dice_result:
        roll_info = (
            f"\n\n[Roll: d20({dice_result['roll']}) + "
            f"{stat_name}({dice_result['stat_value']}) = "
            f"{dice_result['total']} vs DC {dice_result['dc']}"
        )
        if dice_result["critical_success"]:
            roll_info += " \u2014 CRITICAL SUCCESS!]"
        elif dice_result["critical_failure"]:
            roll_info += " \u2014 CRITICAL FAILURE!]"
        elif dice_result["passed"]:
            roll_info += " \u2014 Success]"
        else:
            roll_info += " \u2014 Failure]"
        narration += roll_info

    # Create history event with importance and tags
    history_event = HistoryEvent(
        event=event_description,
        impact=state_changes,
        turn=session.turn_count,
        importance=importance,
        tags=tags,
    )
    session.history.append(history_event)

    # Update timestamp and advance time
    session.updated_at = datetime.now().isoformat()
    _advance_time(session)

    # -----------------------------------------------------------------------
    # Step 11: Fail State Detection
    # -----------------------------------------------------------------------
    fail_state = _check_fail_states(session)

    # Save game state
    save_game(session)

    return TurnResult(
        narration=narration,
        events=[history_event],
        state_changes=state_changes,
        dice_roll=dice_result,
        fail_state=fail_state,
    )


def _apply_state_updates(session: GameSession, intent: PlayerIntent,
                         event_outcome: Dict, context: str) -> Dict[str, Any]:
    """Apply state changes from the Character Manager agent."""
    changes = {}

    # Ask Character Manager for updates
    char_updates = agents.manage_characters(event_outcome.get("outcome", ""), context)

    if char_updates:
        # Apply NPC updates
        for npc_update in char_updates.get("npc_updates", []):
            npc = session.get_npc(npc_update.get("name", ""))
            if npc:
                rel_change = npc_update.get("relationship_change", 0)
                if rel_change:
                    npc.relationships["player"] = npc.relationships.get("player", 0) + rel_change
                    changes[f"{npc.name}_relationship"] = rel_change

                for item in npc_update.get("inventory_add", []):
                    npc.inventory.append(item)
                for item in npc_update.get("inventory_remove", []):
                    if item in npc.inventory:
                        npc.inventory.remove(item)

                new_loc = npc_update.get("location_change", "")
                if new_loc:
                    npc.location = new_loc

                new_action = npc_update.get("current_action", "")
                if new_action:
                    npc.current_action = new_action

        # Apply player updates
        player_updates = char_updates.get("player_updates", {})
        if player_updates:
            # Stat changes
            for stat, change in player_updates.get("stat_changes", {}).items():
                if hasattr(session.player.stats, stat):
                    current = getattr(session.player.stats, stat)
                    setattr(session.player.stats, stat, current + change)
                    changes[f"player_{stat}"] = change

            # Inventory
            for item in player_updates.get("inventory_add", []):
                session.player.inventory.append(item)
                changes.setdefault("inventory_gained", []).append(item)
            for item in player_updates.get("inventory_remove", []):
                if item in session.player.inventory:
                    session.player.inventory.remove(item)
                    changes.setdefault("inventory_lost", []).append(item)

            # Wealth
            wealth_change = player_updates.get("wealth_change", 0)
            if wealth_change:
                session.player.stats.wealth += wealth_change
                changes["wealth_change"] = wealth_change

            # Reputation
            rep_local = player_updates.get("reputation_local_change", 0)
            if rep_local:
                session.player.reputation_local += rep_local
                changes["reputation_local"] = rep_local
            rep_global = player_updates.get("reputation_global_change", 0)
            if rep_global:
                session.player.reputation_global += rep_global
                changes["reputation_global"] = rep_global

            # Location
            loc_change = player_updates.get("location_change", "")
            if loc_change:
                session.player.location = loc_change
                changes["player_location"] = loc_change

            # New known facts (meta-gaming prevention)
            for fact in player_updates.get("new_known_facts", []):
                if fact not in session.player.known_facts:
                    session.player.known_facts.append(fact)

    # Handle movement intent directly
    if intent.intent == "move" and intent.target:
        target_loc = session.world.get_location(intent.target)
        if target_loc:
            session.player.location = target_loc.name
            changes["player_location"] = target_loc.name

    return changes


def _simulate_npcs(session: GameSession) -> None:
    """Run NPC autonomy simulation for background world events."""
    # Only simulate every 2 turns to reduce LLM calls
    if session.turn_count % 2 != 0:
        return

    context = build_context(session)
    npc_data = agents.simulate_npcs(context)
    if not npc_data:
        return

    for action in npc_data.get("npc_actions", []):
        npc = session.get_npc(action.get("name", ""))
        if npc:
            new_loc = action.get("location_change", "")
            if new_loc:
                npc.location = new_loc
            new_action = action.get("current_action", "")
            if new_action:
                npc.current_action = new_action
            # NPC-to-NPC relationship changes
            for target, change in action.get("relationship_changes", {}).items():
                if isinstance(change, (int, float)):
                    npc.relationships[target] = npc.relationships.get(target, 0) + int(change)


def _update_memory(session: GameSession, event_description: str) -> None:
    """Update the memory system with the latest event."""
    recent_events = [h.event for h in session.history[-10:]]
    memory_data = agents.update_memory(
        event_description, session.mid_term_summary, recent_events
    )
    if memory_data:
        new_summary = memory_data.get("mid_term_update", "")
        if new_summary:
            session.mid_term_summary = new_summary


def _update_narrative(session: GameSession) -> None:
    """Update narrative direction every 5 turns."""
    if session.turn_count % 5 != 0:
        return

    direction = agents.direct_narrative(
        session.mid_term_summary,
        session.turn_count,
        session.narrative_act,
        session.narrative_tension,
    )
    if direction:
        session.narrative_act = direction.get("narrative_act", session.narrative_act)
        session.narrative_tension = direction.get("tension_level", session.narrative_tension)


def _check_fail_states(session: GameSession) -> str:
    """Check for game-over conditions. Returns fail state string or empty."""
    # Death (health-related, set by event outcomes)
    if not session.player.is_alive:
        return "death"

    # Bankruptcy
    if session.player.stats.wealth <= BANKRUPTCY_THRESHOLD:
        session.player.fail_state = "bankruptcy"
        return "bankruptcy"

    # Reputation collapse
    if (session.player.reputation_local <= REPUTATION_COLLAPSE_THRESHOLD and
            session.player.reputation_global <= REPUTATION_COLLAPSE_THRESHOLD):
        session.player.fail_state = "reputation_collapse"
        return "reputation_collapse"

    return ""


def _advance_time(session: GameSession) -> None:
    """Advance the in-game time using the WorldTime system."""
    # Advance 2 hours per turn
    session.world.world_time.advance(hours=2)

    # Keep legacy fields in sync for backward compatibility
    session.world.time_of_day = session.world.world_time.period
    session.world.day_count = session.world.world_time.day
