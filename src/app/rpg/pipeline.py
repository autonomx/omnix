"""
Turn Execution Pipeline for the AI Role-Playing System.

Orchestrates the 7-step turn execution:
1. Input Normalization
2. Rule Validation (Pre-LLM)
3. Context Assembly
4. Event Generation
5. State Update
6. Memory Update
7. Narration Output
"""

import logging
import random
from datetime import datetime
from typing import Any, Dict, Optional

from app.rpg import agents
from app.rpg.memory_manager import build_context
from app.rpg.models import (
    GameSession,
    HistoryEvent,
    Location,
    NPCCharacter,
    PlayerIntent,
    PlayerState,
    Quest,
    TurnResult,
    WorldRules,
    WorldState,
)
from app.rpg.persistence import save_game
from app.rpg.rule_enforcer import post_validate_hard, pre_validate_hard

logger = logging.getLogger(__name__)


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
    )

    # Build factions
    from app.rpg.models import Faction
    world.factions = [Faction.from_dict(fac) for fac in world_data.get("factions", [])]

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

    Follows the 7-step pipeline:
    1. Input Normalization
    2. Rule Validation (Pre-LLM)
    3. Context Assembly
    4. Event Generation
    5. State Update
    6. Memory Update
    7. Narration Output
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
    # Step 3: Context Assembly (already done above, refresh with latest)
    # -----------------------------------------------------------------------
    context = build_context(session)

    # Inject player stats into intent for stat checks
    intent_data["player_stats"] = session.player.stats.to_dict()

    # -----------------------------------------------------------------------
    # Step 4: Event Generation
    # -----------------------------------------------------------------------
    event_outcome = agents.generate_event(intent_data, context)
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
        # Don't block, but log issues for debugging

    # -----------------------------------------------------------------------
    # Step 5: State Update
    # -----------------------------------------------------------------------
    state_changes = _apply_state_updates(session, intent, event_outcome, context)

    # -----------------------------------------------------------------------
    # Step 6: Memory Update
    # -----------------------------------------------------------------------
    event_description = event_outcome.get("outcome", raw_input)
    _update_memory(session, event_description)

    # -----------------------------------------------------------------------
    # Step 7: Narration Output
    # -----------------------------------------------------------------------
    narration_context = build_context(session)
    narration = agents.narrate(event_outcome, narration_context)
    if not narration:
        # Fallback narration from event outcome
        narration = f"Narrator: {event_outcome.get('outcome', 'Something happens...')}"
        npc_reactions = event_outcome.get("npc_reactions", [])
        for reaction in npc_reactions:
            narration += f"\n\n{reaction.get('name', 'Someone')}: {reaction.get('reaction', '...')}"

    # Create history event
    history_event = HistoryEvent(
        event=event_description,
        impact=state_changes,
        turn=session.turn_count,
    )
    session.history.append(history_event)

    # Update timestamp
    session.updated_at = datetime.now().isoformat()

    # Advance time
    _advance_time(session)

    # Save game state
    save_game(session)

    return TurnResult(
        narration=narration,
        events=[history_event],
        state_changes=state_changes,
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

    # Handle movement intent directly
    if intent.intent == "move" and intent.target:
        target_loc = session.world.get_location(intent.target)
        if target_loc:
            session.player.location = target_loc.name
            changes["player_location"] = target_loc.name
        else:
            # Try case-insensitive match
            for loc in session.world.locations:
                if loc.name.lower() == intent.target.lower():
                    session.player.location = loc.name
                    changes["player_location"] = loc.name
                    break

    return changes


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


def _advance_time(session: GameSession) -> None:
    """Advance the in-game time of day."""
    time_cycle = ["morning", "afternoon", "evening", "night"]
    current_idx = 0
    for i, t in enumerate(time_cycle):
        if session.world.time_of_day == t:
            current_idx = i
            break

    # Advance every 3 turns
    if session.turn_count % 3 == 0:
        next_idx = (current_idx + 1) % len(time_cycle)
        session.world.time_of_day = time_cycle[next_idx]
        if next_idx == 0:
            session.world.day_count += 1
