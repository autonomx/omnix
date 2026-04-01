"""Narrative Renderer (Player Experience Layer) — TIER 9: Narrative Intelligence Layer.

This module implements the Narrative Renderer from Tier 9 of the RPG design specification.

Purpose:
    Convert scenes, characters, and memory into LLM prompt-ready narrative.
    Provide rich, contextual narrative that incorporates all narrative layers.

The Problem:
    - Scenes, characters, memory exist in isolation
    - No unified narrative presentation layer
    - LLM prompts lose context from other systems
    - Player experience is fragmented

The Solution:
    NarrativeRenderer combines:
    - Active scenes with stakes and participants
    - Character beliefs and goals
    - Memory summaries for continuity
    - World state context
    
    Into a unified narrative payload ready for LLM generation.

Usage:
    renderer = NarrativeRenderer()
    narrative = renderer.render(
        scenes=active_scenes,
        memory=narrative_memory,
        characters=character_engine.characters,
    )

Architecture:
    Scenes + Characters + Memory + World State → Narrative Context
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .scene_engine import Scene


class NarrativeRenderer:
    """Converts narrative components into LLM-ready context.
    
    The NarrativeRenderer is the final layer of the narrative pipeline.
    It aggregates scenes, character data, memory summaries, and world
    state into a unified narrative context that can be used for
    LLM prompt generation or direct text output.
    
    Integration Points:
        - PlayerLoop.step(): Called at end of step with all components
        - LLM Client: render() output feeds into prompt context
        - Testing: Provides deterministic narrative output for validation
    
    Usage:
        renderer = NarrativeRenderer()
        
        narrative = renderer.render(
            scenes=active_scenes,
            memory=narrative_memory,
            characters=character_engine.characters,
            world_state=world_state,
        )
    """
    
    def __init__(self, template: Optional[str] = None):
        """Initialize the NarrativeRenderer.
        
        Args:
            template: Optional custom template string for formatting.
                      Uses default template if None.
        """
        self.template = template
        self._render_count = 0
    
    def render(
        self,
        scenes: List[Scene],
        memory: Any = None,
        characters: Optional[Dict[str, Any]] = None,
        world_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Render narrative from all narrative components.
        
        Combines scenes, memory, characters, and world state into
        a unified narrative context.
        
        Args:
            scenes: List of Scene objects to include.
            memory: NarrativeMemory or object with summaries/events.
            characters: Dict of character_id → Character data.
            world_state: World state dict for context.
            
        Returns:
            Dict with "scene_text", "memory_summary", "character_updates",
            "full_narrative", and metadata keys.
        """
        self._render_count += 1
        
        # Build scene text
        scene_texts = self._build_scene_text(scenes)
        
        # Build memory summary
        memory_summary = self._build_memory_summary(memory)
        
        # Build character updates
        character_text = self._build_character_text(characters)
        
        # Build world context
        world_context = self._build_world_context(world_state)
        
        # Combine into full narrative
        full_narrative = self._combine_narrative(
            scene_texts, memory_summary, character_text, world_context
        )
        
        return {
            "scene_text": "\n".join(scene_texts) if scene_texts else "No active scenes.",
            "memory_summary": memory_summary,
            "character_updates": character_text,
            "world_context": world_context,
            "full_narrative": full_narrative,
            "scene_count": len(scenes),
            "render_count": self._render_count,
        }
    
    def _build_scene_text(self, scenes: List[Scene]) -> List[str]:
        """Convert scenes to narrative text entries.
        
        Args:
            scenes: Scene objects to convert.
            
        Returns:
            List of scene text strings.
        """
        texts: List[str] = []
        
        for scene in scenes:
            if scene.resolved:
                text = (
                    f"[RESOLVED] Scene: {scene.type} at {scene.location}. "
                    f"Stakes: {scene.stakes}. "
                    f"Resolution: {scene.resolution}"
                )
            else:
                text = (
                    f"[ACTIVE] Scene: {scene.type} at {scene.location}. "
                    f"Participants: {', '.join(scene.participants)}. "
                    f"Stakes: {scene.stakes}. "
                    f"{scene.description}"
                )
            texts.append(text)
        
        return texts
    
    def _build_memory_summary(self, memory: Any = None) -> str:
        """Build narrative memory summary.
        
        Args:
            memory: NarrativeMemory or object with get_context/summaries.
            
        Returns:
            Memory summary string.
        """
        if memory is None:
            return "No memory recorded."
        
        # Try get_context method (NarrativeMemory interface)
        if hasattr(memory, "get_context"):
            try:
                ctx = memory.get_context()
                summaries = ctx.get("summaries", [])
                if summaries:
                    parts = []
                    for s in summaries[-3:]:  # Last 3 summaries
                        parts.append(s.get("text", "Summary"))
                    return " | ".join(parts)
                return "Recent events are fresh in memory."
            except Exception:
                pass
        
        # Try summaries attribute
        if hasattr(memory, "summaries"):
            summaries = getattr(memory, "summaries", [])
            if summaries:
                parts = []
                for s in summaries[-3:]:
                    if isinstance(s, dict):
                        parts.append(s.get("text", "Summary"))
                    else:
                        parts.append(str(s))
                return " | ".join(parts)
            return "Recent events are fresh in memory."
        
        return "Memory status: tracking relevant."
    
    def _build_character_text(self, characters: Optional[Dict[str, Any]] = None) -> str:
        """Build character status text.
        
        Args:
            characters: Dict of char_id → Character or dict.
            
        Returns:
            Character status string.
        """
        if not characters:
            return "No notable characters tracked."
        
        lines: List[str] = []
        count = 0
        
        for char_id, char in characters.items():
            # Handle both Character objects and dicts
            if hasattr(char, "to_dict"):
                char_dict = char.to_dict()
            elif isinstance(char, dict):
                char_dict = char
            else:
                continue
            
            name = char_dict.get("name", char_id)
            goals = char_dict.get("goals", [])
            belief_count = len(char_dict.get("beliefs", {}))
            
            # Only include characters with active goals
            if goals:
                active_goals = goals[:3]  # Top 3 goals only
                goal_str = "; ".join(active_goals)
                lines.append(f"{name}: Goals [{goal_str}]")
                count += 1
                
                if count >= 5:  # Limit to 5 characters
                    lines.append(f"... and {len(characters) - count} others")
                    break
        
        if not lines:
            return "Characters are pursuing personal agendas."
        
        return " | ".join(lines)
    
    def _build_world_context(self, world_state: Optional[Dict[str, Any]] = None) -> str:
        """Build world state context summary.
        
        Args:
            world_state: World state dict.
            
        Returns:
            World context string.
        """
        if world_state is None:
            return "World continues in flux."
        
        parts: List[str] = []
        
        # Check for faction conflicts
        faction_conflicts = world_state.get("faction_conflicts", 0)
        if faction_conflicts:
            parts.append(f"{faction_conflicts} active conflicts")
        
        # Check for crises
        shortages = world_state.get("shortages", {})
        if shortages:
            crisis_locations = list(shortages.keys())[:3]
            parts.append(f"crises in {', '.join(crisis_locations)}")
        
        # Check economy
        economy_state = world_state.get("economy_state", "")
        if economy_state:
            parts.append(f"economy: {economy_state}")
        
        if not parts:
            return "The world stands in uneasy calm."
        
        return "World state: " + "; ".join(parts)
    
    def _combine_narrative(
        self,
        scene_texts: List[str],
        memory_summary: str,
        character_text: str,
        world_context: str,
    ) -> str:
        """Combine all narrative parts into a unified narrative string.
        
        Args:
            scene_texts: List of scene text strings.
            memory_summary: Memory summary string.
            character_text: Character status string.
            world_context: World context string.
            
        Returns:
            Combined narrative string.
        """
        if self.template:
            # Use custom template
            return self.template.format(
                scenes="\n".join(scene_texts) if scene_texts else "No active scenes.",
                memory=memory_summary,
                characters=character_text,
                world=world_context,
            )
        
        # Default format
        parts: List[str] = []
        
        if scene_texts:
            parts.append("--- CURRENT SCENES ---")
            parts.extend(scene_texts)
            parts.append("")
        
        if memory_summary != "No memory recorded.":
            parts.append("--- HISTORY ---")
            parts.append(memory_summary)
            parts.append("")
        
        if character_text != "No notable characters tracked.":
            parts.append("--- CHARACTERS ---")
            parts.append(character_text)
            parts.append("")
        
        parts.append("--- WORLD ---")
        parts.append(world_context)
        
        return "\n".join(parts)
    
    def render_for_prompt(
        self,
        scenes: List[Scene],
        memory: Any = None,
        characters: Optional[Dict[str, Any]] = None,
        world_state: Optional[Dict[str, Any]] = None,
        max_length: int = 2000,
    ) -> str:
        """Render narrative optimized for LLM prompt context.
        
        Truncates output to fit within token limits while preserving
        the most important narrative elements.
        
        Args:
            scenes: Scene objects.
            memory: Memory object.
            characters: Character data.
            world_state: World state.
            max_length: Maximum output length in characters.
            
        Returns:
            Narrative string within length limit.
        """
        result = self.render(scenes, memory, characters, world_state)
        narrative = result["full_narrative"]
        
        # Truncate if needed
        if len(narrative) > max_length:
            narrative = narrative[:max_length - 3] + "..."
        
        return narrative
    
    def reset(self) -> None:
        """Reset renderer state."""
        self._render_count = 0