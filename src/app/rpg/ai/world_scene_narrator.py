"""Phase 5 — LLM Scene Engine + NPC Behavior

Turns structured scenes into narrative experiences:
    Scene → Narrative → NPC reactions → Dialogue → Player response

Provides prompt building, narrative generation, and response parsing
for the scene narration pipeline.

Phase 5.1 fixes:
- JSON-structured LLM output enforcement
- NPC state injection (memory, beliefs, relationships)
- Choice → action binding
- Scene action hooks
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Phase 8: player-facing encounter view
from app.rpg.player import build_encounter_view

logger = logging.getLogger(__name__)


def _llm_text(llm_gateway, prompt, *, context=None):
    """Call the LLM gateway and return the response as a clean string."""
    logger.debug("[RPG LLM GATEWAY] Calling LLM with prompt length: %d, context keys: %s", len(prompt), list(context.keys()) if context else [])
    response = llm_gateway.call("generate", prompt, context=context or {})
    logger.debug("[RPG LLM GATEWAY] Received response type: %s, length: %d", type(response), len(str(response)) if response else 0)
    if response is None:
        logger.warning("[RPG LLM GATEWAY] LLM returned None")
        return ""
    if isinstance(response, str):
        return response
    logger.warning("[RPG LLM GATEWAY] LLM returned non-string type: %s", type(response))
    return str(response)


# ---------------------------------------------------------------------------
# Phase 6.5 — social context helpers
# ---------------------------------------------------------------------------
def _attach_social_context(scene, simulation_state):
    scene = dict(scene or {})
    simulation_state = simulation_state or {}
    social_state = simulation_state.get("social_state") or {}

    scene["active_rumors"] = [
        dict(item)
        for item in (simulation_state.get("active_rumors") or [])[:3]
    ]
    scene["active_alliances"] = [
        dict(item)
        for item in (social_state.get("alliances") or [])
        if item.get("status") == "active"
    ][:3]
    scene["faction_positions"] = {
        key: dict(value)
        for key, value in sorted((social_state.get("group_positions") or {}).items())
    }
    return scene


# ---------------------------------------------------------------------------
# Phase 6 — NPC mind context helpers
# ---------------------------------------------------------------------------

def _safe_str_p6(value):
    if value is None:
        return ""
    return str(value)


def _attach_npc_mind_context(actor, simulation_state):
    """Attach Phase 6 NPC mind context to an actor dict."""
    actor = dict(actor or {})
    simulation_state = simulation_state or {}

    npc_id = _safe_str_p6(actor.get("id"))
    npc_minds = simulation_state.get("npc_minds") or {}
    mind = npc_minds.get(npc_id) or {}

    if isinstance(mind, dict):
        actor["memory_summary"] = ((mind.get("memory") or {}).get("entries") or [])[:5]
        actor["belief_summary"] = ((mind.get("beliefs") or {}).get("beliefs") or {})
        actor["active_goals"] = ((mind.get("goals") or {}).get("goals") or [])[:5]
        actor["last_decision"] = mind.get("last_decision") or {}

    return actor


_NARRATION_MAX_MARKDOWN = 300


def _safe_str(value: Any) -> str:
    return str(value) if value is not None else ""


def _safe_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return list(value) if isinstance(value, list) else []


def _bound_text(value: Any, limit: int = 180) -> str:
    text = _safe_str(value).strip()
    if len(text) > limit:
        return text[:limit].rstrip() + "..."
    return text


def _titleize_action(action_type: str) -> str:
    value = _safe_str(action_type).strip().replace("_", " ")
    return value[:1].upper() + value[1:] if value else "Action"


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = _safe_str(value).strip()
        if text:
            return text
    return ""


def _extract_text_lines(text: str) -> List[str]:
    lines = []
    for part in _safe_str(text).splitlines():
        part = part.strip()
        if part:
            lines.append(part)
    return lines


def _normalize_speaker_block(npc_value: Any) -> Dict[str, Any]:
    npc_value = _safe_dict(npc_value) if isinstance(npc_value, dict) else {"text": _safe_str(npc_value).strip()}
    return {
        "speaker_id": _safe_str(npc_value.get("speaker_id") or npc_value.get("npc_id")).strip(),
        "name": _safe_str(npc_value.get("name")).strip(),
        "text": _bound_text(npc_value.get("text"), 180),
        "emotion": _safe_str(npc_value.get("emotion")).strip(),
        "portrait": _safe_str(npc_value.get("portrait")).strip(),
        "role": _safe_str(npc_value.get("role")).strip(),
    }


def _build_safe_prompt_context(scene: Dict[str, Any], narration_context: Dict[str, Any]) -> Dict[str, Any]:
    scene = _safe_dict(scene)
    narration_context = _safe_dict(narration_context)
    resolved = _safe_dict(narration_context.get("resolved_result"))
    xp_result = _safe_dict(narration_context.get("xp_result"))
    skill_xp_result = _safe_dict(narration_context.get("skill_xp_result"))

    return {
        "player_input": _bound_text(narration_context.get("player_input"), 120),
        "action_type": _safe_str(narration_context.get("action_type")).strip(),
        "action_result": _bound_text(
            _first_nonempty(
                resolved.get("message"),
                resolved.get("summary"),
                resolved.get("result_text"),
            ),
            140,
        ),
        "target_name": _first_nonempty(
            _safe_dict(resolved.get("combat_result")).get("target_name"),
            resolved.get("target_name"),
            resolved.get("npc_name"),
            resolved.get("target_id"),
        ),
        "damage": int(_safe_dict(resolved.get("combat_result")).get("damage", resolved.get("damage", 0)) or 0),
        "player_xp": int(xp_result.get("player_xp", 0) or 0),
        "skill_xp_awards": {
            k: int(v or 0)
            for k, v in sorted(_safe_dict(skill_xp_result.get("awards")).items())
            if int(v or 0) > 0
        },
        "level_up": bool(_safe_list(narration_context.get("level_up"))),
        "scene_title": _safe_str(scene.get("title")).strip(),
        "location_name": _first_nonempty(scene.get("location_name"), scene.get("location_id"), scene.get("scene_id")),
    }


def _build_speaker_turns(parsed: Dict[str, Any]) -> List[Dict[str, Any]]:
    parsed = _safe_dict(parsed)
    npc = _normalize_speaker_block(parsed.get("npc"))
    turns: List[Dict[str, Any]] = []

    narrator_text = " ".join(
        filter(
            None,
            [
                _safe_str(parsed.get("narrator")).strip(),
                _safe_str(parsed.get("action")).strip(),
            ],
        )
    ).strip()
    if narrator_text:
        turns.append({
            "speaker_id": "narrator",
            "name": "Narrator",
            "text": _bound_text(narrator_text, 180),
        })
    if npc.get("text"):
        turns.append(npc)
    return turns


def _structured_fallback_response() -> str:
    return (
        "NARRATOR: [ERROR: LLM FORMAT INVALID]\n"
        "ACTION: [NO VALID RESPONSE]\n"
    )


def _build_scene_summary(scene: Dict[str, Any], llm_narrative: str) -> str:
    scene = _safe_dict(scene)
    title = _safe_str(scene.get("title")).strip()
    location_name = _first_nonempty(
        scene.get("location_name"),
        scene.get("location_id"),
        scene.get("scene_id"),
    )
    summary = _safe_str(scene.get("summary")).strip()

    if summary:
        if title:
            return f"You are in {title}. {summary}"
        return summary

    llm_lines = _extract_text_lines(llm_narrative)
    if llm_lines:
        return llm_lines[0]

    if title and location_name:
        return f"You are in {title} at {location_name}."
    if title:
        return f"You are in {title}."
    if location_name:
        return f"You are at {location_name}."
    return "The scene settles around you."


def _build_action_result_line(narration_context: Dict[str, Any]) -> str:
    narration_context = _safe_dict(narration_context)
    resolved = _safe_dict(narration_context.get("resolved_result"))
    combat = _safe_dict(resolved.get("combat_result"))
    action_type = _safe_str(narration_context.get("action_type")).strip()
    action_label = _titleize_action(action_type)

    outcome = _safe_str(combat.get("outcome")).strip().lower()
    target_name = _first_nonempty(
        combat.get("target_name"),
        resolved.get("target_name"),
        resolved.get("npc_name"),
        resolved.get("target_id"),
    )
    damage = int(combat.get("damage", resolved.get("damage", 0)) or 0)

    if outcome in ("hit", "crit", "graze", "miss"):
        if outcome == "miss":
            if target_name:
                return f"**{action_label}:** You miss **{target_name}**."
            return f"**{action_label}:** You miss."
        if target_name:
            return f"**{action_label}:** {outcome.title()} on **{target_name}** for **{damage} damage**."
        return f"**{action_label}:** {outcome.title()} for **{damage} damage**."

    if resolved.get("ok") is False:
        message = _first_nonempty(resolved.get("message"), resolved.get("reason"))
        if message:
            return f"**{action_label}:** {message}"
        return f"**{action_label}:** The attempt fails."

    message = _first_nonempty(
        resolved.get("message"),
        resolved.get("summary"),
        resolved.get("result_text"),
    )
    if message:
        return f"**{action_label}:** {message}"

    return f"**{action_label}:** You act."


def _pick_npc_reply_text(llm_narrative: str) -> str:
    """Extract NPC dialogue from LLM narrative text."""
    # Look for quoted text or dialogue patterns
    import re
    quotes = re.findall(r'"([^"]*)"', _safe_str(llm_narrative))
    if quotes:
        return quotes[0]
    # Look for dialogue after colons
    dialogue_match = re.search(r':\s*([^.!?]+[.!?])', _safe_str(llm_narrative))
    if dialogue_match:
        return dialogue_match.group(1).strip()
    return ""


def _build_npc_reply_block(scene: Dict[str, Any], narration_context: Dict[str, Any], llm_narrative: str) -> str:
    narration_context = _safe_dict(narration_context)
    resolved = _safe_dict(narration_context.get("resolved_result"))

    reply = _first_nonempty(
        resolved.get("npc_reply"),
        resolved.get("reply"),
        resolved.get("dialogue"),
        resolved.get("spoken_response"),
    )
    if reply:
        return reply

    target_name = _first_nonempty(
        resolved.get("target_name"),
        resolved.get("npc_name"),
        resolved.get("target_id"),
    )
    picked = _pick_npc_reply_text(llm_narrative)
    if picked:
        if target_name and target_name.lower() not in picked.lower():
            return f"**{target_name}:** {picked}"
        return picked
    return ""


def _build_rewards_block(narration_context: Dict[str, Any]) -> str:
    narration_context = _safe_dict(narration_context)
    xp_result = _safe_dict(narration_context.get("xp_result"))
    skill_xp_result = _safe_dict(narration_context.get("skill_xp_result"))
    level_up = _safe_list(narration_context.get("level_up"))
    skill_level_ups = _safe_list(narration_context.get("skill_level_ups"))
    resolved = _safe_dict(narration_context.get("resolved_result"))

    parts: List[str] = []

    player_xp = int(xp_result.get("player_xp", 0) or 0)
    if player_xp > 0:
        parts.append(f"**+{player_xp} XP**")

    awards = _safe_dict(skill_xp_result.get("awards"))
    skill_parts = []
    for skill_id in sorted(awards.keys()):
        amount = int(awards.get(skill_id, 0) or 0)
        if amount > 0:
            skill_parts.append(f"**+{amount} {skill_id} XP**")
    if skill_parts:
        parts.append(", ".join(skill_parts))

    item_name = _first_nonempty(
        resolved.get("item_name"),
        _safe_dict(resolved.get("dropped_item")).get("name"),
        _safe_dict(resolved.get("picked_up_item")).get("name"),
        _safe_dict(resolved.get("item")).get("name"),
    )
    if item_name:
        parts.append(f"**Item:** {item_name}")

    if level_up:
        parts.append("**Level Up!**")

    if skill_level_ups:
        labels = []
        for entry in skill_level_ups:
            entry = _safe_dict(entry)
            skill_id = _first_nonempty(entry.get("skill_id"), entry.get("name"))
            if skill_id:
                labels.append(skill_id)
        if labels:
            parts.append("**Skill Up:** " + ", ".join(labels))

    return " · ".join(parts)


def _collect_emphasis_markers(scene: Dict[str, Any], narration_context: Dict[str, Any], blocks: Dict[str, str]) -> List[str]:
    scene = _safe_dict(scene)
    narration_context = _safe_dict(narration_context)
    resolved = _safe_dict(narration_context.get("resolved_result"))
    xp_result = _safe_dict(narration_context.get("xp_result"))
    markers: List[str] = []

    for value in [
        scene.get("title"),
        scene.get("location_name"),
        resolved.get("target_name"),
        resolved.get("npc_name"),
        _safe_dict(resolved.get("item")).get("name"),
        _safe_dict(resolved.get("picked_up_item")).get("name"),
        _safe_dict(resolved.get("dropped_item")).get("name"),
    ]:
        text = _safe_str(value).strip()
        if text:
            markers.append(text)

    damage = int(_safe_dict(resolved.get("combat_result")).get("damage", resolved.get("damage", 0)) or 0)
    if damage > 0:
        markers.append(f"{damage} damage")

    player_xp = int(xp_result.get("player_xp", 0) or 0)
    if player_xp > 0:
        markers.append(f"+{player_xp} XP")

    if _safe_list(narration_context.get("level_up")):
        markers.append("Level Up!")

    deduped: List[str] = []
    seen = set()
    for marker in markers:
        key = marker.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(marker)
    return deduped


def apply_narration_emphasis(text: str, emphasis_markers: List[str]) -> str:
    rendered = _safe_str(text)
    for marker in sorted(_safe_list(emphasis_markers), key=len, reverse=True):
        marker = _safe_str(marker).strip()
        if not marker:
            continue
        # Only match standalone text (avoid breaking markdown or double wrapping)
        pattern = rf"(?<!\*)\b{re.escape(marker)}\b(?!\*)"
        rendered = re.sub(pattern, f"**{marker}**", rendered)
    rendered = rendered.replace("****", "**")
    return rendered


def build_structured_narration(scene: Dict[str, Any], narration_context: Dict[str, Any], llm_narrative: str) -> Dict[str, Any]:
    parsed = _with_scene_response_defaults(parse_scene_response(llm_narrative))
    npc = _normalize_speaker_block(parsed.get("npc"))
    npc_text = npc.get("text", "")
    action_text = _safe_str(parsed.get("action")).strip() or _build_action_result_line(narration_context)
    rewards_text = _build_rewards_block(narration_context)
    speaker_turns = _build_speaker_turns(parsed)

    blocks = {
        "scene_summary": parsed["narrator"],
        "action_result_line": action_text,
        "npc_reply_block": npc_text,
        "rewards_block": rewards_text,
    }
    emphasis_markers = _collect_emphasis_markers(scene, narration_context, blocks)

    ordered = [
        parsed["narrator"],
        f"**Action:** {action_text}" if action_text else "",
        (
            f"**Reply:** {npc['name'] or 'Character'}: {npc['text']}"
            if npc.get("text")
            else ""
        ),
        f"**Reward:** {rewards_text}" if rewards_text else "",
    ]
    markdown = "\n\n".join(filter(None, ordered))
    markdown = apply_narration_emphasis(markdown, emphasis_markers)

    if len(markdown) > _NARRATION_MAX_MARKDOWN:
        cutoff = markdown[:_NARRATION_MAX_MARKDOWN]
        last_break = cutoff.rfind("\n")
        if last_break > 0:
            cutoff = cutoff[:last_break]
        markdown = cutoff.rstrip() + "..."

    return {
        "scene_summary": apply_narration_emphasis(parsed["narrator"], emphasis_markers),
        "action_result_line": apply_narration_emphasis(action_text, emphasis_markers),
        "npc_reply_block": apply_narration_emphasis(npc_text, emphasis_markers),
        "npc": {
            **npc,
            "text": apply_narration_emphasis(npc_text, emphasis_markers),
        },
        "rewards_block": apply_narration_emphasis(rewards_text, emphasis_markers),
        "emphasis_markers": emphasis_markers,
        "speaker_turns": speaker_turns,
        "markdown": markdown,
    }


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class NPCReaction:
    """An NPC's reaction to a scene event."""
    npc_id: str = ""
    npc_name: str = ""
    reaction: str = ""
    dialogue: str = ""
    emotion: str = "neutral"
    intent: str = ""


@dataclass
class NarrativeResult:
    """Complete result from scene narration."""
    narrative: str
    choices: List[Dict[str, Any]] = field(default_factory=list)
    npc_reactions: List[NPCReaction] = field(default_factory=list)
    dialogue_blocks: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _normalize_response_length(value: Any) -> str:
    value = str(value or "").strip().lower()
    if value in ("short", "medium", "long"):
        return value
    return "short"


def _response_length_prompt_rules(response_length: str) -> str:
    response_length = _normalize_response_length(response_length)

    if response_length == "long":
        return (
            "NARRATOR: 5 to 7 sentences describing the scene.\n"
            "ACTION: 5 to 7 sentences describing the result of the player's action.\n"
            "NPC: <npc_name>: \"no restrictions on length\" (omit if none)\n"
            "REWARD: <xp/items if any, else omit>"
        )

    if response_length == "medium":
        return (
            "NARRATOR: 3 to 5 sentences describing the scene.\n"
            "ACTION: 3 to 5 sentences describing the result of the player's action.\n"
            "NPC: <npc_name>: \"3 to 5 short sentences\" (omit if none)\n"
            "REWARD: <xp/items if any, else omit>"
        )

    return (
        "NARRATOR: 2 to 3 short sentence describing the scene.\n"
        "ACTION: 2 to 3 short sentence describing the result of the player's action.\n"
        "NPC: <npc_name>: \"2 - 3 short reply\" (omit if none)\n"
        "REWARD: <xp/items if any, else omit>"
    )


def build_scene_prompt(scene, narration_context, tone="dramatic"):
    """Build an LLM prompt to narrate a scene with strict structured output format.

    Returns:
        Prompt string for the LLM.
    """
    # ✅ Apply scene grounding FIRST before any prompt construction
    from app.rpg.session.runtime import (
        _apply_grounded_scene_overlay,
        _derive_grounded_scene_context,
        _normalize_prompt_location_name,
    )
    simulation_state = narration_context.get("simulation_state") or {}
    runtime_state = narration_context.get("runtime_state") or {}
    turn_result = narration_context.get("resolved_result") or {}
    
    grounded = _derive_grounded_scene_context(simulation_state, runtime_state, turn_result)
    scene = _apply_grounded_scene_overlay(scene, grounded)
    
    # ✅ Get final values from authoritative grounded state
    title = _safe_str(scene.get("title") or grounded.get("scene_title")).strip() or "Current Scene"
    summary = _safe_str(scene.get("summary") or grounded.get("scene_summary")).strip()
    
    # ✅ Normalize actors: convert dicts to names, always have safe fallback
    raw_actors = _safe_list(scene.get("actors") or grounded.get("present_actor_names"))
    actors = []
    for a in raw_actors:
        if isinstance(a, dict):
            actors.append(_safe_str(a.get("name") or a.get("id") or "Unknown"))
        else:
            actors.append(_safe_str(a))
    
    # ✅ Hard fallback: Actors present is never empty
    if not actors:
        actors = ["Other people nearby"]
    
    raw_location = _safe_str(scene.get("location_name") or turn_result.get("location_name")).strip()
    location = _normalize_prompt_location_name(raw_location, _safe_str(grounded.get("location_name"))) or "Current Location"
    stakes = scene.get("stakes", "much is at stake")
    tension = scene.get("tension", "moderate")

    actor_list = ""
    if actors:
        if isinstance(actors, list):
            actor_list = "\n".join(f"  - {a}" for a in actors)
        elif isinstance(actors, dict):
            actor_list = "\n".join(f"  - {k}: {v}" for k, v in actors.items())
        else:
            actor_list = str(actors)

    settings = _safe_dict(narration_context.get("settings"))
    response_length = _normalize_response_length(settings.get("response_length"))
    length_rules = _response_length_prompt_rules(response_length)
    
    print("[RPG LENGTH DEBUG] response_length =", response_length)
    print("[RPG LENGTH DEBUG] length_rules =", length_rules)

    safe_context = _build_safe_prompt_context(scene, narration_context)
    logger.debug("[RPG PROMPT] Scene title: %s, location: %s", title, location)
    logger.debug("[RPG PROMPT] Narration context keys: %s", list(narration_context.keys()))
    logger.debug("[RPG PROMPT] Safe context: %s", safe_context)

    prompt = f"""You are a deterministic RPG narration engine.

YOUR ONLY TASK: Generate narration for a player's action in an RPG.

STRICT OUTPUT FORMAT (follow exactly):

{length_rules}

IMPORTANT RULES:
- Output ONLY the 4 lines shown above
- NO extra text, explanations, or commentary
- NO faction goals, loyalty, awareness, or ambient content
- NO markdown, formatting, or special characters
- NO content about ticks, time, or system messages
- Just the structured response

SCENE:
Title: {title}
Location: {location}
Tone: {tone}
Tension: {tension}
Summary: {summary}
Actors present:
{actor_list}
Stakes: {stakes}

CONTEXT:
{safe_context}
"""
    logger.debug("[RPG PROMPT] Final prompt length: %d", len(prompt))
    return prompt


def build_npc_reaction_prompt(
    npc: Dict[str, Any],
    scene: Dict[str, Any],
    narrative: str,
    *,
    state: Optional[Dict[str, Any]] = None,
) -> str:
    """Build a prompt to generate an individual NPC reaction.

    Args:
        npc: NPC dict with name, personality, goals, memory, relationships, etc.
        scene: Current scene dict.
        narrative: The generated narrative text.
        state: Optional game state dict.

    Returns:
        Prompt string for the LLM.
    """
    npc_name = npc.get("name", "Unknown NPC")
    npc_personality = npc.get("personality", "")
    npc_goals = npc.get("goals", "")
    npc_relation = npc.get("relation_to_player", "neutral")
    scene_title = scene.get("title", "Unknown Scene")

    # Phase 5.1: Inject NPC state (memory, beliefs, relationships)
    # Phase 6: Enhanced with deterministic mind context
    npc_memory = npc.get("memory_summary", "")
    npc_beliefs = npc.get("beliefs", npc.get("belief_summary", {}))
    npc_relationships = npc.get("relationships", {})
    npc_active_goals = npc.get("active_goals", [])
    npc_last_decision = npc.get("last_decision", {})

    personality_info = f"Personality: {npc_personality}" if npc_personality else ""
    goals_info = f"Goals: {npc_goals}" if npc_goals else ""
    relation_info = f"Relation to player: {npc_relation}" if npc_relation else ""
    memory_info = f"Recent memory: {npc_memory}" if npc_memory else ""
    beliefs_info = f"Current beliefs: {', '.join(str(v) for v in npc_beliefs.values())}" if npc_beliefs else ""
    relationships_info = f"Relationships: {npc_relationships}" if npc_relationships else ""
    rumor_info = f"Rumors in circulation: {scene.get('active_rumors', [])}" if scene.get("active_rumors") else ""
    alliance_info = f"Active alliances: {scene.get('active_alliances', [])}" if scene.get("active_alliances") else ""
    faction_position_info = f"Faction positions: {scene.get('faction_positions', {})}" if scene.get("faction_positions") else ""
    # Phase 8.3: Add sandbox context to scene prompt
    sandbox_info = f"Sandbox summary: {scene.get('sandbox_summary', {})}" if scene.get("sandbox_summary") else ""
    world_consequence_info = f"Recent world consequences: {scene.get('world_consequences', [])}" if scene.get("world_consequences") else ""
    goals_list_info = f"Active goals: {npc_active_goals}" if npc_active_goals else ""
    last_decision_info = f"Last decision: {npc_last_decision}" if npc_last_decision else ""
    # Phase 7: Add debug context info for explainability
    debug_context_info = f"Scene debug context: {scene.get('debug_context', {})}" if scene.get("debug_context") else ""

    prompt = f"""You are generating NPC reactions for an RPG.

Character: {npc_name}
{personality_info}
{goals_info}
{relation_info}
{memory_info}
{beliefs_info}
{relationships_info}
{rumor_info}
{alliance_info}
    {faction_position_info}
    {sandbox_info}
    {world_consequence_info}
    {goals_list_info}
    {last_decision_info}
    {debug_context_info}

Scene: {scene_title}

Narrative:
{narrative[:1000]}

=== INSTRUCTIONS ===
Describe {npc_name}'s internal reaction to what just happened.
- Use the NPC's active goals to shape what they want right now.
- Use belief_summary about the player to determine tone.
- Use memory_summary to maintain continuity.
- Use last_decision so reactions align with recent intent.
- Do not contradict the provided structured state.
Then provide a short line of dialogue they might say.
Specify their emotional state (one of: calm, tense, angry, fearful, curious, excited, neutral).
Specify their immediate intent (one of: observe, act, confront, flee, negotiate, wait).

Respond ONLY in JSON format:
{{
  "reaction": "...",
  "dialogue": "...",
  "emotion": "...",
  "intent": "..."
}}
"""
    return prompt


def build_choice_prompt(
    scene: Dict[str, Any],
    narrative: str,
    *,
    num_choices: int = 3,
    action_hooks: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Build a prompt to generate player choices.

    Args:
        scene: Current scene dict.
        narrative: The narrative text.
        num_choices: Number of choices to generate.
        action_hooks: Optional list of action hooks from the scene.

    Returns:
        Prompt string for the LLM.
    """
    title = scene.get("title", "Scene")
    stakes = scene.get("stakes", "")
    source = scene.get("id", scene.get("source", ""))

    # Phase 5.1: Build action hooks for choice → action binding
    hooks_text = ""
    if action_hooks:
        hooks_text = "\nAvailable action types:\n"
        for hook in action_hooks:
            hooks_text += f"  - {hook.get('type', 'unknown')}: target={hook.get('target_id', source)}\n"
    else:
        # Default action hooks
        hooks_text = f"""
Available action types:
  - intervene_thread: target={source}
  - escalate_conflict: target={source}
  - observe_situation: target={source}
"""

    prompt = f"""You are generating player choices for an RPG scene.

Scene: {title}
Stakes: {stakes}
{hooks_text}
Narrative situation:
{narrative[-500:]}

=== INSTRUCTIONS ===
Generate exactly {num_choices} meaningful choices for the player.
Each choice should have:
  - A short, action-oriented description (5-10 words)
  - An implied risk or consequence
  - A distinct approach (combat, stealth, diplomacy, observation, etc.)
  - A mapped action type from the available action types above

Respond ONLY in JSON format:
{{
  "choices": [
    {{
      "text": "...",
      "type": "action|observe|dialogue|stealth|combat|diplomacy",
      "action": {{
        "type": "intervene_thread|escalate_conflict|observe_situation|...",
        "target_id": "..."
      }}
    }}
  ]
}}
"""
    return prompt


# ---------------------------------------------------------------------------
# Response parsers
# ---------------------------------------------------------------------------

def parse_scene_response(text: str) -> Dict[str, Any]:
    """Parse a raw LLM narrative response.

    Returns raw parsed fields only.
    Parses structured output format directly from LLM response.
    More flexible parsing that looks for keywords anywhere in the text.

    Args:
        text: Raw LLM response text.

    Returns:
        Dict with parsed fields.
    """
    logger.debug("[RPG PARSE] Starting to parse response, length: %d", len(text))

    result = {
        "narrator": "",
        "action": "",
        "npc": {
            "speaker_id": "",
            "name": "",
            "text": "",
            "emotion": "",
            "portrait": "",
        },
        "reward": "",
    }

    # Clean up the text
    text = _safe_str(text).strip()
    logger.debug("[RPG PARSE] Cleaned text: %r", text[:200] + "..." if len(text) > 200 else text)

    # Look for patterns anywhere in the text
    import re

    # NARRATOR pattern
    narrator_match = re.search(r'NARRATOR:\s*(.+?)(?=\n[A-Z]+:|\n*$)', text, re.DOTALL | re.IGNORECASE)
    if narrator_match:
        result["narrator"] = narrator_match.group(1).strip()
        logger.debug("[RPG PARSE] Found NARRATOR: %r", result["narrator"])

    # ACTION pattern
    action_match = re.search(r'ACTION:\s*(.+?)(?=\n[A-Z]+:|\n*$)', text, re.DOTALL | re.IGNORECASE)
    if action_match:
        result["action"] = action_match.group(1).strip()
        logger.debug("[RPG PARSE] Found ACTION: %r", result["action"])

    # NPC pattern
    npc_match = re.search(r'NPC:\s*(.+?)(?=\n[A-Z]+:|\n*$)', text, re.DOTALL | re.IGNORECASE)
    if npc_match:
        npc_text = npc_match.group(1).strip()
        logger.debug("[RPG PARSE] Found NPC text: %r", npc_text)
        if ":" in npc_text:
            name, text_part = npc_text.split(":", 1)
            npc_name = name.strip()
            result["npc"] = {
                "speaker_id": npc_name.lower().replace(" ", "_"),
                "name": npc_name,
                "text": _bound_text(text_part.strip().strip('"'), 180),
                "emotion": "",
                "portrait": "",
            }
            logger.debug("[RPG PARSE] Parsed NPC: name=%r, text=%r", npc_name, result["npc"]["text"])
        else:
            result["npc"] = {
                "speaker_id": "",
                "name": "",
                "text": _bound_text(npc_text, 180),
                "emotion": "",
                "portrait": "",
            }
            logger.debug("[RPG PARSE] Parsed NPC without name: text=%r", result["npc"]["text"])

    # REWARD pattern
    reward_match = re.search(r'REWARD:\s*(.+?)(?=\n[A-Z]+:|\n*$)', text, re.DOTALL | re.IGNORECASE)
    if reward_match:
        result["reward"] = _bound_text(reward_match.group(1).strip(), 120)
        logger.debug("[RPG PARSE] Found REWARD: %r", result["reward"])

    # Fallback: if no structured format found, try to extract from plain text
    if not result["narrator"] and not result["action"]:
        lines = text.split('\n')
        logger.debug("[RPG PARSE] No structured format found, using fallback with %d lines", len(lines))
        if lines:
            # Assume first line is narrator
            result["narrator"] = lines[0].strip()
            logger.debug("[RPG PARSE] Fallback NARRATOR: %r", result["narrator"])
        if len(lines) > 1:
            # Assume second line is action
            result["action"] = lines[1].strip()
            logger.debug("[RPG PARSE] Fallback ACTION: %r", result["action"])

    logger.debug("[RPG PARSE] Final parsed result: %s", result)
    return result


def _is_valid_scene_response(parsed: Dict[str, Any]) -> bool:
    parsed = _safe_dict(parsed)
    narrator = _safe_str(parsed.get("narrator")).strip()
    action = _safe_str(parsed.get("action")).strip()
    npc_text = _safe_str(parsed.get("npc", {}).get("text")).strip()

    # Accept any response that has at least some content
    has_content = bool(narrator or action or npc_text)
    is_valid = has_content and len((narrator + action + npc_text).strip()) > 10  # At least 10 chars of content

    logger.warning("[RPG VALIDATE] narrator=%r, action=%r, npc_text=%r -> valid=%s",
                narrator[:50], action[:50], npc_text[:50], is_valid)
    return is_valid


def _with_scene_response_defaults(parsed: Dict[str, Any]) -> Dict[str, Any]:
    parsed = _safe_dict(parsed)

    npc = parsed.get("npc")
    if not isinstance(npc, dict):
        parsed["npc"] = {
            "speaker_id": "unknown",
            "name": "",
            "text": _safe_str(npc).strip(),
            "emotion": "",
            "portrait": "",
        }
    if not parsed.get("narrator"):
        parsed["narrator"] = "You are here."
    if not parsed.get("action"):
        parsed["action"] = "You act."

    return parsed


def parse_npc_reaction(text: str, npc_id: str = "", npc_name: str = "") -> NPCReaction:
    """Parse an NPC reaction response.

    Phase 5.1: Attempts JSON parsing first, falls back to text extraction.

    Args:
        text: Raw LLM response for NPC reaction.
        npc_id: NPC identifier.
        npc_name: Fallback NPC name.

    Returns:
        NPCReaction dataclass instance.
    """
    # Phase 5.1: Try JSON parsing first
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return NPCReaction(
                npc_id=npc_id,
                npc_name=npc_name,
                reaction=data.get("reaction", ""),
                dialogue=data.get("dialogue", ""),
                emotion=data.get("emotion", "neutral").lower(),
                intent=data.get("intent", ""),
            )
    except (json.JSONDecodeError, TypeError):
        pass

    # Fallback: text extraction
    reaction = ""
    dialogue = ""
    emotion = "neutral"
    intent = ""

    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("REACTION:"):
            reaction = line[len("REACTION:"):].strip()
        elif line.startswith("DIALOGUE:"):
            dialogue = line[len("DIALOGUE:"):].strip().strip('"')
        elif line.startswith("EMOTION:"):
            emotion = line[len("EMOTION:"):].strip().lower()
        elif line.startswith("INTENT:"):
            intent = line[len("INTENT:"):].strip().lower()

    return NPCReaction(
        npc_id=npc_id,
        npc_name=npc_name,
        reaction=reaction,
        dialogue=dialogue,
        emotion=emotion,
        intent=intent,
    )


def parse_choices(text: str, source: str = "") -> List[Dict[str, Any]]:
    """Parse LLM-generated player choices.

    Phase 5.1: Attempts JSON parsing first, falls back to text extraction.
    Choices now include action binding for integration with apply_player_action.

    Args:
        text: Raw LLM response with numbered choices.
        source: Scene/source ID for action target binding.

    Returns:
        List of choice dicts with 'id', 'text', 'type', and 'action' keys.
    """
    # Phase 5.1: Try JSON parsing first
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "choices" in data:
            choices_data = data["choices"]
        elif isinstance(data, list):
            choices_data = data
        else:
            choices_data = []

        if choices_data:
            choices = []
            for i, c in enumerate(choices_data):
                if isinstance(c, dict):
                    action = c.get("action", {})
                    choices.append({
                        "id": f"choice_{i+1}",
                        "text": c.get("text", ""),
                        "type": c.get("type", "action"),
                        "action": {
                            "type": action.get("type", "intervene_thread"),
                            "target_id": action.get("target_id", source),
                        },
                    })
            if choices:
                return choices
    except (json.JSONDecodeError, TypeError):
        pass

    # Fallback: text extraction with default action binding
    choices = []
    choice_types = ["action", "observe", "dialogue", "stealth", "combat", "diplomacy"]
    action_types = ["intervene_thread", "observe_situation", "escalate_conflict"]

    for line in text.split("\n"):
        line = line.strip()
        if line and (line[0].isdigit() and line[1] in (".", ")")):
            choice_text = line[2:].strip()
            idx = len(choices) + 1
            choice_type = choice_types[idx % len(choice_types)]
            action_type = action_types[idx % len(action_types)]
            choices.append({
                "id": f"choice_{idx}",
                "text": choice_text,
                "type": choice_type,
                "action": {
                    "type": action_type,
                    "target_id": source,
                },
            })

    return choices if choices else [
        {"id": "choice_1", "text": "Take action", "type": "action", "action": {"type": "intervene_thread", "target_id": source}},
        {"id": "choice_2", "text": "Wait and observe", "type": "observe", "action": {"type": "observe_situation", "target_id": source}},
    ]


def apply_hooks_to_choices(
    choices: List[Dict[str, Any]],
    hooks: List[Dict[str, Any]],
    *,
    source: str = "",
) -> List[Dict[str, Any]]:
    """Inject action hooks into choices for binding.

    Phase 5.5: Maps scene action_hooks onto choice objects so that
    when a player selects a choice, the corresponding action is ready.

    Args:
        choices: List of choice dicts to update in-place.
        hooks: List of action hooks from the scene (e.g. from action_hooks).
        source: Fallback target_id when a hook has none.

    Returns:
        The same choices list, updated with action bindings.
    """
    for i, c in enumerate(choices):
        if i < len(hooks):
            hook = hooks[i]
            c["action"] = {
                "type": hook.get("type", "intervene_thread"),
                "target_id": hook.get("target_id", source),
            }
    return choices


# ---------------------------------------------------------------------------
# Scene narration service
# ---------------------------------------------------------------------------

class SceneNarrator:
    """Orchestrates scene narration with NPC reactions and player choices.

    This is the main entry point for Phase 5. It coordinates:
    1. Narrative generation from scene data
    2. NPC reaction generation
    3. Player choice generation
    4. Assembly into a complete NarrativeResult
    """

    def __init__(
        self,
        llm_gateway: Optional[Any] = None,
        *,
        default_tone: str = "dramatic",
        simulate_mode: bool = False,
    ):
        self.llm_gateway = llm_gateway
        self.default_tone = default_tone
        self.simulate_mode = simulate_mode
        self.live_mode = bool(llm_gateway) and not simulate_mode
        self._last_llm_success = False

    def narrate_scene(
        self,
        scene: Dict[str, Any],
        state: Dict[str, Any],
        *,
        tone: Optional[str] = None,
        include_npc_reactions: bool = True,
        include_choices: bool = True,
        max_npc_reactions: int = 3,
    ) -> NarrativeResult:
        """Generate a complete narrated scene.

        Args:
            scene: Scene dict to narrate.
            state: Current game state dict.
            tone: Override default tone.
            include_npc_reactions: Whether to generate NPC reactions.
            include_choices: Whether to generate player choices.
            max_npc_reactions: Max NPC reactions to generate.

        Returns:
            NarrativeResult with narrative, choices, and NPC reactions.
        """
        tone = tone or self.default_tone

        # Step 1: Generate narrative
        narrative = self._generate_narrative(scene, state, tone=tone)

        # Step 2: Generate NPC reactions
        npc_reactions: List[NPCReaction] = []
        if include_npc_reactions:
            npc_reactions = self._generate_npc_reactions(
                scene, narrative, state,
                max_reactions=max_npc_reactions,
            )

        # Step 3: Generate choices
        choices: List[Dict[str, Any]] = []
        if include_choices:
            choices = self._generate_choices(scene, narrative)

        # Step 4: Build dialogue blocks from NPC reactions
        dialogue_blocks = [
            {
                "speaker": r.npc_name,
                "npc_id": r.npc_id,
                "text": r.dialogue,
                "emotion": r.emotion,
            }
            for r in npc_reactions
            if r.dialogue
        ]

        # Phase 8: player-facing packaged view
        player_view = {
            "scene_id": scene.get("scene_id") or scene.get("id", ""),
            "scene_title": scene.get("title", ""),
            "mode": "scene",
            "active_npc_id": (
                npc_reactions[0].npc_id
                if npc_reactions
                else ""
            ),
            "encounter": build_encounter_view(scene, state),
            "active_rumors": list(scene.get("active_rumors") or [])[:3],
            "active_alliances": list(scene.get("active_alliances") or [])[:3],
            "faction_positions": dict(scene.get("faction_positions") or {}),
        }

        llm_success = getattr(self, "_last_llm_success", False)

        return NarrativeResult(
            narrative=narrative,
            choices=choices,
            npc_reactions=npc_reactions,
            dialogue_blocks=dialogue_blocks,
            metadata={
                "tone": tone,
                "scene_id": scene.get("id"),
                "npc_count": len(npc_reactions),
                "choice_count": len(choices),
                "llm_live": bool(self.live_mode and llm_success),
                "llm_attempted": bool(self.live_mode),
                "llm_fallback_used": not llm_success,
                "player_view": player_view,
                "sandbox_summary": scene.get("sandbox_summary", {}),
            },
        )

    def _generate_narrative(
        self,
        scene: Dict[str, Any],
        state: Dict[str, Any],
        tone: str,
    ) -> str:
        """Generate narrative text for a scene."""
        # Inject player_input from state into scene so simulation fallback sees it
        scene = dict(scene or {})
        if "player_input" not in scene and state:
            pi = state.get("player_input", "")
            if pi:
                scene["player_input"] = str(pi)

        if not self.live_mode:
            return self._simulate_narrative(scene, tone)

        try:
            prompt = build_scene_prompt(scene, state, tone=tone)
            response = _llm_text(self.llm_gateway, prompt, context={"scene": scene})
            parsed = parse_scene_response(response)
            narrative = parsed.get("narrative") or ""

            if narrative:
                self._last_llm_success = True
                return narrative
        except Exception:
            pass

        # fallback
        self._last_llm_success = False
        return self._simulate_narrative(scene, tone)

    def _generate_npc_reactions(
        self,
        scene: Dict[str, Any],
        narrative: str,
        state: Dict[str, Any],
        *,
        max_reactions: int = 3,
    ) -> List[NPCReaction]:
        """Generate NPC reactions for actors in the scene."""
        actors = scene.get("actors", [])
        if isinstance(actors, dict):
            actor_list = [{"id": k, "name": k, **v} for k, v in actors.items()]
        elif isinstance(actors, list):
            actor_list = [
                a if isinstance(a, dict) else {"id": a, "name": str(a)}
                for a in actors
            ]
        else:
            actor_list = [{"id": "unknown", "name": str(actors)}]

        reactions: List[NPCReaction] = []
        for actor in actor_list[:max_reactions]:
            npc_id = actor.get("id", "unknown")
            npc_name = actor.get("name", "Unknown")

            if not self.live_mode:
                reaction = self._simulate_npc_reaction(npc_name)
            else:
                try:
                    prompt = build_npc_reaction_prompt(actor, scene, narrative, state=state)
                    response = _llm_text(self.llm_gateway, prompt, context={"npc": npc_id})
                    reaction = parse_npc_reaction(response, npc_id=npc_id, npc_name=npc_name)
                    if reaction and reaction.reaction:
                        self._last_llm_success = True
                    else:
                        raise ValueError("empty reaction")
                except Exception:
                    self._last_llm_success = False
                    reaction = self._simulate_npc_reaction(npc_name)

            reactions.append(reaction)

        return reactions

    def _generate_choices(
        self,
        scene: Dict[str, Any],
        narrative: str,
    ) -> List[Dict[str, Any]]:
        """Generate player choices."""
        source = scene.get("id", scene.get("source", ""))
        action_hooks = scene.get("action_hooks", None)

        if not self.live_mode:
            return self._simulate_choices(scene, source)

        try:
            prompt = build_choice_prompt(scene, narrative, action_hooks=action_hooks)
            response = _llm_text(self.llm_gateway, prompt, context={"scene": scene.get("id")})
            parsed = parse_choices(response, source=source)
            if parsed:
                self._last_llm_success = True
                return parsed
        except Exception:
            pass

        self._last_llm_success = False
        return self._simulate_choices(scene, source)

    # ------------------------------------------------------------------
    # Simulation fallbacks (no LLM required)
    # ------------------------------------------------------------------

    @staticmethod
    def _simulate_narrative(scene: Dict[str, Any], tone: str) -> str:
        """Generate simulated narrative text without LLM.

        Incorporates player input and scene actors for varied responses.
        """
        title = scene.get("title", "The Scene")
        summary = scene.get("summary", "Events unfold around you.")
        stakes = scene.get("stakes", "much is at stake")
        player_input = scene.get("player_input", "")
        actors_data = scene.get("actors", [])

        # Extract NPC names from actor dicts
        npc_names = []
        if isinstance(actors_data, list):
            for a in actors_data[:5]:
                if isinstance(a, dict):
                    name = a.get("name", a.get("id", ""))
                    if name:
                        npc_names.append(str(name))
                else:
                    npc_names.append(str(a))
        elif isinstance(actors_data, dict):
            npc_names = list(actors_data.keys())[:5]

        npc_text = f"{', '.join(npc_names)} {'are' if len(npc_names) != 1 else 'is'} {'present' if npc_names else 'absent'}" if npc_names else "You are alone for now"

        # Acknowledge player's action
        action_text = ""
        if player_input:
            action_lower = player_input.lower().strip()
            if any(w in action_lower for w in ("look", "observe", "see", "examine", "search")):
                action_text = "You carefully observe your surroundings. "
            elif any(w in action_lower for w in ("talk", "speak", "ask", "question", "whisper", "say")):
                npc = npc_names[0] if npc_names else "those nearby"
                action_text = f"You try to speak with {npc}. "
            elif any(w in action_lower for w in ("attack", "hit", "strike", "kill", "fight")):
                npc = npc_names[0] if npc_names else "your target"
                action_text = f"You lash out toward {npc}. "
            elif any(w in action_lower for w in ("move", "go", "walk", "run", "leave", "head")):
                loc = scene.get("location", "another area")
                action_text = f"You start to move toward {loc}. "
            elif any(w in action_lower for w in ("take", "grab", "pick up", "use")):
                action_text = "You reach for something. "
            else:
                action_text = f"Your words echo: \"{player_input[:80]}\". "
        else:
            action_text = "You hesitate, weighing your options. "

        title_scene = f"{title}\n\n" if title != "The Scene" else ""

        return (
            f"{title_scene}{action_text}"
            f"{summary}\n\n"
            f"{npc_text}, the weight of the moment pressing down. "
            f"The stakes are clear: {stakes}. "
            f"The air is thick with {tone} tension as the scene unfolds."
        )

    @staticmethod
    def _simulate_npc_reaction(npc_name: str) -> NPCReaction:
        """Generate a simulated NPC reaction without LLM."""
        emotions = ["tense", "curious", "determined", "cautious", "alert"]
        intents = ["observe", "act", "confront", "wait", "negotiate"]
        reactions = [
            f"{npc_name} considers the situation carefully.",
            f"{npc_name}'s expression grows serious.",
            f"{npc_name} shifts uneasily, weighing options.",
            f"{npc_name} meets your gaze with quiet resolve.",
        ]
        dialogues = [
            "We should act quickly.",
            "This changes everything.",
            "I've seen this before.",
            "What do you think we should do?",
        ]
        # Use hash of name for deterministic selection
        idx = hash(npc_name)
        return NPCReaction(
            npc_id=npc_name.lower().replace(" ", "_"),
            npc_name=npc_name,
            reaction=reactions[idx % len(reactions)],
            dialogue=dialogues[idx % len(dialogues)],
            emotion=emotions[idx % len(emotions)],
            intent=intents[idx % len(intents)],
        )

    @staticmethod
    def _simulate_choices(scene: Dict[str, Any], source: str = "") -> List[Dict[str, Any]]:
        """Generate simulated choices without LLM.

        Adapts choices based on player input for more relevant options.
        """
        player_input = scene.get("player_input", "").lower().strip() if isinstance(scene.get("player_input", ""), str) else ""

        # Base choice pool — rotate based on what player did
        if player_input:
            if any(w in player_input for w in ("talk", "speak", "ask", "question")):
                # After talking, offer follow-up options
                return [
                    {"id": "choice_1", "text": "Press for more information", "type": "dialogue", "action": {"type": "escalate_conflict", "target_id": source}},
                    {"id": "choice_2", "text": "Change the subject", "type": "dialogue", "action": {"type": "intervene_thread", "target_id": source}},
                    {"id": "choice_3", "text": "Step back and consider", "type": "observe", "action": {"type": "observe_situation", "target_id": source}},
                ]
            elif any(w in player_input for w in ("look", "observe", "see", "examine", "search")):
                # After observing, offer action options
                return [
                    {"id": "choice_1", "text": "Act on what you've learned", "type": "action", "action": {"type": "intervene_thread", "target_id": source}},
                    {"id": "choice_2", "text": "Investigate further", "type": "observe", "action": {"type": "observe_situation", "target_id": source}},
                    {"id": "choice_3", "text": "Share your findings", "type": "dialogue", "action": {"type": "escalate_conflict", "target_id": source}},
                ]
            elif any(w in player_input for w in ("attack", "hit", "strike", "kill", "fight", "draw")):
                # After combat action, offer escalation
                return [
                    {"id": "choice_1", "text": "Press the attack", "type": "action", "action": {"type": "escalate_conflict", "target_id": source}},
                    {"id": "choice_2", "text": "Stand down", "type": "observe", "action": {"type": "intervene_thread", "target_id": source}},
                    {"id": "choice_3", "text": "Call for parley", "type": "dialogue", "action": {"type": "intervene_thread", "target_id": source}},
                ]
            elif any(w in player_input for w in ("move", "go", "walk", "run", "leave", "head")):
                # After movement
                return [
                    {"id": "choice_1", "text": "Continue forward", "type": "action", "action": {"type": "intervene_thread", "target_id": source}},
                    {"id": "choice_2", "text": "Reassess your route", "type": "observe", "action": {"type": "observe_situation", "target_id": source}},
                    {"id": "choice_3", "text": "Return to where you started", "type": "action", "action": {"type": "intervene_thread", "target_id": source}},
                ]

        # Default varied choices
        return [
            {"id": "choice_1", "text": "Take decisive action", "type": "action", "action": {"type": "intervene_thread", "target_id": source}},
            {"id": "choice_2", "text": "Observe the situation carefully", "type": "observe", "action": {"type": "observe_situation", "target_id": source}},
            {"id": "choice_3", "text": "Speak with those present", "type": "dialogue", "action": {"type": "escalate_conflict", "target_id": source}},
        ]


# ---------------------------------------------------------------------------
# Convenience functions (service layer)
# ---------------------------------------------------------------------------

def _generate_live_narrative(
    scene: Dict[str, Any],
    narration_context: Dict[str, Any],
    llm_gateway: Any,
    tone: str = "dramatic",
    retry_on_invalid: bool = True,
    debug_logging: bool = False,
) -> str:
    """Generate narrative using LLM."""
    # Inject player_input from narration_context into scene
    scene = dict(scene or {})
    if "player_input" not in scene and narration_context:
        pi = narration_context.get("player_input", "")
        if pi:
            scene["player_input"] = str(pi)

    prompt = build_scene_prompt(scene, narration_context, tone=tone)
    if debug_logging:
        logger.warning("[RPG LLM PROMPT]\n%s", prompt)
    else:
        logger.debug("[RPG LLM PROMPT] prompt length: %d", len(prompt))
    max_attempts = 2 if retry_on_invalid else 1
    for attempt in range(max_attempts):
        try:
            response = _llm_text(llm_gateway, prompt, context={})
            if debug_logging:
                logger.warning("[RPG LLM RAW OUTPUT attempt %d]\n%s", attempt + 1, response)
            else:
                logger.debug("[RPG LLM RAW OUTPUT attempt %d] length: %d", attempt + 1, len(str(response or "")))

            # Check if response contains invalid content (like ambient updates)
            response_lower = _safe_str(response).lower()
            if any(phrase in response_lower for phrase in [
                "faction loyalty baseline",
                "maintain awareness",
                "playertick",
                "📜 📜"
            ]):
                logger.error("LLM response contains invalid ambient-like content, rejecting: %s", response[:200])
                continue

            parsed = parse_scene_response(response)
            if debug_logging:
                logger.warning("[RPG PARSED RESPONSE]\n%s", parsed)
            else:
                logger.debug("[RPG PARSED RESPONSE] keys: %s", list(parsed.keys()) if isinstance(parsed, dict) else type(parsed))

            if _is_valid_scene_response(parsed):
                logger.debug("LLM response validation successful")
                return response
            else:
                logger.error("LLM response failed validation, parsed: %s", parsed)
        except Exception as e:
            logger.exception("Exception during LLM narration")

    # fallback if LLM fails format
    logger.error("Structured RPG narration LLM output failed validation after %d attempt(s)", max_attempts)
    return _structured_fallback_response()


def _simulate_narrative(scene: Dict[str, Any], narration_context: Dict[str, Any], tone: str = "dramatic") -> str:
    """Generate simulated narrative text without LLM.

    Incorporates player input and scene actors for varied responses.
    """
    title = scene.get("title", "The Scene")
    summary = scene.get("summary", "Events unfold around you.")
    stakes = scene.get("stakes", "much is at stake")
    player_input = narration_context.get("player_input", scene.get("player_input", ""))
    actors_data = scene.get("actors", [])

    # Extract NPC names from actor dicts
    npc_names = []
    if isinstance(actors_data, list):
        for a in actors_data[:5]:
            if isinstance(a, dict):
                name = a.get("name", a.get("id", ""))
                if name:
                    npc_names.append(str(name))
            else:
                npc_names.append(str(a))
    elif isinstance(actors_data, dict):
        npc_names = list(actors_data.keys())[:5]

    npc_text = f"{', '.join(npc_names)} {'are' if len(npc_names) != 1 else 'is'} {'present' if npc_names else 'absent'}" if npc_names else "You are alone for now"

    # Acknowledge player's action
    action_text = ""
    if player_input:
        action_lower = player_input.lower().strip()
        if any(w in action_lower for w in ("look", "observe", "see", "examine", "search")):
            action_text = "You carefully observe your surroundings. "
        elif any(w in action_lower for w in ("talk", "speak", "ask", "question", "whisper", "say")):
            npc = npc_names[0] if npc_names else "those nearby"
            action_text = f"You try to speak with {npc}. "
        elif any(w in action_lower for w in ("attack", "hit", "strike", "kill", "fight")):
            npc = npc_names[0] if npc_names else "your target"
            action_text = f"You lash out toward {npc}. "
        elif any(w in action_lower for w in ("move", "go", "walk", "run", "leave", "head")):
            loc = scene.get("location", "another area")
            action_text = f"You start to move toward {loc}. "
        elif any(w in action_lower for w in ("take", "grab", "pick up", "use")):
            action_text = "You reach for something. "
        else:
            action_text = f"Your words echo: \"{player_input[:80]}\". "
    else:
        action_text = "You hesitate, weighing your options. "

    title_scene = f"{title}\n\n" if title != "The Scene" else ""

    return (
        f"{title_scene}{action_text}"
        f"{summary}\n\n"
        f"{npc_text}, the weight of the moment pressing down. "
        f"The stakes are clear: {stakes}. "
        f"The air is thick with {tone} tension as the scene unfolds."
    )


def narrate_scene(
    scene: Dict[str, Any],
    narration_context: Dict[str, Any],
    llm_gateway: Any | None = None,
    tone: str = "dramatic",
    retry_on_invalid: bool = True,
    debug_logging: bool = False,
) -> Dict[str, Any]:
    scene = _safe_dict(scene)
    narration_context = _safe_dict(narration_context)

    if llm_gateway:
        llm_narrative = _generate_live_narrative(
            scene,
            narration_context,
            llm_gateway=llm_gateway,
            tone=tone,
            retry_on_invalid=retry_on_invalid,
            debug_logging=debug_logging,
        )
        used_llm = "[ERROR:" not in llm_narrative
    else:
        llm_narrative = _simulate_narrative(scene, narration_context, tone=tone)
        used_llm = False

    structured = build_structured_narration(scene, narration_context, llm_narrative)

    return {
        "narrative": _safe_str(structured.get("markdown")),
        "narration": _safe_str(structured.get("markdown")),
        "structured_narration": structured,
        "speaker_turns": _safe_list(structured.get("speaker_turns")),
        "used_llm": used_llm,
        "raw_llm_narrative": _safe_str(llm_narrative),
        "llm_error": "[ERROR:" in _safe_str(llm_narrative),
    }


def play_scene(
    scene: Dict[str, Any],
    state: Dict[str, Any],
    *,
    llm_gateway: Optional[Any] = None,
    tone: str = "dramatic",
) -> Dict[str, Any]:
    """Play a scene and return narrated result as dict.

    This is the main service function called by routes.

    Args:
        scene: Scene dict to play.
        state: Game state dict.
        llm_gateway: Optional LLM gateway for real narration.
        tone: Narrative tone.

    Returns:
        Dict suitable for JSON response.
    """
    narrator = SceneNarrator(
        llm_gateway=llm_gateway,
        default_tone=tone,
        simulate_mode=not bool(llm_gateway),
    )
    result = narrator.narrate_scene(scene, state, tone=tone)

    return {
        "narrative": result.narrative,
        "choices": result.choices,
        "npc_reactions": [
            {
                "npc_id": r.npc_id,
                "npc_name": r.npc_name,
                "dialogue": r.dialogue,
                "emotion": r.emotion,
                "intent": r.intent,
            }
            for r in result.npc_reactions
        ],
        "dialogue_blocks": result.dialogue_blocks,
        "metadata": result.metadata,
    }


def apply_legacy_narration_emphasis(narration_payload: dict) -> dict:
    """Apply markdown emphasis to important narration elements.

    Deterministically formats structured result fields — does NOT ask
    the LLM to bold things randomly.
    """
    import re
    payload = dict(narration_payload or {})
    text = str(payload.get("narration") or payload.get("text") or payload.get("content") or "")

    if not text:
        return payload

    # Bold item names (from items list if available)
    items = payload.get("items", [])
    for item in (items if isinstance(items, list) else []):
        if isinstance(item, dict):
            name = str(item.get("name", ""))
            if name and len(name) > 2:
                text = text.replace(name, f"**{name}**")

    # Bold quest updates
    text = re.sub(r'(?i)(quest updated?:?\s*)', r'**\1**', text)
    text = re.sub(r'(?i)(quest complete[d]?:?\s*)', r'**\1**', text)

    # Bold damage numbers
    text = re.sub(r'(\d+)\s+(damage)', r'**\1 \2**', text)

    # Bold level ups
    text = re.sub(r'(?i)(level up!?)', r'**\1**', text)
    text = re.sub(r'(?i)(leveled? up!?)', r'**\1**', text)

    # Bold named enemies in combat results
    combat = payload.get("combat_result", {})
    if isinstance(combat, dict):
        enemy_name = str(combat.get("enemy_name") or combat.get("target_name") or "")
        if enemy_name and len(enemy_name) > 2:
            text = text.replace(enemy_name, f"**{enemy_name}**")

    # Avoid double-bold
    text = text.replace("****", "**")

    # Update payload
    if "narration" in payload:
        payload["narration"] = text
    elif "text" in payload:
        payload["text"] = text
    elif "content" in payload:
        payload["content"] = text

    return payload


# ── Living-world: ambient narration (Phase 5) ─────────────────────────────

_AMBIENT_TEMPLATES = {
    "npc_to_player": "{speaker_name} turns to you: \"{text}\"",
    "npc_to_npc": "{speaker_name} speaks to {target_name}: \"{text}\"",
    "npc_reaction": "{speaker_name} reacts: \"{text}\"",
    "companion_comment": "{speaker_name} says: \"{text}\"",
    "warning": "{speaker_name} warns: \"{text}\"",
    "demand": "{speaker_name} demands: \"{text}\"",
    "taunt": "{speaker_name} taunts: \"{text}\"",
    "gossip": "{speaker_name} mutters: \"{text}\"",
    "world_event": "{text}",
    "arrival": "{text}",
    "departure": "{text}",
    "combat_start": "⚔️ {text}",
    "system_summary": "📜 {text}",
}

_AMBIENT_PROMPTS = {
    "npc_to_player": (
        "You are {speaker_name}, an NPC in a living fantasy world. "
        "Write one short sentence addressed to the player. "
        "Emotion: {emotion}. Context: {context}. "
        "Respond ONLY with the spoken line, no quotation marks."
    ),
    "npc_to_npc": (
        "You are {speaker_name}, an NPC. Write one short sentence spoken to {target_name}. "
        "Emotion: {emotion}. Context: {context}. "
        "Respond ONLY with the spoken line, no quotation marks."
    ),
    "companion_comment": (
        "You are {speaker_name}, a companion of the player. "
        "Write one short observation or comment about the current situation. "
        "Context: {context}. "
        "Respond ONLY with the spoken line, no quotation marks."
    ),
    "warning": (
        "You are {speaker_name}. Write a brief, tense warning directed at the player. "
        "Context: {context}. "
        "Respond ONLY with the spoken line, no quotation marks."
    ),
    "world_event": (
        "Write one concise sentence narrating this world event for the player: {text}. "
        "Context: {context}. "
        "Respond ONLY with the narration sentence."
    ),
    "system_summary": (
        "Summarize these world changes in one or two sentences for a returning player: {text}. "
        "Context: {context}. "
        "Respond ONLY with the summary."
    ),
}


def narrate_ambient_update(
    *,
    ambient_update: Dict[str, Any],
    simulation_state: Dict[str, Any],
    current_scene: Dict[str, Any],
    llm_gateway: Any = None,
) -> Dict[str, Any]:
    """Narrate an ambient update for player presentation.
    
    If LLM is available, uses it for stylistic phrasing.
    Always falls back to deterministic templates if LLM is unavailable.
    LLM only styles phrasing — never invents world truth.
    
    Returns:
        {
            "text": str,
            "speaker_turns": list,
            "used_app_llm": bool,
            "raw_llm_narrative": str,
            "structured": dict,
        }
    """
    ambient_update = _safe_dict(ambient_update)
    simulation_state = _safe_dict(simulation_state)
    current_scene = _safe_dict(current_scene)
    
    kind = _safe_str(ambient_update.get("kind"))
    speaker_id = _safe_str(ambient_update.get("speaker_id"))
    speaker_name = _safe_str(ambient_update.get("speaker_name")) or speaker_id
    target_name = _safe_str(ambient_update.get("target_name"))
    raw_text = _safe_str(ambient_update.get("text"))
    emotion = _safe_str(ambient_update.get("emotion")) or "neutral"
    
    # Build scene context summary for LLM prompt
    scene_summary = _safe_str(current_scene.get("summary") or current_scene.get("scene"))
    context = scene_summary[:200] if scene_summary else "The world stirs."
    
    used_llm = False
    raw_llm_narrative = ""
    narrated_text = raw_text
    
    # Try LLM narration if available
    if llm_gateway and kind in _AMBIENT_PROMPTS:
        try:
            prompt_template = _AMBIENT_PROMPTS[kind]
            prompt = prompt_template.format(
                speaker_name=speaker_name,
                target_name=target_name,
                emotion=emotion,
                context=context,
                text=raw_text,
            )
            llm_response = _llm_text(llm_gateway, prompt)
            if llm_response and "[ERROR:" not in llm_response:
                narrated_text = _bound_text(llm_response.strip(), 250)
                raw_llm_narrative = llm_response
                used_llm = True
        except Exception:
            pass  # Fall through to template
    
    # Template fallback
    if not used_llm:
        template = _AMBIENT_TEMPLATES.get(kind, "{text}")
        narrated_text = template.format(
            speaker_name=speaker_name,
            target_name=target_name,
            text=raw_text,
        )
    
    # Build speaker turns for dialogue rendering
    speaker_turns: List[Dict[str, Any]] = []
    if speaker_id and kind in ("npc_to_player", "npc_to_npc", "companion_comment", "warning", "demand", "taunt", "gossip", "npc_reaction"):
        speaker_turns.append({
            "speaker_id": speaker_id,
            "name": speaker_name,
            "text": narrated_text,
            "emotion": emotion,
            "ambient": True,
        })
    
    return {
        "text": narrated_text,
        "speaker_turns": speaker_turns,
        "used_app_llm": used_llm,
        "raw_llm_narrative": raw_llm_narrative,
        "structured": {
            "kind": kind,
            "speaker_id": speaker_id,
            "speaker_name": speaker_name,
            "target_id": _safe_str(ambient_update.get("target_id")),
            "target_name": target_name,
            "ambient": True,
        },
    }