# AI module for RPG system - Unified Decision Pipeline

from .behavior_driver import BehaviorDriver, BehaviorContext
from .npc_actor import NPCActor, NPCGoal
from .goal_generator import GoalGenerator
from .strategy_profiles import STRATEGY_PROFILES, get_strategy_profile, get_strategy_bias, list_strategies
from .intent_engine import IntentEngine
from .opposition_engine import OppositionEngine
from .decision import DecisionContext, DecisionEngine, ActionResolver
from .goap import GOAPPlanner

# Phase 4.5 exports
from .branch_ai_evaluator import AIBranchEvaluator, BranchEvaluation

# Phase 5 exports
from .world_scene_narrator import (
    SceneNarrator,
    NPCReaction,
    NarrativeResult,
    build_scene_prompt,
    build_npc_reaction_prompt,
    build_choice_prompt,
    parse_scene_response,
    parse_npc_reaction,
    parse_choices,
    play_scene,
)

__all__ = [
    "BehaviorDriver",
    "BehaviorContext",
    "NPCActor",
    "NPCGoal",
    "GoalGenerator",
    "STRATEGY_PROFILES",
    "get_strategy_profile",
    "get_strategy_bias",
    "list_strategies",
    "IntentEngine",
    "OppositionEngine",
    # Decision pipeline
    "DecisionContext",
    "DecisionEngine",
    "ActionResolver",
    "GOAPPlanner",
    # Phase 4.5
    "AIBranchEvaluator",
    "BranchEvaluation",
    # Phase 5
    "SceneNarrator",
    "NPCReaction",
    "NarrativeResult",
    "build_scene_prompt",
    "build_npc_reaction_prompt",
    "build_choice_prompt",
    "parse_scene_response",
    "parse_npc_reaction",
    "parse_choices",
    "play_scene",
]
