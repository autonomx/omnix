"""Where Omnix declares its prompt templates (WP-8.4).

Features declare each model-facing prompt once, as a module-level
``prompt_template(...)`` constant beside the code that sends it (see
``app.prompts.models.prompt_template``). ``PROMPT_MODULES`` lists those
modules; ``load_templates`` imports them and returns the templates by id. The
golden test pins every template's version and text hash, so changing a prompt
is a reviewed diff that also bumps its version.

Nothing imports this module at runtime: it exists for tests and tools.
"""
from __future__ import annotations

import importlib

from .models import PromptTemplate

PROMPT_MODULES: tuple[str, ...] = (
    "app.agent_runtime.coding_quality",
    "app.agent_runtime.pi_runtime",
    "app.agent_runtime.pi_runtime_core",
    "app.agent_runtime.planning_review",
    "app.agent_runtime.review_orchestration_core",
    "app.agent_runtime.semantic_classifier",
    "app.agent_runtime.semantic_task_parser",
    "app.agent_runtime.service",
    "app.agent_runtime.service_core",
    "app.assistant_memory.initiative",
    "app.assistant_memory.paralinguistic_state",
    "app.assistant_memory.structured_provider",
    "app.characters.avatar_generation_service",
    "app.characters.avatar_viseme_generation",
    "app.characters.interaction",
    "app.chat.assist.hermes",
    "app.chat.live_agent_store",
    "app.chat.live_call_greeting",
    "app.chat.live_conversation_proactive",
    "app.chat.session_defaults",
    "app.desktop_companion.commentary",
    "app.desktop_companion.observation",
    "app.providers.chatgpt_codex_provider",
    "app.providers.desktop_vision",
    "app.rpg.ai.action_intelligence",
    "app.rpg.ai.compact_dialogue",
    "app.rpg.ai.conversation_prompt_builder",
    "app.rpg.ai.grounding_soft_audit",
    "app.rpg.ai.llm_mind.npc_prompt_builder",
    "app.rpg.ai.memory_narration_grounding",
    "app.rpg.ai.semantic_action_intelligence",
    "app.rpg.ai.survival_narration_grounding",
    "app.rpg.ai.world_scene_narrator_prompts",
    "app.rpg.api.feature_routes.rpg_world_image_routes",
    "app.rpg.cognitive.intent_enrichment",
    "app.rpg.cognitive.resolution_engine",
    "app.rpg.jobs.turn_executor",
    "app.rpg.narration.combat_prompt",
    "app.rpg.narration.narrator",
    "app.rpg.narration.runtime_narration_legacy",
    "app.rpg.narrative.narrative_generator",
    "app.rpg.narrative_provider",
    "app.rpg.npc_dialogue.intelligence",
    "app.rpg.presentation.current_turn_prompt_contract",
    "app.rpg.presentation.personality",
    "app.rpg.profiles.llm_profile_drafter",
    "app.rpg.profiles.profile_portraits",
    "app.rpg.session.ability_detail",
    "app.rpg.session.environment_narration",
    "app.rpg.session.genesis.campaign_lore_store",
    "app.rpg.session.genesis.runtime_lore_materialization",
    "app.rpg.session.genesis.runtime_materialization",
    "app.rpg.session.genesis.world_forge_dossiers",
    "app.rpg.session.item_detail",
    "app.rpg.session.memory_prompt",
    "app.rpg.session.player_agency_contract",
    "app.rpg.session.semantic_state_changes",
    "app.rpg.worlds.generation_first_pass_provider",
    "app.rpg.worlds.providers.single_pass",
    "app.rpg.worlds.providers.world_forge_foundation",
    "app.rpg.worlds.world_images",
    "app.story.jobs",
    "app.trading.research.market_brief",
    "app.trading.research.market_research",
)


def load_templates(modules: tuple[str, ...] = PROMPT_MODULES) -> dict[str, PromptTemplate]:
    """Import every prompt module and return its templates by id."""
    templates: dict[str, PromptTemplate] = {}
    for name in modules:
        declared = [value for value in vars(importlib.import_module(name)).values()
                    if isinstance(value, PromptTemplate)]
        if not declared:
            raise ValueError(f"{name} declares no prompt templates")
        for template in declared:
            if template.id in templates and templates[template.id] is not template:
                raise ValueError(f"prompt id {template.id} is declared twice")
            templates[template.id] = template
    return templates
