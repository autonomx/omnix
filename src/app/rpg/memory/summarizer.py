"""Memory Summarizer — Token control for memory system.

This module implements the Memory Summarization system from the design spec.
It compresses memory events into compact summaries to keep prompt size
manageable at scale.

Purpose:
    Control token usage — dump too much memory into prompt → break at scale

Architecture:
    Events → Summarizer → Compact Memory → LLM Prompt (bounded tokens)

Usage:
    summarizer = MemorySummarizer(llm)
    summary = summarizer.summarize(episode_list)
    compact = summarizer.compress_memory(manager, max_tokens=500)

Design Compliance:
    - Keeps key facts
    - Preserves relationships
    - Max token budget enforced
    - Supports multi-pass summarization for large memory sets
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


class MemorySummarizer:
    """Compresses memory events into compact summaries.
    
    This class takes a set of memory episodes/events and produces
    a shorter text representation that retains the essential
    narrative content while staying within token budgets.
    
    Two modes of operation:
    - LLM mode: Uses an LLM to generate summaries (requires llm callable)
    - Heuristic mode: Uses rule-based summarization (no LLM needed)
    
    Attributes:
        llm: Optional LLM callable for generating summaries.
        max_summary_tokens: Maximum tokens per summary.
        max_total_tokens: Maximum total tokens for all context.
    """
    
    def __init__(
        self,
        llm: Optional[Callable] = None,
        max_summary_tokens: int = 100,
        max_total_tokens: int = 500,
    ):
        """Initialize the MemorySummarizer.
        
        Args:
            llm: Optional LLM callable. Signature: llm(prompt: str) -> str.
                If not provided, uses heuristic summarization.
            max_summary_tokens: Maximum tokens for a single summary.
            max_total_tokens: Maximum total tokens for full context.
        """
        self.llm = llm
        self.max_summary_tokens = max_summary_tokens
        self.max_total_tokens = max_total_tokens
        
    def summarize(self, episodes: List[Any]) -> str:
        """Summarize a list of episodes into compact memory.
        
        Args:
            episodes: List of Episode objects or event dicts.
            
        Returns:
            Summary string retaining key facts and relationships.
        """
        if not episodes:
            return ""
            
        if len(episodes) == 1:
            return self._summarize_single(episodes[0])
            
        if self.llm:
            return self._summarize_with_llm(episodes)
        else:
            return self._summarize_heuristic(episodes)
        
    def _summarize_single(self, episode: Any) -> str:
        """Summarize a single episode/event.
        
        Args:
            episode: Episode object or event dict.
            
        Returns:
            Summary string.
        """
        if isinstance(episode, dict):
            return self._summarize_event_dict(episode)
        elif hasattr(episode, 'summary'):
            return episode.summary[:300]
        else:
            return str(episode)[:300]
    
    def _summarize_event_dict(self, event: Dict[str, Any]) -> str:
        """Summarize an event dict into compact text.
        
        Args:
            event: Event dict to summarize.
            
        Returns:
            Compact summary string.
        """
        etype = event.get("type", "event")
        source = event.get("source", event.get("actor", ""))
        target = event.get("target", "")
        
        if etype == "damage":
            return f"{source} damaged {target} ({event.get('amount', '?')} dmg)"
        elif etype == "death":
            return f"{target} was killed by {source}"
        elif etype == "heal":
            return f"{source} healed {target} ({event.get('amount', '?')} hp)"
        elif etype == "speak":
            msg = event.get("message", "")[:100]
            return f"{source} → {target}: \"{msg}\""
        elif etype == "move":
            return f"{event.get('entity', '?')} moved to {event.get('to', '?')}"
        elif etype == "story_event":
            return event.get("summary", str(event))
        else:
            summary = event.get("summary", str(event))
            return summary[:200]
    
    def _summarize_with_llm(self, episodes: List[Any]) -> str:
        """Summarize episodes using LLM.
        
        Args:
            episodes: List of Episode objects or event dicts.
            
        Returns:
            LLM-generated summary.
        """
        # Build text representation of episodes
        texts = []
        for ep in episodes[:50]:  # Cap to avoid huge prompts
            texts.append(self._summarize_single(ep))
            
        combined = "\n".join(texts)
        
        prompt = f"""Summarize the following events into compact memory:

{combined}

Rules:
- Keep key facts
- Preserve relationships
- Max {self.max_summary_tokens} tokens
- Focus on who did what to whom
- Note any major outcomes (deaths, alliances, betrayals)

Summary:"""

        try:
            result = self.llm(prompt)
            return result[:self.max_summary_tokens * 4]  # Rough char limit
        except Exception:
            # Fall back to heuristic on LLM failure
            return self._summarize_heuristic(episodes)
    
    def _summarize_heuristic(self, episodes: List[Any]) -> str:
        """Summarize episodes using rule-based heuristic.
        
        Groups events by type and entity, then produces compact output.
        
        Args:
            episodes: List of Episode objects or event dicts.
            
        Returns:
            Heuristic summary string.
        """
        # Collect events
        events = []
        for ep in episodes:
            if isinstance(ep, dict):
                events.append(ep)
            elif hasattr(ep, 'summary'):
                events.append({"summary": ep.summary, "tags": getattr(ep, 'tags', []),
                              "entities": getattr(ep, 'entities', set())})
            else:
                events.append({"summary": str(ep)})
        
        # Group by entity
        entity_events: Dict[str, List[str]] = {}
        for event in events:
            summary = event.get("summary", str(event))
            entities = event.get("entities", set())
            for key in ("source", "target", "actor", "speaker"):
                val = event.get(key, "")
                if val:
                    entities.add(val)
            
            for entity in entities:
                if entity not in entity_events:
                    entity_events[entity] = []
                entity_events[entity].append(summary)
        
        # Build summary
        lines = []
        for entity, events_list in sorted(entity_events.items()):
            if len(events_list) <= 3:
                for e in events_list:
                    lines.append(f"{entity}: {e[:150]}")
            else:
                # Condense many events
                unique = list(dict.fromkeys(events_list))[:5]
                lines.append(f"{entity}: {len(events_list)} events — " +
                           " | ".join(e[:80] for e in unique[:3]))
        
        # Relationship summary
        relationships = []
        for event in events:
            source = event.get("source", event.get("actor", ""))
            target = event.get("target", "")
            etype = event.get("type", event.get("original_type", ""))
            if source and target and etype in ("damage", "death", "heal", "betrayal"):
                relationships.append(f"{source}→{target}:{etype}")
        
        if relationships:
            unique_rels = list(dict.fromkeys(relationships))[:10]
            lines.append(f"Relationships: {' | '.join(unique_rels)}")
        
        return " | ".join(lines[:20])
    
    def compress_memory(
        self,
        memory_manager,
        max_tokens: Optional[int] = None,
        mode: str = "general",
    ) -> str:
        """Get compressed memory context from a MemoryManager.
        
        This is the main integration point. It retrieves memories
        from the manager and ensures they fit within the token budget.
        
        Args:
            memory_manager: The MemoryManager instance to query.
            max_tokens: Override max total tokens (default: self.max_total_tokens).
            mode: Retrieval mode for the memory manager.
            
        Returns:
            Compressed memory context string within token budget.
        """
        max_t = max_tokens or self.max_total_tokens
        
        # Retrieve memories with generous limit
        memories = memory_manager.retrieve(limit=50, mode=mode)
        
        if not memories:
            return "(No relevant memories)"
        
        # Select memories that fit within token budget
        selected = []
        total_tokens = 0
        
        for score, item in memories:
            text = self._summarize_item(item)
            token_count = len(text.split())
            
            if total_tokens + token_count > max_t:
                break
                
            selected.append((score, text))
            total_tokens += token_count
        
        if not selected:
            # At least include the top memory
            score, item = memories[0]
            text = self._summarize_item(item)
            selected.append((score, text[:max_t // 2]))
        
        # Format output
        return " | ".join(text for _, text in selected)
    
    def _summarize_item(self, item: Any) -> str:
        """Summarize a single memory item.
        
        Args:
            item: Episode, belief dict, or event dict.
            
        Returns:
            Summary string.
        """
        if hasattr(item, 'summary'):
            # Episode
            tags = ""
            if hasattr(item, 'tags') and item.tags:
                tags = f" [{', '.join(item.tags[:3])}]"
            return f"{item.summary}{tags}"
        elif isinstance(item, dict):
            if item.get("type") == "relationship":
                entity = item.get("entity", "?")
                target = item.get("target_entity", "?")
                value = item.get("value", 0)
                reason = item.get("reason", "")
                sentiment = "positive" if value > 0 else "negative"
                return f"{entity} has {sentiment} feelings toward {target}: {reason}"
            elif item.get("type") == "fact":
                return item.get("fact", str(item))
            elif item.get("type") == "narrative_event":
                return item.get("summary", str(item))
            else:
                return str(item)
        else:
            return str(item)
    
    def summarize_for_llm(
        self,
        memory_manager,
        query_entities: Optional[List[str]] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Get compressed memory context formatted for LLM prompt.
        
        Convenience method that combines retrieval, summarization,
        and token budgeting.
        
        Args:
            memory_manager: The MemoryManager to query.
            query_entities: Entities to focus retrieval on.
            max_tokens: Override max total tokens.
            
        Returns:
            Formatted memory context string.
        """
        kwargs = {}
        if query_entities:
            kwargs["query_entities"] = query_entities
            
        memories = memory_manager.retrieve(limit=30, **kwargs)
        
        if not memories:
            return "(No relevant memories)"
        
        # Summarize in batch if LLM available
        items = [item for _, item in memories]
        
        if self.llm and len(items) >= 5:
            summary = self._summarize_with_llm(items)
            # Enforce token limit
            words = summary.split()
            max_t = max_tokens or self.max_total_tokens
            if len(words) > max_t:
                summary = " ".join(words[:max_t]) + "..."
            return summary
        else:
            return self.compress_memory(memory_manager, max_tokens=max_t)
    
    def reset(self) -> None:
        """Reset summarizer state."""
        pass  # Stateless, nothing to reset