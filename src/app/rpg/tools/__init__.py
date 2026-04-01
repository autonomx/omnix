"""RPG Tools — Action registry and tool function calling system.

This module provides the tool/function calling architecture that allows
the AI Director to execute actions, not just describe them.

Architecture:
    Director → decides action → ActionRegistry → executes → Events

Key Classes:
    ActionRegistry: Central registry for all available actions
"""

from rpg.tools.action_registry import ActionRegistry, ActionRegistryError

__all__ = [
    "ActionRegistry",
    "ActionRegistryError",
]