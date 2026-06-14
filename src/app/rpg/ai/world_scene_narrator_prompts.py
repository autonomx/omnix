"""Split helpers for RPG world scene narration."""
from __future__ import annotations

# ruff: noqa: F401,F403,F405
from app.rpg.ai.world_scene_narrator_common import *
from app.rpg.ai.world_scene_narrator_payloads import *
from app.rpg.ai.world_scene_narrator_structured import *
from app.rpg.session.memory_prompt import (
    build_relevant_memory_context_from_runtime,
    build_relevant_memory_prompt_block,
)


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


def _current_turn_semantic_visible_response(narration_context: Dict[str, Any]) -> Dict[str, Any]:
    """Return visible-response guidance bound to the current turn only."""
    narration_context = _safe_dict(narration_context)
    turn_contract = _safe_dict(narration_context.get("turn_contract"))
    resolved = _safe_dict(narration_context.get("resolved_result"))
    contract_resolved = _safe_dict(
        turn_contract.get("resolved_result") or turn_contract.get("resolved_action")
    )
    action = _safe_dict(turn_contract.get("action") or narration_context.get("action"))
    action_metadata = _safe_dict(action.get("metadata"))
    semantic_action = _safe_dict(turn_contract.get("semantic_action"))
    metadata_semantic_action = _safe_dict(action_metadata.get("semantic_action"))
    resolved_semantic_action = _safe_dict(
        resolved.get("semantic_action") or contract_resolved.get("semantic_action")
    )

    candidates = (
        ("turn_contract.current_turn_visible_response", turn_contract.get("current_turn_visible_response")),
        ("turn_contract.semantic_visible_response", turn_contract.get("semantic_visible_response")),
        ("turn_contract.semantic_action.visible_response", semantic_action.get("visible_response")),
        ("turn_contract.semantic_action.semantic_visible_response", semantic_action.get("semantic_visible_response")),
        ("resolved_result.visible_response", resolved.get("visible_response")),
        ("turn_contract.resolved_result.visible_response", contract_resolved.get("visible_response")),
        ("resolved_result.semantic_action.visible_response", resolved_semantic_action.get("visible_response")),
        ("action.metadata.semantic_action.visible_response", metadata_semantic_action.get("visible_response")),
        ("action.metadata.semantic_action.semantic_visible_response", metadata_semantic_action.get("semantic_visible_response")),
        ("action.metadata.visible_response_if_no_runtime_needed", action_metadata.get("visible_response_if_no_runtime_needed")),
    )

    for source, value in candidates:
        visible = _safe_dict(value)
        if not visible:
            continue
        npc = _safe_dict(visible.get("npc"))
        narration = _safe_str(visible.get("narration") or visible.get("text")).strip()
        npc_line = _safe_str(npc.get("line") or npc.get("text")).strip()
        npc_speaker = _safe_str(npc.get("speaker") or npc.get("name")).strip()
        if not narration and not npc_line:
            continue
        return {
            "source": source,
            "narration": narration[:600],
            "npc": {
                "speaker": npc_speaker[:120],
                "line": npc_line[:600],
            },
        }
    return {}


def _compact_prompt_json(value: Any, max_chars: int, fallback: Any = None) -> str:
    if fallback is None:
        fallback = {}
    try:
        text = json.dumps(value if value is not None else fallback, ensure_ascii=False, separators=(",", ":"), default=str)
    except Exception:
        text = _safe_str(value)
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "...[truncated]"
    return text


def _compact_prompt_text(value: Any, max_chars: int) -> str:
    text = " ".join(_safe_str(value).split())
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "...[truncated]"
    return text


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
    actors = [a for a in actors if _safe_str(a).strip()][:10]

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

    safe_context = _build_safe_prompt_context(scene, narration_context)

    # Build conversation threads context
    conversation_threads = _safe_list(narration_context.get("conversation_threads"))
    conversation_threads_block = ""
    if conversation_threads:
        lines = ["ONGOING CONVERSATION THREADS:"]
        for thread in conversation_threads[:2]:
            thread = _safe_dict(thread)
            topic = _safe_dict(thread.get("topic"))
            lines.append(
                f"- {_safe_str(thread.get('thread_id'))} | participants={', '.join(_safe_str(p) for p in _safe_list(thread.get('participants'))[:4])} | topic={_compact_prompt_text(topic.get('summary'), 160)}"
            )
            for line in _safe_list(thread.get("recent_lines"))[-2:]:
                line = _safe_dict(line)
                lines.append(
                    f"  {_safe_str(line.get('speaker_name') or line.get('speaker_id'))}: {_compact_prompt_text(line.get('text'), 160)}"
                )
        conversation_threads_block = "\n".join(lines)
    else:
        conversation_threads_block = "none"

    recent_authoritative_facts = _recent_authoritative_facts(narration_context)
    recent_facts_block = "\n".join(f"- {fact}" for fact in recent_authoritative_facts[:3]) or "- none"
    combat_facts_block = _build_combat_facts_block(narration_context)
    current_turn_prompt_contract = build_runtime_current_turn_prompt_contract(
        scene=scene,
        narration_context=narration_context,
    )
    current_turn_visible_response = _current_turn_semantic_visible_response(narration_context)
    compact_turn = _safe_dict(current_turn_prompt_contract.get("turn_contract"))
    compact_interpreted = _safe_dict(compact_turn.get("interpreted_action"))
    visible_npc = _safe_dict(current_turn_visible_response.get("npc"))
    relevant_memory_context = build_relevant_memory_context_from_runtime(
        runtime_state,
        player_input=narration_context.get("player_input")
        or narration_context.get("player_action")
        or current_turn_prompt_contract.get("player_action"),
        actor_ids=[
            compact_interpreted.get("target_id"),
            visible_npc.get("speaker"),
        ],
        location_id=grounded.get("location_id") or scene.get("location_id"),
    )
    npc_response_architecture = build_runtime_npc_response_architecture(
        narration_context=narration_context,
        current_turn_prompt_contract=current_turn_prompt_contract,
    )
    relevant_memory_block = build_relevant_memory_prompt_block(relevant_memory_context)
    runtime_guardrails_block = build_runtime_presentation_guardrails_block(narration_context)
    npc_behavior_context = _safe_dict(
        narration_context.get("npc_behavior_context")
        or _safe_dict(narration_context.get("turn_contract")).get("npc_behavior_context")
    )
    npc_state_summary = {
        "mood": npc_behavior_context.get("mood"),
        "relationship": npc_behavior_context.get("relationship_to_player"),
        "trust": npc_behavior_context.get("trust"),
        "fear": npc_behavior_context.get("fear"),
        "recent_memories": _safe_list(npc_behavior_context.get("recent_memories"))[:4],
    }
    safe_context_block = _compact_prompt_json(safe_context, 1400)
    turn_contract_block = _compact_prompt_json(_safe_dict(narration_context.get("turn_contract")), 5200)
    current_turn_contract_block = _compact_prompt_json(current_turn_prompt_contract, 3600)
    npc_response_architecture_block = _compact_prompt_json(npc_response_architecture, 3200)
    current_turn_visible_response_block = _compact_prompt_json(current_turn_visible_response or {"present": False}, 1200)
    npc_state_summary_block = _compact_prompt_json(npc_state_summary, 1200)
    npc_behavior_context_block = _compact_prompt_json(npc_behavior_context, 1800)

    grounding_settings = normalize_grounding_settings(
        _safe_dict(_safe_dict(narration_context.get("runtime_settings")).get("grounding"))
        or _safe_dict(_safe_dict(narration_context.get("settings")).get("grounding"))
    )
    use_safe_fallback_candidate = bool(
        grounding_settings.get("llm_safe_fallback_candidate", True)
    )

    if use_safe_fallback_candidate:
        schema = """
Use exactly this object shape:
{
    "format_version": "rpg_narration_candidates_v1",
    "primary": {
        "format_version": "rpg_narration_v2",
        "narration": "<descriptive scene narration grounded in turn_contract>",
        "action": "<short, in-world description of what happened; consequence only, no meta language>",
        "npc": {
            "speaker": "<target NPC name if an allowed/present NPC reacts, otherwise empty string>",
            "line": "<natural in-character dialogue, or empty string only if no NPC reaction is needed>"
        },
        "reward": null,
        "followup_hooks": []
    },
    "safe_fallback": {
        "format_version": "rpg_narration_v2",
        "narration": "<safe conservative narration that refuses or defers unsupported claims>",
        "action": "<safe consequence only; no state changes unless explicitly in turn_contract>",
        "npc": {
            "speaker": "<same allowed speaker as primary when possible>",
            "line": "<safe in-character fallback line; no rewards, no combat, no travel, no quest completion, no hidden facts>"
        },
        "reward": null,
        "followup_hooks": []
    }
}
"""
    else:
        schema = """
Use exactly this object shape:
{
    "format_version": "rpg_narration_v2",
    "narration": "<descriptive scene narration grounded in turn_contract>",
    "action": "<short, in-world description of what happened; consequence only, no meta language>",
    "npc": {
        "speaker": "<target NPC name if an allowed/present NPC reacts, otherwise empty string>",
        "line": "<natural in-character dialogue, or empty string only if no NPC reaction is needed>"
    },
    "reward": null,
    "followup_hooks": []
}
"""

    prompt = f"""You are a deterministic RPG narration engine.

CONTEXT:
{safe_context_block}

Recent authoritative facts:
{recent_facts_block}

Authoritative combat facts:
{combat_facts_block}

Turn contract PRIMARY TRUTH:
{turn_contract_block}

CURRENT_TURN_PROMPT_CONTRACT_JSON:
{current_turn_contract_block}

NPC_RESPONSE_ARCHITECTURE_JSON:
{npc_response_architecture_block}

CURRENT_TURN_SEMANTIC_VISIBLE_RESPONSE_JSON:
{current_turn_visible_response_block}

{runtime_guardrails_block}

NPC STATE SUMMARY (must influence tone and dialogue):
{npc_state_summary_block}

NPC behavior context:
{npc_behavior_context_block}

Ongoing conversation threads:
{conversation_threads_block}

{relevant_memory_block}

YOUR ONLY TASK: Generate narration for a player's action in an RPG.

OUTPUT ONLY VALID JSON.
Do not include markdown fences.
Do not include commentary outside JSON.
{schema}

 IMPORTANT RULES:
 - Output ONLY valid JSON with no extra text
 - NO markdown fences or commentary outside the JSON object
 - NO content about ticks, time, or system messages
 - NO faction goals, loyalty, awareness, or ambient content
TURN CONTRACT RULES:
- turn_contract is the primary truth for this turn.
- CURRENT_TURN_PROMPT_CONTRACT_JSON is the presentation boundary for this exact player action.
- required_focus must be addressed before older context, memories, profile hooks, or recent events.
- NPC_RESPONSE_ARCHITECTURE_JSON may shape speaker, tone, persona, and continuity only.
- resolved_result is legacy compatibility; prefer turn_contract when both are present.
- CURRENT_TURN_SEMANTIC_VISIBLE_RESPONSE_JSON, when present, is current-turn dialogue guidance from the intent/advisory pass. Preserve its speaker, answer intent, and emotional direction unless the authoritative turn_contract forbids NPC dialogue.
- CURRENT_TURN_SEMANTIC_VISIBLE_RESPONSE_JSON outranks conversation_threads recent_lines, older NPC memories, and prior NPC questions. Use those older records only for continuity after answering this current player input.
- Do not copy an older NPC question from conversation_threads when the current player input is answering, correcting, or emotionally disclosing to that question.
- CURRENT_TURN_SEMANTIC_VISIBLE_RESPONSE_JSON is not permission to invent rewards, combat, travel, purchases, inventory changes, or quest progress.
- Relevant Memory is continuity context only. It may shape tone, recall, and wording after the current turn is satisfied.
- Relevant Memory never authorizes new rewards, combat, travel, purchases, inventory changes, quest progress, secret disclosure, or relationship changes.
- Private Relevant Memory may shape NPC tone only; do not reveal private memory directly unless current runtime state or turn_contract exposes it.
- You MUST base the narration primarily on turn_contract.narration_brief.
- You MUST reflect turn_contract.state_delta when it exists.
- You MUST NOT invent state changes outside turn_contract.state_delta, resolved_result, or combat facts.
- HIGH-RISK CLAIM RULE:
    You MUST NOT mention rewards, currency, items, XP, inventory, combat, injury, blood, death, location travel, quest completion, objective completion, secret facts, or NPC knowledge unless they are explicitly present in turn_contract, state_delta, resolved_result, or combat facts.
- If the player makes an unsupported claim such as "you owe me gold", the primary and safe_fallback must refuse or defer the claim unless the turn contract explicitly authorizes payment.
- The safe_fallback must be conservative and natural. It must never include rewards, combat, injury, blood, travel, quest completion, or hidden facts.
- The safe_fallback should sound in-character, but it must be safe over dramatic.
- You may freely add sensory detail, body language, pacing, and natural dialogue as presentation only.
- NEVER copy or restate narration_brief directly. Convert it into in-world description.
- NEVER refer to "the player" in narration. Always describe actions in-world (e.g., "You step forward..." or omit subject).
- NEVER output internal IDs like npc:0, npc_bran, player, target_id, action_type, state_delta, narration_brief, or turn_contract.
- The final prose must sound like an RPG narrator, not a debug summary.
- If your output resembles an instruction, rewrite it into a natural in-world description.
- If narration sounds like a system description, rewrite it before finalizing.
- Never output generic filler like "Action: You act."

NPC REACTION RULES:
- If turn_contract.interpreted_action.target_id exists, that NPC MUST visibly react.
- If npc_behavior_context.required_reaction is true, include either:
  1. physical/body-language reaction, or
  2. direct dialogue, preferably both.
- NPC dialogue must match npc_behavior_context.reaction_tone.
- hostile/angry NPCs should not respond as friendly.
- wary NPCs should remain cautious even after an apology.
- recent_memories MUST influence tone and dialogue.
- If a memory includes violence or betrayal, NPC should reference or emotionally reflect it.
- If the player recently harmed an NPC, that NPC should remember it and respond accordingly.
- NPC dialogue should sound natural, not like a summary of emotions.
- Avoid phrases like "I am wary" or "I feel cautious".
- Express emotion through tone, word choice, and implication.
- Any combat description MUST match the authoritative combat facts block
- Do NOT invent hits, misses, damage, knockdowns, or combatants
- The reward field MUST stay empty unless the authoritative context explicitly shows XP, item, or level gain
- Do NOT invent gold, reputation, items, guards, factions, or bystanders not present in the scene/context
- NPC speaker MUST be one present actor or the explicit target NPC from context
- Keep continuity with the recent authoritative facts block below
- Do NOT change previously established prices, speakers, outcomes, or conflict state unless the current resolved result changed them
- Do not end the response with an ellipsis
- Finish with complete sentences
- Do not leave dialogue, action, or scene description trailing mid-thought

Conversation thread rules:
- If conversation_threads are provided, treat them as ongoing local dialogue context.
- Do not restart the same NPC line from scratch.
- Continue from recent_lines when the player's input references an ongoing exchange.
- NPCs may answer, pivot, interrupt, or defer, but must not invent rewards, inventory, combat results, locations, or new NPCs.
- If a thread has world_signals, phrase them as rumors, tension, suspicions, or social shifts only.
- Do not resolve or mutate authoritative state unless action_result already says it happened.

Relevant NPC memories from deterministic simulation:
{_format_recalled_service_memories_for_prompt(narration_context)}

Relevant general NPC memories:
{_format_recalled_npc_memories_for_prompt(narration_context)}

Deterministic NPC-to-NPC conversation beat:
{_format_conversation_beat_for_prompt(narration_context)}

Memory rules:
- NPCs may reference prior interactions only if they appear in Relevant NPC memories or Relevant general NPC memories.
- Do not invent prior purchases, debts, failed purchases, promises, favors, or relationships.
- If Relevant NPC memories is None, do not say "again", "last time", "remember", or imply a previous encounter.
- If a deterministic NPC-to-NPC conversation beat is provided, use only that speaker and line for the NPC dialogue. Do not invent additional conversation consequences.

SCENE:
Title: {title}
Location: {location}
Tone: {tone}
Tension: {tension}
Summary: {summary}
Actors present:
{actor_list}
Stakes: {stakes}
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

    Handles both:
    - JSON format: {"format_version": "...", "narration": "...", "action": "...", ...}
    - Text format: NARRATOR: ...\nACTION: ...\nNPC: ...
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

    # Try JSON format first
    if text.startswith("{"):
        try:
            import json
            parsed_json = json.loads(text)
            if isinstance(parsed_json, dict):
                # Map JSON fields to result fields
                result["narrator"] = _safe_str(parsed_json.get("narration")).strip()
                result["action"] = _safe_str(parsed_json.get("action")).strip()

                npc = parsed_json.get("npc")
                if isinstance(npc, dict):
                    result["npc"] = {
                        "speaker_id": _safe_str(npc.get("speaker")).strip().replace(" ", "_").lower(),
                        "name": _safe_str(npc.get("speaker")).strip(),
                        "text": _bound_text(npc.get("line"), 180),
                        "emotion": "",
                        "portrait": "",
                    }

                result["reward"] = ""

                logger.debug("[RPG PARSE] Parsed JSON format: narrator=%r, action=%r, npc_text=%r",
                             result["narrator"][:50], result["action"][:50], result["npc"]["text"][:50])
                return result
        except Exception:
            logger.debug("[RPG PARSE] JSON parsing failed, falling back to text parsing")

    import re

    # Look for patterns anywhere in the text
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

    blob = (narrator + "\n" + action + "\n" + npc_text).strip()
    if not blob:
        is_valid = False
    elif len(blob) <= 10:
        is_valid = False
    elif blob.startswith("{") or '"format_version"' in blob or '"narration"' in blob:
        # Do not treat leaked JSON / partial JSON as valid rendered prose.
        is_valid = False
    else:
        is_valid = True

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

__all__ = [name for name in globals() if not name.startswith("__")]
