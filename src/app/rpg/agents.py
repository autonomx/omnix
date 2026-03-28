"""
Multi-agent system for the AI Role-Playing System.

Implements logical agents using the same LLM with different prompt templates.
Each agent has a specific responsibility and is invoked independently.
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
    "custom_rules": ["list of special world rules"]
  },
  "locations": [
    {
      "name": "Location Name",
      "description": "Brief description",
      "connected_to": ["Other Location"],
      "npcs_present": [],
      "items_available": ["item1"]
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
      "hidden_goal": "Their true hidden goal"
    }
  ],
  "starting_location": "Name of starting location",
  "opening_narration": "A 2-3 sentence opening narration for the player"
}

Generate 3-5 locations, 2-3 factions, and 4-6 NPCs. Make the world feel alive with
interconnected locations, rival factions, and NPCs with conflicting goals. Use the seed
number to create variation - different seeds should produce distinctly different worlds."""


def build_world(seed: int, genre: str = "medieval fantasy") -> Optional[Dict[str, Any]]:
    """Generate a new game world using the World Builder agent."""
    prompt = f"Generate a unique {genre} world using seed number {seed}. Be creative and make locations, factions, and NPCs interconnected with conflicts and opportunities."
    result = _call_llm(WORLD_BUILDER_SYSTEM, prompt)
    return _parse_json_response(result)


# ---------------------------------------------------------------------------
# Agent: Input Normalizer
# ---------------------------------------------------------------------------

INPUT_NORMALIZER_SYSTEM = """You are the Input Normalizer agent in a role-playing game system.

Your job is to convert raw player input into a structured intent.

You must output ONLY valid JSON with this exact structure:
{
  "intent": "action_type",
  "target": "target_of_action",
  "details": {}
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
- "quest" (target = "accept"/"complete"/"check", details.quest_id = if applicable)
- "other" (target = description, details.description = full description)

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
      "mood": "current mood description"
    }
  ],
  "player_updates": {
    "stat_changes": {},
    "inventory_add": [],
    "inventory_remove": [],
    "wealth_change": 0,
    "reputation_local_change": 0,
    "reputation_global_change": 0,
    "location_change": ""
  }
}

Consider NPC personalities, goals, and existing relationships when determining reactions.
NPCs should act autonomously based on their traits - they never blindly agree with the player."""


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
# Agent: Event Engine
# ---------------------------------------------------------------------------

EVENT_ENGINE_SYSTEM = """You are the Event Engine agent in a role-playing game system.

You must:
- Follow world rules strictly
- Respect character personalities
- Generate realistic outcomes
- Do not allow exploits or unrealistic outcomes
- Consider player stats when determining success/failure

You must output ONLY valid JSON with this exact structure:
{
  "success": true,
  "outcome": "Description of what happened",
  "npc_reactions": [
    {"name": "NPC Name", "reaction": "What they do/say"}
  ],
  "world_impact": "Description of any world changes",
  "stat_check": {
    "stat_used": "strength/charisma/intelligence",
    "difficulty": 5,
    "player_value": 0,
    "passed": true
  }
}

Not all actions should succeed. Use stat checks for uncertain outcomes:
- Easy tasks: difficulty 3
- Medium tasks: difficulty 6
- Hard tasks: difficulty 8
- Near impossible: difficulty 10

The player succeeds if their relevant stat >= difficulty."""


def generate_event(intent: Dict[str, Any], context: str) -> Optional[Dict[str, Any]]:
    """Generate an event outcome based on player intent."""
    prompt = f"""Current game context:
{context}

Player intent:
{json.dumps(intent, indent=2)}

Generate the event outcome. Be fair but realistic. Consider the player's stats."""
    result = _call_llm(EVENT_ENGINE_SYSTEM, prompt)
    return _parse_json_response(result)


# ---------------------------------------------------------------------------
# Agent: Memory Manager
# ---------------------------------------------------------------------------

MEMORY_MANAGER_SYSTEM = """You are the Memory Manager agent in a role-playing game system.

Your job is to create concise summaries of game events for memory optimization.

You must output ONLY valid JSON with this exact structure:
{
  "event_summary": "One sentence summary of what happened this turn",
  "important_facts": ["fact1", "fact2"],
  "mid_term_update": "Updated mid-term summary incorporating new events (2-4 sentences)"
}

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

Generate updated memory summaries."""
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

For POST-VALIDATION, check if the event outcome is consistent:
- Does it match the world's lore?
- Does it respect NPC personalities?
- Is the economy maintained realistically?

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

Is this action valid in the current world? Check rules, location, items, and realism."""
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


def narrate(event_outcome: Dict[str, Any], context: str) -> Optional[str]:
    """Generate narration for an event outcome."""
    prompt = f"""Current scene context:
{context}

Event that occurred:
{json.dumps(event_outcome, indent=2)}

Write the narration in Speaker: text format. Include NPC dialogue where relevant.
End with 2-3 player choices if appropriate."""
    return _call_llm(STORY_TELLER_SYSTEM, prompt)
