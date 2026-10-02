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
    "app.assist_core.hermes_client",
    "app.assist_core.rpg_direction",
    "app.assistant_context.vision",
    "app.assistant_memory.initiative",
    "app.assistant_memory.paralinguistic_state",
    "app.assistant_memory.structured_provider",
    "app.characters.avatar_generation_service",
    "app.characters.avatar_viseme_generation",
    "app.characters.interaction",
    "app.characters.stage1_contracts",
    "app.chat.live_call_greeting",
    "app.chat.live_conversation_proactive",
    "app.desktop_companion.commentary",
    "app.desktop_companion.observation",
    "app.platform.effective_defaults",
    "app.providers.chatgpt_codex_provider",
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
