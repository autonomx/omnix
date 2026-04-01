"""Director Agent — LLM-first multi-step planner for story direction.

This module implements PATCH 1 from rpg-design.txt:
"Upgrade Director → LLM-first planner"

The Problem: Director outputs single actions, not multi-step plans.
The Solution: DirectorAgent uses LLM to generate structured multi-step
plans with reasoning, based on world state, memory, and player input.

Architecture:
    Director → LLM Prompt → JSON Plan → Multi-Step Actions
    
Usage:
    agent = DirectorAgent(llm, registry)
    plan = agent.decide(player_input, context, world)
    # plan = {"plan": "...", "actions": [{"action": "attack", ...}, ...]}
    
Design Compliance:
    - Multi-step planning per turn
    - LLM-driven decision making
    - Strategic action selection
    - Memory and world-state aware
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

from rpg.tools.action_registry import ActionRegistry


class DirectorOutput:
    """Structured output from the Director Agent.
    
    Contains the plan explanation and list of actions to execute.
    
    Attributes:
        plan: Human-readable plan explanation.
        actions: List of action dicts to execute.
        reasoning: LLM reasoning for the plan (optional).
    """
    
    def __init__(
        self,
        plan: str = "",
        actions: Optional[List[Dict[str, Any]]] = None,
        reasoning: str = "",
        tension_delta: float = 0.0,
    ):
        self.plan = plan
        self.actions = actions or []
        self.reasoning = reasoning
        self.tension_delta = tension_delta
        
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "plan": self.plan,
            "actions": self.actions,
            "reasoning": self.reasoning,
            "tension_delta": self.tension_delta,
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DirectorOutput':
        """Deserialize from dict."""
        return cls(
            plan=data.get("plan", ""),
            actions=data.get("actions", []),
            reasoning=data.get("reasoning", ""),
            tension_delta=data.get("tension_delta", 0.0),
        )
        
    def is_empty(self) -> bool:
        """Check if output has no actions."""
        return len(self.actions) == 0


class DirectorAgent:
    """LLM-first story director that outputs multi-step plans.
    
    This is the authoritative Director Agent from the design spec.
    It uses an LLM to decide story direction, generating structured
    multi-step plans based on world state, memory context, and
    player input.
    
    Key Differences from StoryDirector:
    - Outputs multiple actions per turn (not single action)
    - LLM-driven (not heuristic-based)
    - Strategic reasoning included in output
    - Uses action registry for available actions
    
    Attributes:
        llm: Callable for LLM inference.
        registry: ActionRegistry with available world actions.
        style: Director style ("dramatic", "balanced", "chaotic").
        max_actions: Maximum actions per turn (prevents runaway plans).
    """
    
    def __init__(
        self,
        llm: Optional[Callable] = None,
        registry: Optional[ActionRegistry] = None,
        style: str = "balanced",
        max_actions: int = 5,
    ):
        """Initialize DirectorAgent.
        
        Args:
            llm: LLM callable. Signature: llm(prompt: str) -> str.
            registry: ActionRegistry with available actions.
            style: Directing style ("dramatic", "balanced", "chaotic").
            max_actions: Maximum actions per plan (default 5).
        """
        self.llm = llm
        self.registry = registry or ActionRegistry()
        self.style = style
        self.max_actions = max_actions
        
    def decide(
        self,
        player_input: str,
        context: str = "",
        world: Any = None,
        memory_context: str = "",
        beliefs: Optional[Dict[str, Any]] = None,
    ) -> DirectorOutput:
        """Decide story direction for this turn.
        
        This is the main entry point. It generates a multi-step plan
        based on all available context.
        
        Args:
            player_input: Player's input text.
            context: Additional narrative context.
            world: WorldState or world-like object.
            memory_context: Memory context string from MemoryManager.
            beliefs: Optional beliefs dict for NPC behavior shaping.
            
        Returns:
            DirectorOutput with plan and actions.
        """
        # Build world summary
        world_summary = ""
        if world:
            if hasattr(world, 'to_short_summary'):
                world_summary = world.to_short_summary()
            elif hasattr(world, 'serialize_for_prompt'):
                world_summary = world.serialize_for_prompt()
            else:
                world_summary = str(world)
                
        # Build available actions text
        available_actions = self.registry.get_prompt_text()
        
        # Build beliefs context
        beliefs_context = ""
        if beliefs:
            belief_lines = []
            for key, value in beliefs.items():
                if isinstance(value, dict):
                    belief_lines.append(f"- {key}: {value.get('reason', str(value))}")
                else:
                    belief_lines.append(f"- {key}: {value}")
            beliefs_context = "\n".join(belief_lines)
            
        # Build the LLM prompt
        prompt = self._build_prompt(
            world_summary=world_summary,
            memory_context=memory_context,
            player_input=player_input,
            available_actions=available_actions,
            beliefs_context=beliefs_context,
            narrative_context=context,
        )
        
        # Get LLM response
        if self.llm:
            try:
                response = self.llm(prompt)
                return self._parse_response(response)
            except Exception:
                pass
                
        # Fallback: return empty plan
        return DirectorOutput(
            plan="No LLM available. Waiting for player direction.",
            actions=[],
            reasoning="Fallback: LLM not configured.",
        )
        
    def _build_prompt(
        self,
        world_summary: str,
        memory_context: str,
        player_input: str,
        available_actions: str,
        beliefs_context: str = "",
        narrative_context: str = "",
    ) -> str:
        """Build the LLM prompt for story direction.
        
        Args:
            world_summary: World state summary.
            memory_context: Memory context from MemoryManager.
            player_input: Player's input.
            available_actions: Available action descriptions.
            beliefs_context: NPC beliefs context.
            narrative_context: Additional narrative context.
            
        Returns:
            Formatted prompt string.
        """
        style_instructions = {
            "dramatic": (
                "You are a DRAMATIC story director. "
                "Create tension, conflict, and emotional stakes. "
                "Every scene should feel important."
            ),
            "balanced": (
                "You are a BALANCED story director. "
                "Mix conflict with moments of calm. "
                "Let the story breathe but keep it engaging."
            ),
            "chaotic": (
                "You are a CHAOTIC story director. "
                "Introduce unexpected twists, betrayals, and surprises. "
                "Keep the player on edge."
            ),
        }
        
        style = style_instructions.get(self.style, style_instructions["balanced"])
        
        beliefs_section = ""
        if beliefs_context:
            beliefs_section = f"""
BELIEFS:
{beliefs_context}

Use these beliefs to inform NPC motivations and reactions.
"""
            
        return f"""
You are a STORY DIRECTOR AI.

GOALS:
- Progress the story
- Maintain coherence
- Introduce conflict
- Use available actions strategically

{style}

WORLD:
{world_summary}

MEMORY:
{memory_context if memory_context else "(No relevant memories)"}

BELIEFS:
{beliefs_context if beliefs_context else "(No active beliefs)"}

NARRATIVE CONTEXT:
{narrative_context if narrative_context else "(No additional context)"}

PLAYER INPUT:
{player_input if player_input else "(No player input this turn)"}

AVAILABLE ACTIONS:
{available_actions}

Return JSON ONLY. Do not include any text outside the JSON.

{{
  "plan": "Brief description of what you're planning to do this turn",
  "reasoning": "Why you're choosing these actions - consider beliefs, memory, and world state",
  "tension_delta": <float, how much to change global tension, -1.0 to +1.0>,
  "actions": [
    {{"action": "action_name", "parameters": {{"param": "value"}}}},
    ...
  ]
}}

Rules:
- Maximum {self.max_actions} actions
- Each action must use one of the available actions listed above
- Include reasoning based on world state and beliefs
- Actions should form a coherent narrative beat
"""
        
    def _parse_response(self, response: str) -> DirectorOutput:
        """Parse LLM response into DirectorOutput.
        
        Handles both pure JSON and fenced code blocks.
        
        Args:
            response: Raw LLM response text.
            
        Returns:
            Parsed DirectorOutput.
        """
        # Try to extract JSON from response
        text = response.strip()
        
        # Handle fenced code blocks
        if "```" in text:
            parts = text.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("{"):
                    text = part
                    break
                    
        # Find JSON object
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            return DirectorOutput(
                plan="Could not parse Director response.",
                actions=[],
                reasoning="Parse error.",
            )
            
        json_str = text[start:end + 1]
        
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return DirectorOutput(
                plan="Invalid JSON from Director.",
                actions=[],
                reasoning="JSON parse error.",
            )
            
        # Validate and extract
        actions = data.get("actions", [])
        
        # Limit actions
        if len(actions) > self.max_actions:
            actions = actions[:self.max_actions]
            
        return DirectorOutput(
            plan=data.get("plan", ""),
            actions=actions,
            reasoning=data.get("reasoning", ""),
            tension_delta=float(data.get("tension_delta", 0.0)),
        )
        
    def quick_decision(
        self,
        player_input: str,
        tension: float,
        active_arcs: Optional[List[str]] = None,
    ) -> DirectorOutput:
        """Make a quick decision without full LLM context.
        
        Useful for fast-paced situations or when LLM is unavailable.
        Falls back to heuristic-based decisions.
        
        Args:
            player_input: Player input text.
            tension: Current tension level (0-10).
            active_arcs: List of active arc type strings.
            
        Returns:
            DirectorOutput with heuristic-based plan.
        """
        actions = []
        plan = "Quick heuristic decision."
        reasoning = "No full context available."
        tension_delta = 0.0
        
        input_lower = player_input.lower()
        
        # Heuristic: player aggression
        if any(w in input_lower for w in ["attack", "kill", "fight", "strike"]):
            actions.append({
                "action": "attack",
                "parameters": {
                    "source": "narrator",
                    "target": "player",
                    "damage": 3,
                }
            })
            tension_delta = 0.3
            plan = "Respond to player aggression."
            reasoning = "Player is being aggressive - escalate tension."
            
        # Heuristic: player diplomacy
        elif any(w in input_lower for w in ["talk", "hello", "peace", "help"]):
            tension_delta = -0.1
            plan = "Acknowledge peaceful approach."
            reasoning = "Player is being diplomatic - reduce tension slightly."
            
        # Heuristic: tension-based escalation
        elif tension > 7.0:
            actions.append({
                "action": "speak",
                "parameters": {
                    "speaker": "narrator",
                    "target": "all",
                    "message": "The tension is unbearable...",
                }
            })
            tension_delta = 0.2
            plan = "Heighten rising tension."
            reasoning = "Tension is very high - escalate toward climax."
            
        return DirectorOutput(
            plan=plan,
            actions=actions,
            reasoning=reasoning,
            tension_delta=tension_delta,
        )
        
    def reset(self) -> None:
        """Reset Director Agent state."""
        pass  # Stateless