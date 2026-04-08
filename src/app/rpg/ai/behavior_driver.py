"""Behavior Driver — Inject beliefs and memory into NPC decision layer.

This module implements PATCH 4 from rpg-design.txt:
"Memory Is Not Driving Behavior — Inject beliefs into decision layer"

The Problem: Beliefs and relationships are stored but not used by NPCs
to decide actions. NPCs don't reason from their memories.

The Solution: A BehaviorDriver that retrieves memories and beliefs for
each NPC and injects them into the decision-making prompt, requiring
reasoning based on those beliefs.

Architecture:
    Memory → Belief Extraction → Behavior Prompt → NPC Action with Reasoning

Usage:
    driver = BehaviorDriver(memory_manager, belief_system)
    context = driver.build_decision_context(npc_id, entities=["player"])
    # context = {"beliefs": ..., "relationships": ..., "recent_memories": ...}
    
Design Compliance:
    - Beliefs injected into decision layer
    - NPC reasoning based on memories
    - Context-driven behavior
    - Relationship-aware decisions
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.rpg.memory.belief_system import BeliefSystem
from app.rpg.memory.memory_manager import MemoryManager


class BehaviorContext:
    """Complete behavioral context for an NPC's decision-making.
    
    This bundles everything the NPC needs to make memory-driven,
    belief-aware decisions.
    
    Attributes:
        npc_id: The NPC this context is for.
        beliefs: Active beliefs from BeliefSystem.
        relationships: Relationship values from MemoryManager.
        recent_memories: Recent event memories.
        personality: NPC personality traits (if available).
        emotional_state: NPC's current emotional state.
    """
    
    def __init__(
        self,
        npc_id: str,
        beliefs: Optional[Dict[str, Any]] = None,
        relationships: Optional[Dict[str, float]] = None,
        recent_memories: Optional[List[Dict[str, Any]]] = None,
        personality: Optional[Dict[str, Any]] = None,
        emotional_state: Optional[Dict[str, Any]] = None,
    ):
        """Initialize behavioral context.
        
        Args:
            npc_id: NPC identifier.
            beliefs: Active belief dict.
            relationships: Relationship values dict.
            recent_memories: List of recent memory events.
            personality: Personality trait dict.
            emotional_state: Current emotional state dict.
        """
        self.npc_id = npc_id
        self.beliefs = beliefs or {}
        self.relationships = relationships or {}
        self.recent_memories = recent_memories or []
        self.personality = personality or {}
        self.emotional_state = emotional_state or {}
        
    def to_prompt(self) -> str:
        """Format context as LLM prompt section.
        
        Returns:
            Formatted prompt string.
        """
        lines = [f"### Decision Context for {self.npc_id}"]
        
        # Beliefs section
        if self.beliefs:
            lines.append("\nBELIEFS:")
            for key, value in self.beliefs.items():
                if isinstance(value, dict):
                    reason = value.get("reason", str(value))
                    val = value.get("value", 0)
                    lines.append(f"  - {key}: {reason} (val={val:.2f})")
                else:
                    lines.append(f"  - {key}: {value}")
                    
        # Relationships section
        if self.relationships:
            lines.append("\nRELATIONSHIPS:")
            for entity, value in self.relationships.items():
                sentiment = "friendly" if value > 0.2 else (
                    "hostile" if value < -0.2 else "neutral"
                )
                lines.append(f"  - {entity}: {sentiment} ({value:.2f})")
                
        # Recent memories section
        if self.recent_memories:
            lines.append("\nRECENT MEMORIES:")
            for i, mem in enumerate(self.recent_memories[:5]):
                if isinstance(mem, dict):
                    summary = mem.get("summary", mem.get("type", "event"))
                    lines.append(f"  {i+1}. {summary}")
                else:
                    lines.append(f"  {i+1}. {mem}")
                    
        # Personality section
        if self.personality:
            lines.append("\nPERSONALITY:")
            for trait, value in self.personality.items():
                lines.append(f"  - {trait}: {value}")
                
        # Emotional state section
        if self.emotional_state:
            lines.append("\nEMOTIONAL STATE:")
            emotion = self.emotional_state.get("emotion", "neutral")
            intensity = self.emotional_state.get("intensity", 0.5)
            lines.append(f"  - emotion: {emotion} (intensity={intensity:.2f})")
            
        return "\n".join(lines)
        
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            "npc_id": self.npc_id,
            "beliefs": self.beliefs,
            "relationships": self.relationships,
            "recent_memories": [
                m if isinstance(m, dict) else {"text": str(m)}
                for m in self.recent_memories
            ],
            "personality": self.personality,
            "emotional_state": self.emotional_state,
        }


class BehaviorDriver:
    """Injects beliefs and memory into NPC decision-making.
    
    This is the bridge between the memory system and NPC behavior.
    It retrieves relevant memories, extracts beliefs, and formats
    them into a decision context that NPCs use to reason about
    their actions.
    
    Usage:
        driver = BehaviorDriver(memory_manager, belief_system)
        context = driver.build_decision_context(npc_id, entities)
        reasoning = driver.generate_reasoning(context, proposed_action)
    """
    
    def __init__(
        self,
        memory_manager: Optional[MemoryManager] = None,
        belief_system: Optional[BeliefSystem] = None,
    ):
        """Initialize BehaviorDriver.
        
        Args:
            memory_manager: MemoryManager for memory retrieval.
            belief_system: BeliefSystem for belief management.
        """
        self.memory_manager = memory_manager
        self.belief_system = belief_system or BeliefSystem()
        
    def build_decision_context(
        self,
        npc_id: str,
        entities: Optional[List[str]] = None,
        max_memories: int = 5,
    ) -> BehaviorContext:
        """Build complete decision context for an NPC.
        
        Retrieves beliefs, relationships, and recent memories
        relevant to the NPC.
        
        Args:
            npc_id: The NPC to build context for.
            entities: Related entities to include in context.
            max_memories: Maximum recent memories to retrieve.
            
        Returns:
            BehaviorContext with all relevant information.
        """
        query_entities = [npc_id]
        if entities:
            query_entities.extend(entities)
        query_entities = list(set(query_entities))
        
        # Get beliefs for this NPC
        beliefs = self._get_npc_beliefs(npc_id)
        
        # Get relationships
        relationships = self._get_npc_relationships(npc_id)
        
        # Get recent memories
        recent_memories = self._get_recent_memories(
            npc_id, query_entities, max_memories
        )
        
        return BehaviorContext(
            npc_id=npc_id,
            beliefs=beliefs,
            relationships=relationships,
            recent_memories=recent_memories,
        )
        
    def _get_npc_beliefs(self, npc_id: str) -> Dict[str, Any]:
        """Get active beliefs for an NPC.
        
        Args:
            npc_id: NPC identifier.
            
        Returns:
            Dict of active beliefs.
        """
        if not self.belief_system:
            return {}
            
        beliefs = {}
        
        # Get beliefs from BeliefSystem (hostile_targets, trusted_allies, etc.)
        if self.belief_system.beliefs:
            beliefs["belief_system"] = dict(self.belief_system.beliefs)
            
        # Get beliefs this NPC holds about others
        if hasattr(self.belief_system, 'get_summary'):
            summary = self.belief_system.get_summary()
            if summary:
                beliefs["summary"] = summary
                
        # Get beliefs from MemoryManager if available
        if self.memory_manager and hasattr(self.memory_manager, 'semantic_beliefs'):
            relevant = [
                b for b in self.memory_manager.semantic_beliefs
                if b.get("entity") == npc_id or b.get("target_entity") == npc_id
            ]
            if relevant:
                beliefs["memory_beliefs"] = relevant[:5]
                
        return beliefs
        
    def _get_npc_relationships(self, npc_id: str) -> Dict[str, float]:
        """Get relationship values for an NPC.
        
        Args:
            npc_id: NPC identifier.
            
        Returns:
            Dict mapping entity IDs to relationship values.
        """
        relationships = {}
        
        # From MemoryManager
        if self.memory_manager:
            if hasattr(self.memory_manager, 'belief_system'):
                rels = self.memory_manager.belief_system.get_relationships(npc_id)
                if rels:
                    relationships.update(rels)
                    
            # From semantic beliefs
            if hasattr(self.memory_manager, 'semantic_beliefs'):
                for belief in self.memory_manager.semantic_beliefs:
                    if belief.get("type") == "relationship":
                        entity = belief.get("entity", "")
                        target = belief.get("target_entity", "")
                        value = belief.get("value", 0)
                        
                        if entity == npc_id and target:
                            relationships[target] = value
                        elif target == npc_id and entity:
                            relationships[entity] = value
                            
        return relationships
        
    def _get_recent_memories(
        self,
        npc_id: str,
        entities: List[str],
        max_items: int = 5,
    ) -> List[Dict[str, Any]]:
        """Get recent memories relevant to the NPC.
        
        Uses relevance scoring to select the most important memories.
        
        Args:
            npc_id: NPC identifier.
            entities: Related entities.
            max_items: Maximum memories to return.
            
        Returns:
            List of relevant memory dicts, scored by relevance.
        """
        if not self.memory_manager:
            return []
            
        # Use relevance scoring (PATCH 3)
        return self.select_relevant_memories(npc_id, entities, max_items)
        
    # =========================================================
    # PATCH 3: RELEVANCE SCORING (selective memory retrieval)
    # =========================================================
        
    def select_relevant_memories(
        self,
        npc_id: str,
        query_entities: Any,
        k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Select and rank memories by relevance.
        
        CRITICAL PATCH 3: Without selective memory, too many memories
        pass through, mixing relevant and irrelevant. LLM decisions
        degrade over time with noise accumulation.
        
        Scoring heuristic:
            score = recency_weight + importance_weight + 
                    entity_overlap + emotional_intensity
                    
        Args:
            npc_id: NPC identifier for context.
            query_entities: Entities to score relevance against.
                Can be a string, list, or dict with 'text' key.
            k: Number of top memories to return.
            
        Returns:
            Top-k memories sorted by relevance (descending).
        """
        # Get candidate memories
        if isinstance(query_entities, str):
            entities = [query_entities, npc_id]
        elif isinstance(query_entities, list):
            entities = list(query_entities)
            if npc_id not in entities:
                entities.append(npc_id)
        else:
            entities = [npc_id]
            
        # Retrieve all candidate memories
        memories = self.memory_manager.retrieve(
            query_entities=entities,
            limit=50,  # Larger pool for scoring
            mode="general",
        )
        
        if not memories:
            return []
            
        # Score and rank each memory
        scored = []
        for score, memory in memories:
            relevance = self._score_relevance(memory, entities)
            scored.append((relevance, memory))
            
        # Sort descending by relevance, take top-k
        scored.sort(key=lambda x: -x[0])
        return [m for _, m in scored[:k]]
        
    def _score_relevance(
        self,
        memory: Any,
        entities: List[str],
    ) -> float:
        """Score how relevant a memory is to the current context.
        
        Scoring components:
        1. Recency: Newer memories score higher (0-0.3)
        2. Importance: Marked important memories score higher (0-0.3)
        3. Entity overlap: Memories involving key entities score higher (0-0.25)
        4. Emotional intensity: Strong emotion memories score higher (0-0.15)
        
        Args:
            memory: Memory tuple item (score, memory_obj) or memory dict.
            entities: Current context entities.
            
        Returns:
            Relevance score (0.0-1.0).
        """
        # Extract memory data
        if isinstance(memory, tuple):
            mem_data = memory[1] if len(memory) > 1 else memory[0]
        else:
            mem_data = memory
            
        if isinstance(mem_data, dict):
            score = 0.0
            
            # 1. Recency scoring (0-0.3)
            tick = mem_data.get("created_tick", mem_data.get("tick", 0))
            if tick > 0:
                # Assume current tick ~100 for normalization
                recency = max(0, 1 - tick / 100)
                score += recency * 0.3
                
            # 2. Importance scoring (0-0.3)
            importance = mem_data.get("importance", 0.5)
            score += importance * 0.3
            
            # 3. Entity overlap scoring (0-0.25)
            mem_entities = set()
            for field in ["source", "target", "entity", "actor"]:
                val = mem_data.get(field, "")
                if val:
                    mem_entities.add(str(val))
            entity_overlap = len(mem_entities & set(entities))
            score += min(0.25, entity_overlap * 0.15)
            
            # 4. Emotional intensity scoring (0-0.15)
            emotion = mem_data.get("emotion", mem_data.get("intensity", 0))
            if isinstance(emotion, dict):
                emotion = max(emotion.values()) if emotion else 0
            score += min(0.15, abs(emotion) * 0.15)
            
            return score
            
        # Fallback for non-dict memory types
        return 0.3  # Neutral score for unknown types
        
    def generate_reasoning(
        self,
        context: BehaviorContext,
        proposed_action: str,
    ) -> Dict[str, str]:
        """Generate reasoning for a proposed action based on context.
        
        This creates the "reasoning" field required by the design spec.
        
        Args:
            context: Behavioral context.
            proposed_action: The action being considered.
            
        Returns:
            Dict with "reasoning" and "motivation" strings.
        """
        reasoning_parts = []
        
        # Reason from beliefs
        if context.beliefs:
            for key, value in context.beliefs.items():
                if isinstance(value, dict):
                    reason = value.get("reason", "")
                    if reason:
                        reasoning_parts.append(f"Based on {reason}...")
                elif isinstance(value, str):
                    reasoning_parts.append(f"Believes: {value}")
                    
        # Reason from relationships
        if context.relationships:
            for entity, val in context.relationships.items():
                if val < -0.3:
                    reasoning_parts.append(
                        f"Hostility toward {entity} motivates aggressive response"
                    )
                elif val > 0.3:
                    reasoning_parts.append(
                        f"Trust in {entity} motivates cooperative response"
                    )
                    
        # Reason from recent memories
        if context.recent_memories:
            latest = context.recent_memories[0]
            if isinstance(latest, dict):
                mem_type = latest.get("type", "event")
                reasoning_parts.append(
                    f"Recent {mem_type} event influences current decision"
                )
                
        reasoning = " | ".join(reasoning_parts) if reasoning_parts else (
            f"Based on general assessment of the situation"
        )
        
        return {
            "reasoning": reasoning,
            "motivation": f"NPC {context.npc_id} considers: {proposed_action}",
            "action": proposed_action,
        }
        
    def build_decision_prompt(
        self,
        context: BehaviorContext,
        available_actions: str = "",
        player_input: str = "",
        world_state: str = "",
    ) -> str:
        """Build complete LLM prompt for NPC decision-making.
        
        Args:
            context: Behavioral context.
            available_actions: Action descriptions.
            player_input: Current player input.
            world_state: World state summary.
            
        Returns:
            Complete prompt string.
        """
        return f"""
You are an NPC in an RPG world. Make a decision based on your memories and beliefs.

{context.to_prompt()}

WORLD STATE:
{world_state if world_state else "(Unknown)"}

PLAYER INPUT:
{player_input if player_input else "(No current input)"}

AVAILABLE ACTIONS:
{available_actions if available_actions else "(Use your judgment)"}

Return JSON:
{{
  "action": "action_name",
  "parameters": {{}},
  "reasoning": "Based on my beliefs and memories, I decide to... because..."
}}

Rules:
- Your MUST reference your beliefs in reasoning
- Your action should be consistent with your relationships
- Consider recent memories when deciding
"""
        
    def update_beliefs_from_action(
        self,
        npc_id: str,
        action_result: Dict[str, Any],
    ) -> None:
        """Update beliefs based on action outcomes.
        
        After an NPC acts, their beliefs may change based on
        the result.
        
        Args:
            npc_id: NPC identifier.
            action_result: Result dict from action execution.
        """
        if not self.memory_manager:
            return
            
        events = action_result.get("events", [])
        current_tick = action_result.get("tick", 0)
        
        for event in events:
            # Check if event involves this NPC
            source = event.get("source", event.get("actor", ""))
            target = event.get("target", "")
            
            if source == npc_id or target == npc_id:
                self.memory_manager.add_event(event, current_tick=current_tick)