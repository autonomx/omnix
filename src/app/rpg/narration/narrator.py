"""Narrator Agent — Converts events into narrative prose.

This module implements the Narrator Agent from the design spec's Multi-Agent Split.
The Narrator is separate from the Director: the Director decides what happens,
the Narrator tells the story of what happened.

Purpose:
    Convert mechanical events into compelling narrative prose.
    
Architecture:
    Events → Narrator → Narrative Text
    
Usage:
    narrator = NarratorAgent(llm)
    narrative = narrator.generate(events)
    
Design Compliance:
    - Narrator does NOT decide — only narrates
    - Narrator does NOT modify world state
    - Narrator consumes events, produces text
    - Supports both LLM and template-based narration
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


class NarratorAgent:
    """Converts events into narrative prose.
    
    The Narrator Agent is a pure function: events in, narrative text out.
    It does not modify world state or make decisions.
    
    Two modes:
    - LLM mode: Uses an LLM to generate rich narrative
    - Template mode: Uses event templates for fast narration
    
    Attributes:
        llm: Optional LLM callable for narrative generation.
        style: Narration style tag ("dramatic", "neutral", "epic").
    """
    
    def __init__(
        self,
        llm: Optional[Callable] = None,
        style: str = "dramatic",
    ):
        """Initialize the NarratorAgent.
        
        Args:
            llm: Optional LLM callable. Signature: llm(prompt: str) -> str.
            style: Narration style ("dramatic", "neutral", "epic", "minimal").
        """
        self.llm = llm
        self.style = style
        
    def generate(self, events: List[Dict[str, Any]]) -> str:
        """Generate narrative text from a list of events.
        
        This is the main entry point. It takes mechanical events
        and produces narrative prose.
        
        Args:
            events: List of event dicts to narrate.
            
        Returns:
            Narrative text string.
        """
        if not events:
            return ""
            
        # Filter to narratable events
        narratable = self._filter_narratable(events)
        if not narratable:
            return ""
            
        if self.llm and self.style != "minimal":
            return self._generate_with_llm(narratable)
        else:
            return self._generate_template(narratable)
        
    def _filter_narratable(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter events to those worth narrating.
        
        Not all events need narration. Internal state updates,
        for example, are not interesting to the player.
        
        Args:
            events: All events to filter.
            
        Returns:
            Filtered list of narratable events.
        """
        narratable_types = {
            "damage", "death", "heal", "speak", "move",
            "betrayal", "alliance_formed", "story_event",
            "critical_hit", "flee", "spawn",
        }
        
        result = []
        for event in events:
            if event.get("type") in narratable_types:
                result.append(event)
                
        return result
    
    def _generate_with_llm(self, events: List[Dict[str, Any]]) -> str:
        """Generate narrative using LLM.
        
        Args:
            events: Narratable events.
            
        Returns:
            LLM-generated narrative text.
        """
        # Build event descriptions
        event_texts = []
        for event in events:
            event_texts.append(self._event_to_text(event))
            
        combined = "\n".join(event_texts)
        
        style_prompt = {
            "dramatic": "Write in a dramatic, immersive style. Make the reader feel the tension.",
            "neutral": "Write in a clear, factual style. Just report what happened.",
            "epic": "Write in an epic, mythic style. Every action has weight and meaning.",
        }
        
        style_instruction = style_prompt.get(self.style, style_prompt["dramatic"])
        
        prompt = f"""Narrate this as a story:

{combined}

{style_instruction}

Rules:
- Do not add events that didn't happen
- Do not contradict the facts
- Keep it concise (under 200 words)
- Use present tense
- Second person if player is involved

Narrative:"""

        try:
            result = self.llm(prompt)
            return result.strip()
        except Exception:
            return self._generate_template(events)
    
    def _generate_template(self, events: List[Dict[str, Any]]) -> str:
        """Generate narrative using event templates.
        
        Args:
            events: Narratable events.
            
        Returns:
            Template-generated narrative text.
        """
        if self.style == "minimal":
            return self._minimal_narrative(events)
            
        sentences = []
        for event in events:
            sentence = self._template_event(event)
            if sentence:
                sentences.append(sentence)
                
        if not sentences:
            return "Nothing of note happens."
            
        # Join with appropriate transitions
        if len(sentences) == 1:
            return sentences[0]
            
        result = sentences[0]
        for sentence in sentences[1:]:
            result += f" {self._transition()}{sentence[0].lower()}{sentence[1:]}"
            
        return result
    
    def _minimal_narrative(self, events: List[Dict[str, Any]]) -> str:
        """Generate minimal factual narration.
        
        Args:
            events: Events to narrate.
            
        Returns:
            Minimal factual text.
        """
        sentences = []
        for event in events:
            sentence = self._simple_event_text(event)
            if sentence:
                sentences.append(sentence)
        return " | ".join(sentences) if sentences else ""
    
    def _event_to_text(self, event: Dict[str, Any]) -> str:
        """Convert an event dict to narrative-friendly text.
        
        Args:
            event: Event dict.
            
        Returns:
            Human-readable event description.
        """
        etype = event.get("type", "event")
        
        if etype == "damage":
            source = event.get("source", "Unknown")
            target = event.get("target", "Unknown")
            amount = event.get("amount", "")
            return f"{source} attacks {target}{' for ' + str(amount) + ' damage' if amount else ''}"
        elif etype == "death":
            source = event.get("source", "Unknown")
            target = event.get("target", "Unknown")
            return f"{target} is killed by {source}"
        elif etype == "critical_hit":
            source = event.get("source", "Unknown")
            target = event.get("target", "Unknown")
            return f"{source} lands a devastating blow on {target}"
        elif etype == "heal":
            source = event.get("source", "Unknown")
            target = event.get("target", "Unknown")
            amount = event.get("amount", "")
            return f"{source} heals {target}{' for ' + str(amount) + ' HP' if amount else ''}"
        elif etype == "speak":
            speaker = event.get("speaker", "Someone")
            target = event.get("target", "")
            message = event.get("message", "")
            to_target = f" to {target}" if target else ""
            return f'{speaker} says{to_target}: "{message}"'
        elif etype == "move":
            entity = event.get("entity", "Someone")
            to_pos = event.get("to", "somewhere")
            return f"{entity} moves to {to_pos}"
        elif etype == "story_event":
            return event.get("summary", "Something happens")
        elif etype == "spawn":
            entity = event.get("entity", event.get("entity_id", "Something"))
            return f"{entity} appears"
        elif etype == "flee":
            entity = event.get("entity", "Someone")
            from_entity = event.get("from", "")
            from_text = f" from {from_entity}" if from_entity else ""
            return f"{entity} flees{from_text}"
        else:
            return event.get("summary", str(event))
    
    def _template_event(self, event: Dict[str, Any]) -> str:
        """Generate a template narration for a single event.
        
        More descriptive than _event_to_text for dramatic style.
        
        Args:
            event: Event dict.
            
        Returns:
            Narrated sentence.
        """
        etype = event.get("type", "event")
        
        if etype == "damage":
            source = event.get("source", "Unknown")
            target = event.get("target", "Unknown")
            amount = event.get("amount", 0)
            if amount > 15:
                return f"{source} strikes {target} with a heavy blow!"
            elif amount > 5:
                return f"{source} strikes {target}."
            else:
                return f"{source} grazes {target}."
        elif etype == "death":
            target = event.get("target", "Unknown")
            return f"{target} has fallen."
        elif etype == "critical_hit":
            source = event.get("source", "Unknown")
            target = event.get("target", "Unknown")
            return f"{source} lands a devastating blow on {target}!"
        elif etype == "heal":
            source = event.get("source", "Unknown")
            target = event.get("target", "Unknown")
            return f"Light envelops {target} as {source} heals their wounds."
        elif etype == "speak":
            speaker = event.get("speaker", "Someone")
            message = event.get("message", "")
            return f'{speaker} speaks: "{message}"'
        elif etype == "move":
            entity = event.get("entity", "Someone")
            return f"{entity} shifts position."
        elif etype == "story_event":
            return event.get("summary", "Something significant happens.")
        elif etype == "flee":
            entity = event.get("entity", "Someone")
            return f"{entity} turns to flee in terror."
        else:
            return ""
    
    def _simple_event_text(self, event: Dict[str, Any]) -> str:
        """Generate simple factual text for a single event.
        
        Args:
            event: Event dict.
            
        Returns:
            Simple factual text.
        """
        etype = event.get("type", "event")
        
        if etype == "damage":
            return f"{event.get('source', '?')} damages {event.get('target', '?')}"
        elif etype == "death":
            return f"{event.get('target', '?')} dies"
        elif etype == "heal":
            return f"{event.get('source', '?')} heals {event.get('target', '?')}"
        elif etype == "speak":
            return f'{event.get("speaker", "?")}: "{event.get("message", "")}"'
        elif etype == "story_event":
            return event.get("summary", "")
        else:
            return str(event)
    
    def _transition(self) -> str:
        """Get a narrative transition word.
        
        Returns:
            Transition string for joining sentences.
        """
        import random
        transitions = ["Then, ", "Meanwhile, ", "Suddenly, ", "Moments later, ", ""]
        return random.choice(transitions)
    
    def narrate_turn(
        self,
        events: List[Dict[str, Any]],
        context: Optional[str] = None,
    ) -> str:
        """Narrate a complete turn with optional scene context.
        
        Convenience method that wraps generate() with context support.
        
        Args:
            events: Events from this turn.
            context: Optional scene context string (location, mood, etc).
            
        Returns:
            Complete narrative text for the turn.
        """
        if not events:
            return context or ""
            
        if context and self.llm:
            # Include context in the narration
            narrative = self.generate(events)
            return f"{context}\n\n{narrative}"
            
        return self.generate(events)
    
    def reset(self) -> None:
        """Reset narrator state."""
        pass  # Stateless, nothing to reset