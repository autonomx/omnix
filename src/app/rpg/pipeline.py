"""
Turn Execution Pipeline for the AI Role-Playing System.

Orchestrates the turn execution with integrated systems:
1. Fail state check
2. Input Normalization (with risk scoring)
3. Rule Validation (Pre-LLM)
4. Dice Roll (skill check with seed-based randomness)
5. Context Assembly
6. Event Generation (with diff output)
7. Canon Guard (consistency check)
8. Apply Diff (safe state mutation)
9. NPC Autonomy (background world simulation)
10. Memory Update (with importance scoring)
11. Memory Compression (every 15 turns)
12. Narrative Direction
13. Narration Output (with soft-failure tier)
14. Fail State Detection
15. Turn Log (deterministic replay)
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
    TurnLog,
    TurnResult,
    WorldRules,
    WorldState,
    WorldStateDiff,
    WorldTime,
    apply_diff,
    skill_check,
    validate_diff,
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
    "steal": "intelligence",
}

# Difficulty defaults for common actions
INTENT_DIFFICULTY_MAP = {
    "attack": 6,
    "persuade": 6,
    "sneak": 7,
    "pick_up": 3,
    "use_item": 4,
    "steal": 8,
}

# Fail state thresholds
BANKRUPTCY_THRESHOLD = -100
REPUTATION_COLLAPSE_THRESHOLD = -50

# Memory compression trigger interval
MEMORY_COMPRESSION_INTERVAL = 15

# Events at or above this importance are preserved during compression
IMPORTANCE_THRESHOLD_PRESERVE = 0.8


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

    Enhanced pipeline:
      Input -> Risk Score -> Rules -> Dice (seeded) -> Event -> Canon Guard ->
      Diff Apply -> NPC Simulation -> Memory -> Compression -> Narrative -> Narrate
    """
    session.turn_count += 1
    logger.info("Turn %d: player input='%s'", session.turn_count, raw_input)

    # -----------------------------------------------------------------------
    # Step 1: Input Normalization (with risk scoring)
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
    # Extract risk scoring from normalizer
    intent_risk = intent_data.get("risk", 0.0)
    intent_difficulty = intent_data.get("difficulty", 5)
    logger.info("Intent: %s -> %s (risk=%.2f, difficulty=%d)",
                intent.intent, intent.target, intent_risk, intent_difficulty)

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
    # Step 3: Dice Roll (seed-based deterministic randomness)
    # -----------------------------------------------------------------------
    dice_result = None
    # Per-turn seed: stored in TurnLog for deterministic replay even if the
    # derivation formula changes in future versions.
    dice_seed = session.world.seed + session.turn_count
    stat_name = INTENT_STAT_MAP.get(intent.intent)
    if stat_name:
        stat_value = getattr(session.player.stats, stat_name, 5)
        # Use risk-scored difficulty from normalizer if available, else default
        difficulty = intent_difficulty if intent_difficulty > 0 else INTENT_DIFFICULTY_MAP.get(intent.intent, 5)
        # Seed-based deterministic randomness for replayability
        dice_result = skill_check(stat_value, difficulty, seed=dice_seed)
        intent_data["skill_check"] = dice_result
        logger.info("Dice roll: d20=%d + %s(%d) = %d vs DC %d -> %s (%s)",
                     dice_result["roll"], stat_name, stat_value,
                     dice_result["total"], dice_result["dc"],
                     "PASS" if dice_result["passed"] else "FAIL",
                     dice_result["outcome"])

    # -----------------------------------------------------------------------
    # Step 4: Context Assembly (refresh with latest)
    # -----------------------------------------------------------------------
    context = build_context(session)
    intent_data["player_stats"] = session.player.stats.to_dict()
    intent_data["risk"] = intent_risk

    # -----------------------------------------------------------------------
    # Step 5: Event Generation (with diff output)
    # -----------------------------------------------------------------------
    agent_profiles = {k: v.to_dict() for k, v in session.world.agent_profiles.items()}
    event_outcome = agents.generate_event(intent_data, context, agent_profiles)
    if not event_outcome:
        return TurnResult(
            narration="Narrator: Something unexpected happens... the moment passes without consequence.",
            error="Event generation failed",
        )

    # -----------------------------------------------------------------------
    # Step 6: Canon Guard (consistency check)
    # -----------------------------------------------------------------------
    canon_result = agents.canon_guard(event_outcome, context)
    canon_check_data = canon_result if canon_result else {}
    if canon_result and not canon_result.get("valid", True):
        severity = canon_result.get("severity", "minor")
        if severity in ("major", "critical"):
            logger.warning("Canon guard flagged event (severity=%s): %s",
                           severity, canon_result.get("issues", []))
            # Retry event generation with feedback
            feedback = "; ".join(canon_result.get("fix_suggestions", []))
            if feedback:
                intent_data["canon_feedback"] = feedback
                event_outcome_retry = agents.generate_event(intent_data, context, agent_profiles)
                if event_outcome_retry:
                    event_outcome = event_outcome_retry

    # -----------------------------------------------------------------------
    # Post-validation of event outcome (hard checks)
    # -----------------------------------------------------------------------
    post_valid, post_issues = post_validate_hard(event_outcome, session)
    if not post_valid:
        logger.warning("Post-validation issues: %s", post_issues)

    # -----------------------------------------------------------------------
    # Step 7: Apply Diff (safe state mutation)
    # -----------------------------------------------------------------------
    diff_data = event_outcome.get("diff", {})
    state_changes = {}
    diff_validation_result: Dict[str, Any] = {}
    if diff_data:
        world_diff = WorldStateDiff.from_dict(diff_data)
        diff_validation_result = validate_diff(world_diff, session)
        state_changes = apply_diff(session, world_diff)
    else:
        # Fallback: use legacy Character Manager path for backward compatibility
        state_changes = _apply_state_updates_legacy(session, intent, event_outcome, context)

    # -----------------------------------------------------------------------
    # Step 8: NPC Autonomy Simulation (enhanced world tick)
    # -----------------------------------------------------------------------
    _simulate_world_tick(session)

    # -----------------------------------------------------------------------
    # Step 9: Memory Update (with importance scoring)
    # -----------------------------------------------------------------------
    event_description = event_outcome.get("outcome", raw_input)
    importance = event_outcome.get("importance", 0.5)
    # Build structured tags: include npc:, location:, quest: prefixes
    tags = _build_structured_tags(event_outcome, intent, session)
    _update_memory(session, event_description)

    # -----------------------------------------------------------------------
    # Step 10: Memory Compression (every N turns)
    # -----------------------------------------------------------------------
    _compress_memory_if_needed(session)

    # -----------------------------------------------------------------------
    # Step 11: Narrative Direction
    # -----------------------------------------------------------------------
    _update_narrative(session)

    # -----------------------------------------------------------------------
    # Step 12: Narration Output (with soft-failure tier)
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
        outcome_tier = dice_result.get("outcome", "success")
        roll_info = (
            f"\n\n[Roll: d20({dice_result['roll']}) + "
            f"{stat_name}({dice_result['stat_value']}) = "
            f"{dice_result['total']} vs DC {dice_result['dc']}"
        )
        tier_labels = {
            "critical_fail": " \u2014 CRITICAL FAILURE!]",
            "fail": " \u2014 Failure]",
            "partial_success": " \u2014 Partial Success]",
            "success": " \u2014 Success]",
            "critical_success": " \u2014 CRITICAL SUCCESS!]",
        }
        roll_info += tier_labels.get(outcome_tier, " \u2014 " + outcome_tier + "]")
        narration += roll_info

    # Create history event with importance and structured tags
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
    # Step 13: Fail State Detection
    # -----------------------------------------------------------------------
    fail_state = _check_fail_states(session)

    # -----------------------------------------------------------------------
    # Step 14: Turn Log (deterministic replay)
    # -----------------------------------------------------------------------
    turn_log = TurnLog(
        turn=session.turn_count,
        seed=dice_seed,
        raw_input=raw_input,
        normalized_intent=intent_data,
        dice_roll=dice_result,
        event_output=event_outcome,
        canon_check=canon_check_data,
        applied_diff=state_changes,
        diff_validation=diff_validation_result,
        narration=narration,
    )
    session.turn_logs.append(turn_log)

    # Save game state
    save_game(session)

    return TurnResult(
        narration=narration,
        events=[history_event],
        state_changes=state_changes,
        dice_roll=dice_result,
        fail_state=fail_state,
    )


def replay_turn(turn_log: TurnLog, session: GameSession) -> TurnResult:
    """
    Re-execute a turn from a ``TurnLog`` entry deterministically.

    Uses the stored seed and normalized intent to reproduce the dice roll
    and re-applies the stored diff to the session.  No LLM calls are made
    -- this is a pure-data replay for debugging and verification.

    Returns a ``TurnResult`` with the replayed narration and state changes.
    """
    session.turn_count += 1
    logger.info("Replay turn %d: raw_input='%s'", turn_log.turn, turn_log.raw_input)

    # Reproduce dice roll using stored seed
    replayed_dice = None
    intent_data = dict(turn_log.normalized_intent)
    stat_name = INTENT_STAT_MAP.get(intent_data.get("intent", ""))
    if stat_name and turn_log.seed is not None:
        stat_value = getattr(session.player.stats, stat_name, 5)
        difficulty = intent_data.get("difficulty", 5)
        if difficulty <= 0:
            difficulty = INTENT_DIFFICULTY_MAP.get(intent_data.get("intent", ""), 5)
        replayed_dice = skill_check(stat_value, difficulty, seed=turn_log.seed)

    # Re-apply stored diff
    diff_data = turn_log.event_output.get("diff", {})
    state_changes: Dict[str, Any] = {}
    if diff_data:
        world_diff = WorldStateDiff.from_dict(diff_data)
        state_changes = apply_diff(session, world_diff)

    # Reconstruct history event from log
    event_description = turn_log.event_output.get("outcome", turn_log.raw_input)
    importance = turn_log.event_output.get("importance", 0.5)
    history_event = HistoryEvent(
        event=event_description,
        impact=state_changes,
        turn=turn_log.turn,
        importance=importance,
    )
    session.history.append(history_event)

    session.updated_at = datetime.now().isoformat()

    return TurnResult(
        narration=turn_log.narration,
        events=[history_event],
        state_changes=state_changes,
        dice_roll=replayed_dice,
    )


def _apply_state_updates_legacy(session: GameSession, intent: PlayerIntent,
                               event_outcome: Dict, context: str) -> Dict[str, Any]:
    """Legacy state update path for when Event Engine has no diff.

    Calls the Character Manager agent to determine changes and applies them directly.
    """
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


def _simulate_world_tick(session: GameSession) -> None:
    """
    Run enhanced world simulation: NPC autonomy + economy shifts + faction changes.

    Runs every 2 turns to reduce LLM calls.
    """
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

    # Apply economy shifts (market_modifier changes per location)
    for loc_name, modifier_delta in npc_data.get("economy_shifts", {}).items():
        if isinstance(modifier_delta, (int, float)):
            loc = session.world.get_location(loc_name)
            if loc:
                loc.market_modifier = max(0.5, min(2.0, loc.market_modifier + modifier_delta))


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


def _compress_memory_if_needed(session: GameSession) -> None:
    """
    Compress old history events into mid-term summary every N turns.

    This prevents context from growing unboundedly over long sessions.
    """
    if session.turn_count % MEMORY_COMPRESSION_INTERVAL != 0:
        return
    if len(session.history) < MEMORY_COMPRESSION_INTERVAL:
        return

    # Take events older than the short-term window for compression
    old_events = session.history[:-10] if len(session.history) > 10 else []
    if not old_events:
        return

    event_texts = [h.event for h in old_events]
    compressed = agents.compress_memory(event_texts, session.mid_term_summary)
    if compressed:
        new_summary = compressed.get("compressed_summary", "")
        if new_summary:
            session.mid_term_summary = new_summary

        # Preserve critical facts
        for fact in compressed.get("preserved_facts", []):
            if isinstance(fact, str) and fact not in session.player.known_facts:
                session.player.known_facts.append(fact)

        # Trim history: keep only events from the last 10 turns + high-importance old events
        important_old = [h for h in old_events if h.importance >= IMPORTANCE_THRESHOLD_PRESERVE]
        recent = session.history[-10:] if len(session.history) > 10 else session.history
        session.history = important_old + recent
        logger.info("Memory compressed: %d events -> %d (kept %d important + %d recent)",
                     len(old_events), len(session.history),
                     len(important_old), len(recent))


def _build_structured_tags(event_outcome: Dict, intent: PlayerIntent,
                           session: GameSession) -> List[str]:
    """Build structured tags with npc:, location:, quest: prefixes for memory retrieval."""
    tags = list(event_outcome.get("tags", []))

    # Auto-tag based on intent target
    if intent.target:
        npc = session.get_npc(intent.target)
        if npc and f"npc:{npc.name}" not in tags:
            tags.append(f"npc:{npc.name}")
        loc = session.world.get_location(intent.target)
        if loc and f"location:{loc.name}" not in tags:
            tags.append(f"location:{loc.name}")

    # Auto-tag player location
    if session.player.location and f"location:{session.player.location}" not in tags:
        tags.append(f"location:{session.player.location}")

    # Auto-tag intent type
    if intent.intent and intent.intent not in tags:
        tags.append(intent.intent)

    # Auto-tag NPCs mentioned in reactions
    for reaction in event_outcome.get("npc_reactions", []):
        npc_name = reaction.get("name", "")
        if npc_name and f"npc:{npc_name}" not in tags:
            tags.append(f"npc:{npc_name}")

    return tags


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
