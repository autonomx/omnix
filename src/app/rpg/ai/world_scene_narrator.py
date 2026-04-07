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
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Phase 8: player-facing encounter view
from app.rpg.player import build_encounter_view

logger = logging.getLogger(__name__)


def _llm_text(llm_gateway, prompt, *, context=None):
    """Call the LLM gateway and return the response as a clean string."""
    response = llm_gateway.call("generate", prompt, context=context or {})
    if response is None:
        return ""
    if isinstance(response, str):
        return response
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

def build_scene_prompt(
    scene: Dict[str, Any],
    state: Dict[str, Any],
    *,
    tone: str = "dramatic",
    max_paragraphs: int = 3,
) -> str:
    """Build an LLM prompt to narrate a scene.

    Args:
        scene: Scene dict with at least title, summary, actors, stakes.
        state: Current game state dict.
        tone: Narrative tone (dramatic, tense, mysterious, etc.).
        max_paragraphs: Maximum number of paragraphs to generate.

    Returns:
        Prompt string for the LLM.
    """
    title = scene.get("title", "Untitled Scene")
    summary = scene.get("summary", "")
    actors = scene.get("actors", [])
    stakes = scene.get("stakes", "Unknown")
    location = scene.get("location", "an unknown place")
    tension = scene.get("tension", "moderate")

    # Build contextual state summary
    player_name = state.get("player_name", "You")
    genre = state.get("genre", "fantasy")

    actor_list = ""
    if actors:
        if isinstance(actors, list):
            actor_list = "\n".join(f"  - {a}" for a in actors)
        elif isinstance(actors, dict):
            actor_list = "\n".join(f"  - {k}: {v}" for k, v in actors.items())
        else:
            actor_list = str(actors)

    prompt = f"""You are a narrative engine for an RPG set in a {genre} world.

=== SCENE: {title} ===
Location: {location}
Tone: {tone}
Tension: {tension}

Summary:
{summary}

Actors present:
{actor_list}

Stakes:
{stakes}

=== INSTRUCTIONS ===
Describe what happens next in {max_paragraphs} paragraphs.
Include sensory details, character reactions, and building tension.
Write in second person, addressing the player as "{player_name}".
Make the narrative immersive and vivid.
Do NOT include player choices — those will be provided separately.
End with a moment of decision or danger.
"""
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

    Phase 5.1: Attempts JSON parsing first, falls back to text extraction.

    Args:
        text: Raw LLM response text.

    Returns:
        Dict with 'narrative' and default 'choices'.
    """
    # Phase 5.1: Try JSON parsing first
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            narrative = data.get("narrative", "").strip()
            if narrative:
                return {
                    "narrative": narrative,
                    "choices": data.get("choices", []),
                }
    except (json.JSONDecodeError, TypeError):
        pass

    # Fallback: text extraction
    narrative = text.strip() if text else "The scene unfolds before you..."

    return {
        "narrative": narrative,
        "choices": [
            {
                "id": "choice_1",
                "text": "Take decisive action",
                "type": "action",
                "action": {
                    "type": "intervene_thread",
                    "target_id": "auto"
                }
            },
            {
                "id": "choice_2",
                "text": "Observe carefully",
                "type": "observe",
                "action": {
                    "type": "observe_situation",
                    "target_id": "auto"
                }
            },
            {
                "id": "choice_3",
                "text": "Speak to those present",
                "type": "dialogue",
                "action": {
                    "type": "escalate_conflict",
                    "target_id": "auto"
                }
            },
        ],
    }


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


def apply_narration_emphasis(narration_payload: dict) -> dict:
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