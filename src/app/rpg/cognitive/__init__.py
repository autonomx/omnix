"""Cognitive Layer — Tier 11: Hybrid Cognitive Simulation.

This package implements Tier 11 of the RPG design specification: a hybrid
cognitive simulation engine that augments the deterministic core with
controlled LLM-assisted cognitive capabilities.

Architecture:
    Layer 1: Intent Enrichment (LLM-assisted, not replaced)
    Layer 2: Memory-Informed Planning
    Layer 3: LLM-Enhanced Dialogue Engine
    Layer 4: Persistent Identity System
    Layer 5: Coalition System
    Layer 6: Learning Feedback System

Design Principles:
    - Deterministic core remains unchanged
    - LLM only injected in 3 constrained layers
    - No LLM planning every tick
    - No LLM mutating world directly
    - Guardrails prevent LLM from breaking game logic

Usage:
    cognitive = CognitiveLayer(llm_client=llm)
    intention = cognitive.enrich_intent(brain.decide(character, world))
    plan = cognitive.memory_informed_plan(intention, character)
    dialogue = cognitive.generate_dialogue(speaker, listener, context)
"""

from __future__ import annotations

from .intent_enrichment import IntentEnrichment
from .identity import IdentitySystem
from .coalition import CoalitionSystem
from .learning import LearningSystem
from .cognitive_layer import CognitiveLayer

__all__ = [
    "IntentEnrichment",
    "IdentitySystem", 
    "CoalitionSystem",
    "LearningSystem",
    "CognitiveLayer",
]
