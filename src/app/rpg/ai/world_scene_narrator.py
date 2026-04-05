"""Phase 5 — LLM Scene Engine + NPC Behavior

Turns structured scenes into narrative experiences:
    Scene → Narrative → NPC reactions → Dialogue → Player response

Provides prompt building, narrative generation, and response parsing
for the scene narration pipeline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


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
        npc: NPC dict with name, personality, goals, etc.
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

    personality_info = f"Personality: {npc_personality}" if npc_personality else ""
    goals_info = f"Goals: {npc_goals}" if npc_goals else ""
    relation_info = f"Relation to player: {npc_relation}" if npc_relation else ""

    prompt = f"""You are generating NPC reactions for an RPG.

Character: {npc_name}
{personality_info}
{goals_info}
{relation_info}

Scene: {scene_title}

Narrative:
{narrative[:1000]}

=== INSTRUCTIONS ===
Describe {npc_name}'s internal reaction to what just happened.
Then provide a short line of dialogue they might say.
Specify their emotional state (one of: calm, tense, angry, fearful, curious, excited, neutral).
Specify their immediate intent (one of: observe, act, confront, flee, negotiate, wait).

Format your response as:
REACTION: [description]
DIALOGUE: "[line]"
EMOTION: [emotion]
INTENT: [intent]
"""
    return prompt


def build_choice_prompt(
    scene: Dict[str, Any],
    narrative: str,
    *,
    num_choices: int = 3,
) -> str:
    """Build a prompt to generate player choices.

    Args:
        scene: Current scene dict.
        narrative: The narrative text.
        num_choices: Number of choices to generate.

    Returns:
        Prompt string for the LLM.
    """
    title = scene.get("title", "Scene")
    stakes = scene.get("stakes", "")

    prompt = f"""You are generating player choices for an RPG scene.

Scene: {title}
Stakes: {stakes}

Narrative situation:
{narrative[-500:]}

=== INSTRUCTIONS ===
Generate exactly {num_choices} meaningful choices for the player.
Each choice should have:
  - A short, action-oriented description (5-10 words)
  - An implied risk or consequence
  - A distinct approach (combat, stealth, diplomacy, observation, etc.)

Format your response as:
1. [choice description]
2. [choice description]
3. [choice description]
"""
    return prompt


# ---------------------------------------------------------------------------
# Response parsers
# ---------------------------------------------------------------------------

def parse_scene_response(text: str) -> Dict[str, Any]:
    """Parse a raw LLM narrative response.

    Args:
        text: Raw LLM response text.

    Returns:
        Dict with 'narrative' and default 'choices'.
    """
    narrative = text.strip() if text else "The scene unfolds before you..."

    return {
        "narrative": narrative,
        "choices": [
            {"id": "choice_1", "text": "Take decisive action", "type": "action"},
            {"id": "choice_2", "text": "Observe carefully", "type": "observe"},
            {"id": "choice_3", "text": "Speak to those present", "type": "dialogue"},
        ],
    }


def parse_npc_reaction(text: str, npc_id: str = "", npc_name: str = "") -> NPCReaction:
    """Parse an NPC reaction response.

    Args:
        text: Raw LLM response for NPC reaction.
        npc_id: NPC identifier.
        npc_name: Fallback NPC name.

    Returns:
        NPCReaction dataclass instance.
    """
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


def parse_choices(text: str) -> List[Dict[str, Any]]:
    """Parse LLM-generated player choices.

    Args:
        text: Raw LLM response with numbered choices.

    Returns:
        List of choice dicts with 'id', 'text', and 'type' keys.
    """
    choices = []
    choice_types = ["action", "observe", "dialogue", "stealth", "combat", "diplomacy"]

    for line in text.split("\n"):
        line = line.strip()
        if line and (line[0].isdigit() and line[1] in (".", ")")):
            choice_text = line[2:].strip()
            idx = len(choices) + 1
            choice_type = choice_types[idx % len(choice_types)]
            choices.append({
                "id": f"choice_{idx}",
                "text": choice_text,
                "type": choice_type,
            })

    return choices if choices else [
        {"id": "choice_1", "text": "Take action", "type": "action"},
        {"id": "choice_2", "text": "Wait and observe", "type": "observe"},
    ]


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
            },
        )

    def _generate_narrative(
        self,
        scene: Dict[str, Any],
        state: Dict[str, Any],
        tone: str,
    ) -> str:
        """Generate narrative text for a scene."""
        if self.simulate_mode or self.llm_gateway is None:
            return self._simulate_narrative(scene, tone)

        try:
            prompt = build_scene_prompt(scene, state, tone=tone)
            response = self.llm_gateway.call("generate", prompt, context={"scene": scene})
            parsed = parse_scene_response(response if isinstance(response, str) else str(response))
            return parsed["narrative"]
        except Exception:
            logger.exception("Failed to generate narrative, falling back to simulation")
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

            if self.simulate_mode or self.llm_gateway is None:
                reaction = self._simulate_npc_reaction(npc_name)
            else:
                try:
                    prompt = build_npc_reaction_prompt(actor, scene, narrative, state=state)
                    response = self.llm_gateway.call("generate", prompt, context={"npc": npc_id})
                    reaction = parse_npc_reaction(response if isinstance(response, str) else str(response),
                                                  npc_id=npc_id, npc_name=npc_name)
                except Exception:
                    logger.exception("Failed to generate NPC reaction for %s", npc_name)
                    reaction = self._simulate_npc_reaction(npc_name)

            reactions.append(reaction)

        return reactions

    def _generate_choices(
        self,
        scene: Dict[str, Any],
        narrative: str,
    ) -> List[Dict[str, Any]]:
        """Generate player choices."""
        if self.simulate_mode or self.llm_gateway is None:
            return self._simulate_choices(scene)

        try:
            prompt = build_choice_prompt(scene, narrative)
            response = self.llm_gateway.call("generate", prompt, context={"scene": scene.get("id")})
            parsed = parse_choices(response if isinstance(response, str) else str(response))
            return parsed
        except Exception:
            logger.exception("Failed to generate choices, falling back to defaults")
            return self._simulate_choices(scene)

    # ------------------------------------------------------------------
    # Simulation fallbacks (no LLM required)
    # ------------------------------------------------------------------

    @staticmethod
    def _simulate_narrative(scene: Dict[str, Any], tone: str) -> str:
        """Generate simulated narrative text without LLM."""
        title = scene.get("title", "The Scene")
        summary = scene.get("summary", "Events unfold around you.")
        stakes = scene.get("stakes", "much is at stake")
        actors = scene.get("actors", [])
        actor_names = []
        if isinstance(actors, list):
            actor_names = [str(a) for a in actors[:3]]
        elif isinstance(actors, dict):
            actor_names = list(actors.keys())[:3]

        actor_text = f"{' and '.join(actor_names)} stand before you" if actor_names else "You stand alone"
        return (
            f"{title}\n\n"
            f"{summary}\n\n"
            f"{actor_text}, the weight of the moment pressing down. "
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
    def _simulate_choices(scene: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate simulated choices without LLM."""
        return [
            {"id": "choice_1", "text": "Take decisive action", "type": "action"},
            {"id": "choice_2", "text": "Observe the situation carefully", "type": "observe"},
            {"id": "choice_3", "text": "Speak with those present", "type": "dialogue"},
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
        simulate_mode=(llm_gateway is None),
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