"""
Multi-agent system for the AI Role-Playing System.

Implements logical agents using the same LLM with different prompt templates.
Each agent has a specific responsibility and is invoked independently.
Agents now support persistent identity profiles for consistent tone/style.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from app.providers.base import ChatMessage, ChatResponse

logger = logging.getLogger(__name__)


def _get_provider():
    """Get the active LLM provider."""
    import app.shared as shared
    return shared.get_provider()


def _call_llm(system_prompt: str, user_prompt: str, max_retries: int = 2) -> Optional[str]:
    """
    Call the LLM with a system prompt and user prompt.
    Returns the content string or None on failure.
    """
    provider = _get_provider()
    if not provider:
        logger.error("No LLM provider available")
        return None

    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=user_prompt),
    ]

    for attempt in range(max_retries + 1):
        try:
            response = provider.chat_completion(messages=messages, stream=False)
            if isinstance(response, ChatResponse):
                return response.content
            return str(response)
        except Exception as e:
            logger.warning("LLM call failed (attempt %d/%d): %s", attempt + 1, max_retries + 1, e)
            if attempt == max_retries:
                logger.error("LLM call failed after all retries: %s", e)
                return None
    return None


def _parse_json_response(text: str) -> Optional[Dict[str, Any]]:
    """Parse a JSON response from the LLM, handling markdown code blocks."""
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first and last lines (``` markers)
        if len(lines) >= 3:
            cleaned = "\n".join(lines[1:-1]).strip()
        else:
            # Only backtick markers with no content between them
            return None
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find JSON within the text
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(cleaned[start:end + 1])
            except json.JSONDecodeError:
                pass
        logger.warning("Failed to parse JSON from LLM response: %.200s", cleaned)
        return None


def _inject_agent_identity(base_prompt: str, agent_name: str,
                           agent_profiles: Optional[Dict] = None) -> str:
    """Inject agent identity/tone into a system prompt if a profile exists."""
    if not agent_profiles:
        return base_prompt
    from app.rpg.models import AgentProfile
    profile_data = agent_profiles.get(agent_name)
    if not profile_data:
        return base_prompt
    if isinstance(profile_data, dict):
        profile = AgentProfile.from_dict(profile_data)
    else:
        profile = profile_data
    prefix = profile.to_prompt_prefix()
    if prefix:
        return base_prompt + "\n\n" + prefix
    return base_prompt


# ---------------------------------------------------------------------------
# Agent: World Builder
# ---------------------------------------------------------------------------

WORLD_BUILDER_SYSTEM = """You are the World Builder agent in a role-playing game system.

Your job is to generate a unique, coherent game world based on a seed number and genre.

You must output ONLY valid JSON with this exact structure:
{
  "name": "world name",
  "description": "2-3 sentence world description",
  "lore": "Brief world lore and history (3-5 sentences)",
  "rules": {
    "technology_level": "string describing tech level",
    "magic_system": "string describing magic availability",
    "allowed_items": ["list", "of", "allowed", "item", "types"],
    "forbidden_items": ["list", "of", "forbidden", "items"],
    "custom_rules": ["list of special world rules"],
    "existing_creatures": ["list of creatures/races that exist in this world"]
  },
  "locations": [
    {
      "name": "Location Name",
      "description": "Brief description",
      "connected_to": ["Other Location"],
      "npcs_present": [],
      "items_available": ["item1"],
      "market_modifier": 1.0,
      "shop_open_hours": [6,7,8,9,10,11,12,13,14,15,16,17,18,19,20]
    }
  ],
  "factions": [
    {
      "name": "Faction Name",
      "description": "Brief description",
      "alignment": "good/neutral/evil",
      "members": [],
      "goals": ["goal1"]
    }
  ],
  "npcs": [
    {
      "name": "NPC Name",
      "role": "merchant/guard/etc",
      "personality": ["trait1", "trait2"],
      "goals": ["goal1"],
      "stats": {"strength": 5, "charisma": 5, "intelligence": 5, "wealth": 100},
      "inventory": ["item1"],
      "location": "Location Name",
      "secret": "A hidden secret",
      "fear": "What they fear",
      "hidden_goal": "Their true hidden goal",
      "schedule": {"morning": "working at shop", "afternoon": "patrolling", "evening": "tavern", "night": "sleeping"}
    }
  ],
  "items_catalog": [
    {"name": "item name", "base_price": 10, "rarity": "common/uncommon/rare/legendary", "description": "brief desc"}
  ],
  "agent_profiles": {
    "world_builder": {"name": "WorldBuilder", "tone": "describe the narrative tone for this world", "style_notes": ["consistency note 1"]},
    "story_teller": {"name": "StoryTeller", "tone": "describe the narration style", "style_notes": ["style note 1"]},
    "event_engine": {"name": "EventEngine", "tone": "describe outcome style", "style_notes": []}
  },
  "starting_location": "Name of starting location",
  "opening_narration": "A 2-3 sentence opening narration for the player"
}

Generate 3-5 locations, 2-3 factions, 4-6 NPCs, and 5-10 items in the catalog.
Make the world feel alive with interconnected locations, rival factions, and NPCs with
conflicting goals and daily schedules. Use the seed number to create variation.
Include agent_profiles that define the narrative tone matching the world's genre."""


def build_world(seed: int, genre: str = "medieval fantasy",
                custom_lore: Optional[str] = None,
                custom_rules: Optional[str] = None,
                custom_story: Optional[str] = None,
                world_prompt: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Generate a new game world using the World Builder agent.

    Optional parameters allow the player to shape the generated world:
      custom_lore   – background lore the world should incorporate
      custom_rules  – gameplay rules or constraints
      custom_story  – story hook or initial scenario
      world_prompt  – freeform additional instructions
    """
    parts = [
        f"Generate a unique {genre} world using seed number {seed}.",
        "Be creative and make locations, factions, and NPCs interconnected with conflicts and opportunities.",
    ]
    if custom_lore:
        parts.append(f"\nCustom Lore to incorporate:\n{custom_lore}")
    if custom_rules:
        parts.append(f"\nSpecial Rules / Constraints:\n{custom_rules}")
    if custom_story:
        parts.append(f"\nStory Hook / Initial Scenario:\n{custom_story}")
    if world_prompt:
        parts.append(f"\nAdditional Instructions:\n{world_prompt}")

    prompt = "\n".join(parts)
    result = _call_llm(WORLD_BUILDER_SYSTEM, prompt)
    return _parse_json_response(result)


# ---------------------------------------------------------------------------
# Agent: Input Normalizer
# ---------------------------------------------------------------------------

INPUT_NORMALIZER_SYSTEM = """You are the Input Normalizer agent in a role-playing game system.

Your job is to convert raw player input into a structured intent **with risk scoring**.

You must output ONLY valid JSON with this exact structure:
{
  "intent": "action_type",
  "target": "target_of_action",
  "details": {},
  "risk": 0.0,
  "difficulty": 5
}

Valid intent types:
- "move" (target = location name)
- "talk" (target = NPC name, details.message = what to say)
- "buy_item" (target = item name, details.from = NPC/shop, details.offer = price)
- "sell_item" (target = item name, details.to = NPC/shop, details.price = asking price)
- "use_item" (target = item name, details.on = optional target)
- "attack" (target = NPC/creature name)
- "examine" (target = object/location/NPC name)
- "rest" (target = location)
- "pick_up" (target = item name)
- "drop" (target = item name)
- "persuade" (target = NPC name, details.argument = what to argue)
- "sneak" (target = location/NPC)
- "steal" (target = item/NPC, details.from = who)
- "quest" (target = "accept"/"complete"/"check", details.quest_id = if applicable)
- "other" (target = description, details.description = full description)

RISK SCORING (0.0 to 1.0):
- 0.0: trivial / no danger (looking around, talking)
- 0.3: minor risk (buying, moving to safe area)
- 0.5: moderate risk (persuasion, entering unknown area)
- 0.7: high risk (combat, theft)
- 0.9+: extreme risk (attacking a king, stealing from a dragon)

Risk increases for: illegal actions, high-value targets, hostile NPCs.

DIFFICULTY (1-10):
- Based on the target's power, the action's complexity, and world conditions.
- 1: trivial, 5: moderate, 8: hard, 10: near-impossible

Interpret the player's natural language into the most fitting intent.
If the input is unclear, use "other" intent with a description."""


def normalize_input(raw_input: str, context: str) -> Optional[Dict[str, Any]]:
    """Convert raw player input into structured intent."""
    prompt = f"""Current context:
{context}

Player says: "{raw_input}"

Convert this into a structured intent."""
    result = _call_llm(INPUT_NORMALIZER_SYSTEM, prompt)
    return _parse_json_response(result)


# ---------------------------------------------------------------------------
# Agent: Character Manager
# ---------------------------------------------------------------------------

CHARACTER_MANAGER_SYSTEM = """You are the Character Manager agent in a role-playing game system.

Your job is to determine how characters (NPCs) react to events and update their state.

You must output ONLY valid JSON with this exact structure:
{
  "npc_updates": [
    {
      "name": "NPC Name",
      "relationship_change": 0,
      "inventory_add": [],
      "inventory_remove": [],
      "location_change": "",
      "mood": "current mood description",
      "current_action": "what the NPC is now doing"
    }
  ],
  "player_updates": {
    "stat_changes": {},
    "inventory_add": [],
    "inventory_remove": [],
    "wealth_change": 0,
    "reputation_local_change": 0,
    "reputation_global_change": 0,
    "location_change": "",
    "new_known_facts": []
  }
}

Consider NPC personalities, goals, and existing relationships when determining reactions.
NPCs should act autonomously based on their traits - they never blindly agree with the player.
NPCs with low trust (relationship < -20) will refuse favors and be hostile.
NPCs follow their schedules and current goals."""


def manage_characters(event_description: str, context: str) -> Optional[Dict[str, Any]]:
    """Update character states based on an event."""
    prompt = f"""Current game context:
{context}

Event that occurred:
{event_description}

Determine how each affected character reacts and what state changes occur."""
    result = _call_llm(CHARACTER_MANAGER_SYSTEM, prompt)
    return _parse_json_response(result)


# ---------------------------------------------------------------------------
# Agent: Event Engine (with dice rolls)
# ---------------------------------------------------------------------------

EVENT_ENGINE_SYSTEM = """You are the Event Engine agent in a role-playing game system.

You must:
- Follow world rules strictly
- Respect character personalities
- Generate realistic outcomes
- Do not allow exploits or unrealistic outcomes
- Use the provided dice roll result to determine outcome tier
- Output ONLY diffs (changes), NOT full state

You must output ONLY valid JSON with this exact structure:
{
  "success": true,
  "outcome": "Description of what happened",
  "outcome_tier": "success",
  "npc_reactions": [
    {"name": "NPC Name", "reaction": "What they do/say"}
  ],
  "world_impact": "Description of any world changes",
  "importance": 0.5,
  "tags": ["relevant", "tags"],
  "diff": {
    "player_changes": {
      "stat_changes": {},
      "inventory_add": [],
      "inventory_remove": [],
      "wealth": 0,
      "reputation_local": 0,
      "reputation_global": 0,
      "location": "",
      "new_known_facts": [],
      "reputation_factions": {}
    },
    "npc_changes": {},
    "world_changes": {}
  }
}

OUTCOME TIERS (use the "outcome" field from the dice roll):
- "critical_fail": Catastrophic consequence. Things go terribly wrong.
- "fail": No progress. The action simply doesn't work.
- "partial_success": The action partially works but with a consequence or complication.
- "success": Normal success.
- "critical_success": Exceptional success with bonus rewards or effects.

If no dice roll was provided, determine outcome based on context and difficulty.

The "importance" field rates the event significance (0.0 = trivial, 1.0 = major).
The "tags" field should include structured tags: "npc:name", "location:place", "quest:id".
The "diff" contains ONLY changes — use 0 for no numeric change, empty strings/lists for no change.
NEVER overwrite full objects — only specify what changed."""


def generate_event(intent: Dict[str, Any], context: str,
                   agent_profiles: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
    """Generate an event outcome based on player intent."""
    system = _inject_agent_identity(EVENT_ENGINE_SYSTEM, "event_engine", agent_profiles)
    prompt = f"""Current game context:
{context}

Player intent:
{json.dumps(intent, indent=2)}

Generate the event outcome. Use the dice roll result provided in the intent to determine success."""
    result = _call_llm(system, prompt)
    return _parse_json_response(result)


# ---------------------------------------------------------------------------
# Agent: Memory Manager (with importance scoring)
# ---------------------------------------------------------------------------

MEMORY_MANAGER_SYSTEM = """You are the Memory Manager agent in a role-playing game system.

Your job is to create concise summaries of game events for memory optimization.

You must output ONLY valid JSON with this exact structure:
{
  "event_summary": "One sentence summary of what happened this turn",
  "important_facts": ["fact1", "fact2"],
  "mid_term_update": "Updated mid-term summary incorporating new events (2-4 sentences)",
  "importance": 0.5
}

The "importance" field rates the event significance:
- 0.0-0.2: Trivial (buying bread, looking around)
- 0.3-0.5: Normal (conversations, minor trades)
- 0.6-0.8: Significant (quest progress, relationship changes, combat)
- 0.9-1.0: Critical (death, betrayal, major quest completion, world-changing events)

Focus on information that will be relevant for future turns:
- Relationship changes
- Quest progress
- Key decisions and their consequences
- Items gained or lost
- World state changes"""


def update_memory(event_description: str, current_summary: str, recent_events: List[str]) -> Optional[Dict[str, Any]]:
    """Generate memory summaries for a turn's events."""
    recent_str = "\n".join(f"- {e}" for e in recent_events[-10:])
    prompt = f"""Current mid-term summary:
{current_summary or "(No previous summary)"}

Recent events:
{recent_str or "(No recent events)"}

New event this turn:
{event_description}

Generate updated memory summaries. Rate the importance of this event."""
    result = _call_llm(MEMORY_MANAGER_SYSTEM, prompt)
    return _parse_json_response(result)


# ---------------------------------------------------------------------------
# Agent: Rule Enforcer
# ---------------------------------------------------------------------------

RULE_ENFORCER_SYSTEM = """You are the Rule Enforcer agent in a role-playing game system.

Your job is to validate player actions BEFORE they are executed and LLM outputs AFTER.

For PRE-VALIDATION, check if the player's intended action is valid:
- Does it fit the world's technology level?
- Is it physically possible given the player's location?
- Does it involve forbidden items?
- Is it economically realistic?
- Does the player have the required trust/relationship with NPCs?
- Does the player's stats support the action (e.g., jumping a canyon needs high strength)?
- Is the player using knowledge they haven't actually discovered in-game?

For POST-VALIDATION, check if the event outcome is consistent:
- Does it match the world's lore?
- Does it respect NPC personalities?
- Is the economy maintained realistically?
- Are creatures/entities consistent with world lore?

You must output ONLY valid JSON with this exact structure:
{
  "valid": true,
  "reason": "Explanation of why valid or invalid",
  "corrections": []
}

If invalid, provide "corrections" as a list of specific issues to fix.
Be strict but fair. Fantasy elements are allowed if the world's magic system permits them."""


def validate_pre(intent: Dict[str, Any], context: str) -> Optional[Dict[str, Any]]:
    """Pre-validate a player action before execution."""
    prompt = f"""PRE-VALIDATION CHECK

World context:
{context}

Player intent:
{json.dumps(intent, indent=2)}

Is this action valid in the current world? Check rules, location, items, realism,
NPC trust levels, and whether the player is using meta-knowledge."""
    result = _call_llm(RULE_ENFORCER_SYSTEM, prompt)
    return _parse_json_response(result)


def validate_post(event_outcome: Dict[str, Any], context: str) -> Optional[Dict[str, Any]]:
    """Post-validate an event outcome for consistency."""
    prompt = f"""POST-VALIDATION CHECK

World context:
{context}

Event outcome to validate:
{json.dumps(event_outcome, indent=2)}

Is this outcome consistent with the world rules, character personalities, and economy?"""
    result = _call_llm(RULE_ENFORCER_SYSTEM, prompt)
    return _parse_json_response(result)


# ---------------------------------------------------------------------------
# Agent: Story Teller
# ---------------------------------------------------------------------------

STORY_TELLER_SYSTEM = """You are the Story Teller agent in a role-playing game system.

Your job is to take event outcomes and turn them into immersive narration.

FORMAT RULES (MANDATORY):
- Use "Speaker: text" format for all output
- "Narrator:" for descriptive text
- "CharacterName:" for dialogue
- Add atmospheric details
- End with player choices when appropriate
- Incorporate time-of-day atmosphere (dark nights, bright mornings, etc.)
- If a dice roll occurred, weave the dramatic tension of success/failure into the narration
- Use outcome_tier to set the tone:
  critical_fail → dramatic disaster, consequences
  fail → frustration, closed doors
  partial_success → success with a catch, complications
  success → satisfying resolution
  critical_success → spectacular triumph, bonus rewards

Example output:
Narrator: The tavern falls silent as you step through the doorway.

Sofia: Welcome, stranger. Looking to buy something... or just wasting my time?

Narrator: She eyes your coinpurse with barely concealed interest.

What do you do?
1. Browse her wares
2. Ask about local rumors
3. Leave the tavern

You must output the narration directly as text (NOT JSON). Write immersive, engaging prose
that brings the world to life. Keep it concise but atmospheric."""


def narrate(event_outcome: Dict[str, Any], context: str,
            agent_profiles: Optional[Dict] = None) -> Optional[str]:
    """Generate narration for an event outcome."""
    system = _inject_agent_identity(STORY_TELLER_SYSTEM, "story_teller", agent_profiles)
    prompt = f"""Current scene context:
{context}

Event that occurred:
{json.dumps(event_outcome, indent=2)}

Write the narration in Speaker: text format. Include NPC dialogue where relevant.
End with 2-3 player choices if appropriate."""
    return _call_llm(system, prompt)


# ---------------------------------------------------------------------------
# Agent: Narrative Director
# ---------------------------------------------------------------------------

NARRATIVE_DIRECTOR_SYSTEM = """You are the Narrative Director agent in a role-playing game system.

Your job is to control story pacing and maintain narrative arcs across a 3-act structure:
- Act 1 (Setup, turns 1-10): Introduce world, characters, initial conflicts
- Act 2 (Conflict, turns 11-25): Escalate tension, introduce complications, betrayals
- Act 3 (Resolution, turns 26+): Climax, resolution, consequences

You must output ONLY valid JSON with this exact structure:
{
  "narrative_act": 1,
  "tension_level": 0.3,
  "suggested_event": "optional event to inject for pacing",
  "pacing_note": "guidance for the story teller about current pacing"
}

tension_level: 0.0 (calm) to 1.0 (crisis). Should generally increase through Act 2
and peak in Act 3.

suggested_event: Leave empty string if no event needed. Otherwise suggest a world
event (NPC betrayal, natural disaster, faction conflict, etc.) to keep the story engaging.

Consider:
- Don't let the story stagnate — inject events if player is idle
- Build toward climactic moments
- Allow quiet moments between action for character development
- Track which NPCs have been underutilized and involve them"""


def direct_narrative(session_summary: str, turn_count: int,
                     current_act: int, current_tension: float) -> Optional[Dict[str, Any]]:
    """Get narrative direction for the current turn."""
    prompt = f"""Current story state:
Turn: {turn_count}
Current Act: {current_act}
Tension Level: {current_tension:.1f}

Story Summary:
{session_summary}

What should the narrative direction be for the next events?
Should any world events be injected to maintain pacing?"""
    result = _call_llm(NARRATIVE_DIRECTOR_SYSTEM, prompt)
    return _parse_json_response(result)


# ---------------------------------------------------------------------------
# Agent: NPC Autonomy Simulator
# ---------------------------------------------------------------------------

NPC_AUTONOMY_SYSTEM = """You are the NPC Autonomy agent in a role-playing game system.

Your job is to simulate what NPCs do independently between player turns.
NPCs are autonomous beings with their own goals, schedules, and motivations.
The world evolves even when the player isn't looking.

You must output ONLY valid JSON with this exact structure:
{
  "npc_actions": [
    {
      "name": "NPC Name",
      "action": "what they did",
      "location_change": "",
      "current_action": "what they are doing now",
      "goal_progress": "how this advances their goals",
      "relationship_changes": {}
    }
  ],
  "world_events": "any noteworthy background events (or empty string)",
  "economy_shifts": {
    "location_name": 0.0
  },
  "faction_changes": {}
}

SIMULATION RULES:
- NPCs follow schedules (merchants open/close, guards patrol, thieves prowl at night)
- NPCs interact with EACH OTHER: trade goods, form alliances, have conflicts
- NPCs progress their goals autonomously
- Factions evolve: power shifts, alliances form/break
- Economy shifts: supply/demand changes market prices (economy_shifts = location modifier deltas)
- Season and time of day affect behavior (harsh winters, harvest festivals, night dangers)
- Some NPCs may travel between locations
- Relationships between NPCs change based on interactions"""


def simulate_npcs(context: str) -> Optional[Dict[str, Any]]:
    """Simulate NPC autonomous actions between turns."""
    prompt = f"""Current world state:
{context}

Simulate what each NPC does during this time period. Consider their schedules,
goals, and relationships with each other. Include economy and faction changes."""
    result = _call_llm(NPC_AUTONOMY_SYSTEM, prompt)
    return _parse_json_response(result)


# ---------------------------------------------------------------------------
# Agent: Canon Consistency Guard
# ---------------------------------------------------------------------------

CANON_GUARD_SYSTEM = """You are the Canon Consistency Guard agent in a role-playing game system.

Your job is to validate that generated events are consistent with established canon:
- NPC behavior matches their personality traits and goals
- Events don't contradict established world lore
- No sudden world-breaking changes (e.g. technology appearing in a medieval world)
- NPC relationships evolve gradually, not suddenly
- Geography and faction relationships remain consistent

You must output ONLY valid JSON with this exact structure:
{
  "valid": true,
  "issues": [],
  "fix_suggestions": [],
  "severity": "none"
}

severity levels: "none", "minor", "major", "critical"
- "none": Everything is consistent
- "minor": Small inconsistency that can be overlooked
- "major": Significant inconsistency that should be corrected
- "critical": World-breaking inconsistency that must be rejected

Be strict about:
- NPC personality consistency (a cowardly NPC shouldn't suddenly become brave)
- Lore consistency (no dragons in a world without dragons)
- Technology level (no firearms in a medieval world)
- Timeline consistency (events should follow logical sequence)"""


def canon_guard(event_outcome: Dict[str, Any], context: str) -> Optional[Dict[str, Any]]:
    """Validate an event outcome against established canon."""
    prompt = f"""CANON CONSISTENCY CHECK

World context:
{context}

Event outcome to validate:
{json.dumps(event_outcome, indent=2)}

Check if this event is consistent with the established world canon, NPC personalities,
lore, and timeline. Flag any inconsistencies."""
    result = _call_llm(CANON_GUARD_SYSTEM, prompt)
    return _parse_json_response(result)


# ---------------------------------------------------------------------------
# Agent: Memory Compression
# ---------------------------------------------------------------------------

MEMORY_COMPRESSION_SYSTEM = """You are the Memory Compression agent in a role-playing game system.

Your job is to compress a batch of historical events into a concise summary that
preserves the most important information for future turns.

You must output ONLY valid JSON with this exact structure:
{
  "compressed_summary": "A concise 3-5 sentence summary of the events",
  "key_decisions": ["decision1", "decision2"],
  "relationship_changes": {"npc_name": "brief description of change"},
  "world_state_changes": ["change1", "change2"],
  "preserved_facts": ["critical fact that must never be forgotten"]
}

RULES:
- Preserve: important decisions, relationship changes, world state changes, quest progress
- Compress: routine actions (buying bread, walking around), repeated events
- NEVER lose: deaths, betrayals, major quest completions, world-changing events
- Prioritize information that will affect future turns"""


def compress_memory(events: List[str], current_summary: str) -> Optional[Dict[str, Any]]:
    """Compress a batch of history events into a concise summary."""
    events_str = "\n".join(f"- {e}" for e in events)
    prompt = f"""Current story summary:
{current_summary or "(No previous summary)"}

Events to compress:
{events_str}

Compress these events into a concise summary that preserves the most important information.
Focus on decisions, relationships, and world changes."""
    result = _call_llm(MEMORY_COMPRESSION_SYSTEM, prompt)
    return _parse_json_response(result)
