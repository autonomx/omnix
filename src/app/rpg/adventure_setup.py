"""Compatibility wrapper for Phase 7 creator-driven adventure setup.

NOTE:
This module is compatibility-only.
The authoritative setup path is app.rpg.creator.schema.AdventureSetup.
"""

from __future__ import annotations

from .creator import AdventureSetup, StartupGenerationPipeline


class AdventureSetupService:
    def build_setup(self, payload: dict) -> AdventureSetup:
        setup = AdventureSetup.from_dict(payload)
        setup.validate()
        return setup

    def start_adventure(self, setup: AdventureSetup, game_loop) -> dict:
        return game_loop.start_new_adventure(setup.to_dict())


class AdventureConfig:
    """Legacy setup model retained for backwards compatibility only."""
    def __init__(self, theme="fantasy", difficulty="medium", player_background="hero"):
        self.theme = theme
        self.difficulty = difficulty
        self.player_background = player_background
        self.custom_rules = []
        self.lore_elements = []

    def add_custom_rule(self, rule):
        self.custom_rules.append(rule)

    def add_lore_element(self, element):
        self.lore_elements.append(element)


def generate_world(config: AdventureConfig):
    """Legacy world generator retained for backwards compatibility only."""
    # Placeholder for LLM call - in real implementation, this would call an LLM
    # with prompts based on config.theme, config.difficulty, etc.

    world = {
        "factions": [
            {"name": "Kingdom of Eldoria", "description": "A noble realm seeking peace"},
            {"name": "Shadow Syndicate", "description": "A criminal organization thriving in chaos"}
        ],
        "npcs": [
            {
                "id": "king_arthur",
                "name": "King Arthur",
                "faction": "Kingdom of Eldoria",
                "personality": "wise and just",
                "goals": ["maintain peace", "defeat evil"]
            },
            {
                "id": "shadow_lord",
                "name": "Shadow Lord",
                "faction": "Shadow Syndicate",
                "personality": "cunning and ruthless",
                "goals": ["expand influence", "undermine the kingdom"]
            }
        ],
        "locations": [
            {"name": "Castle Eldoria", "description": "The seat of royal power"},
            {"name": "Dark Alley", "description": "A dangerous part of the city"}
        ],
        "conflicts": [
            {"description": "The Shadow Syndicate plots to assassinate the king"}
        ],
        "tensions": [
            {"description": "Rising distrust between factions"}
        ]
    }

    # Incorporate custom rules and lore from config
    if config.custom_rules:
        world["custom_rules"] = config.custom_rules

    if config.lore_elements:
        world["lore"] = config.lore_elements

    return world


__all__ = [
    "AdventureConfig",
    "AdventureSetup",
    "AdventureSetupService",
    "StartupGenerationPipeline",
    "generate_world",
]