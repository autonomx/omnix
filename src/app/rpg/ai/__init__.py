# AI module for RPG system - Unified Decision Pipeline

from .behavior_driver import BehaviorContext, BehaviorDriver

# Phase 4.5 exports
from .branch_ai_evaluator import AIBranchEvaluator, BranchEvaluation
from .decision import ActionResolver, DecisionContext, DecisionEngine
from .goal_generator import GoalGenerator
from .goap import GOAPPlanner
from .intent_engine import IntentEngine
from .npc_actor import NPCActor, NPCGoal
from .opposition_engine import OppositionEngine
from .strategy_profiles import (
    STRATEGY_PROFILES,
    get_strategy_bias,
    get_strategy_profile,
    list_strategies,
)

# Phase 5 exports
from .world_scene_narrator import (
    NarrativeResult,
    NPCReaction,
    SceneNarrator,
    # Phase 5.5
    apply_hooks_to_choices,
    build_choice_prompt,
    build_npc_reaction_prompt,
    build_scene_prompt,
    parse_choices,
    parse_npc_reaction,
    parse_scene_response,
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
    # Phase 5.5
    "apply_hooks_to_choices",
]
