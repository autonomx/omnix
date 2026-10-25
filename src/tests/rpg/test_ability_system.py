from __future__ import annotations

from typing import Any

import pytest

from app.apps.rpg.session.ability_tree import build_ability_tree, build_progression_package, validate_ability_tree


def _base_active_ability(**overrides: Any) -> dict[str, Any]:
    ability = {
        "ability_id": "test_active",
        "kind": "active",
        "name": "Test Active",
        "description": "A deterministic test ability.",
        "capability": "knowledge",
        "power_source": "magic",
        "purpose": "utility",
        "dimensions": ["information"],
        "level_required": 1,
        "rank": 1,
        "max_rank": 3,
        "resource_cost": {"mana": 1},
        "cooldown_turns": 1,
        "prerequisites": [],
        "effect_ops": [{"dimension": "information", "op": "reveal_clue", "clue_tag": "test_clue"}],
    }
    ability.update(overrides)
    return ability


def test_progression_package_stores_capability_identity_and_valid_tree() -> None:
    package = build_progression_package(
        {
            "campaign_template": "cyberpunk",
            "genre": "cyberpunk",
            "tone": "street-level neon noir",
            "player": {"name": "Nyx", "background": "corporate defector", "build": "balanced_adventurer"},
            "primary_capability": "technical",
            "secondary_capabilities": ["knowledge", "recon"],
            "power_source": "technology",
        },
        build_id="balanced_adventurer",
        level=1,
        seed=123,
    )

    identity = package["character_identity"]
    assert identity["primary_capability"] == "technical"
    assert identity["power_source"] == "technology"
    assert identity["generated_class_name"] == "Netrunner"

    tree = package["ability_tree"]
    assert validate_ability_tree(tree).ok is True
    assert tree["design_rule"].startswith("Every active ability")
    assert {"information", "access"}.issubset(set(tree["dimensions"]))


@pytest.mark.parametrize(
    ("identity", "expected_family", "expected_class"),
    [
        ({"genre": "classic_fantasy", "primary_capability": "knowledge", "power_source": "magic"}, "classic_fantasy_knowledge_magic_v1", "Runebinder"),
        ({"genre": "classic_fantasy", "primary_capability": "combat", "power_source": "martial"}, "classic_fantasy_combat_martial_v1", "Champion"),
        ({"genre": "classic_fantasy", "primary_capability": "recon", "power_source": "martial"}, "classic_fantasy_recon_martial_v1", "Ranger"),
        ({"genre": "cyberpunk", "primary_capability": "technical", "power_source": "technology"}, "cyberpunk_technical_technology_v1", "Netrunner"),
        ({"genre": "cyberpunk", "primary_capability": "combat", "power_source": "technology"}, "cyberpunk_combat_technology_v1", "Street Samurai"),
        ({"genre": "detective_noir", "primary_capability": "recon", "power_source": "mundane"}, "detective_noir_recon_mundane_v1", "Private Eye"),
        ({"genre": "political_intrigue", "primary_capability": "influence", "power_source": "social_power"}, "political_intrigue_influence_social_power_v1", "Court Schemer"),
        ({"genre": "post_apocalyptic", "primary_capability": "survival", "power_source": "scrap"}, "post_apocalyptic_survival_scrap_v1", "Scavenger"),
        ({"genre": "space_opera", "primary_capability": "knowledge", "power_source": "psionic"}, "space_opera_knowledge_psionic_v1", "Psionic"),
        ({"genre": "space_opera", "primary_capability": "technical", "power_source": "technology"}, "space_opera_technical_technology_v1", "Science Officer"),
        ({"genre": "modern_occult", "primary_capability": "knowledge", "power_source": "occult"}, "modern_occult_knowledge_occult_v1", "Ritualist"),
        ({"genre": "survival_horror", "primary_capability": "survival", "power_source": "mundane"}, "survival_horror_survival_mundane_v1", "Survivor"),
    ],
)
def test_template_families_build_valid_playable_trees(identity: dict[str, Any], expected_family: str, expected_class: str) -> None:
    tree = build_ability_tree(identity)

    assert tree["source"] == "template_family_v1"
    assert tree["template_family"] == expected_family
    assert tree["class_name"] == expected_class
    assert validate_ability_tree(tree).ok is True
    assert tree["starting_unlocks"]
    assert tree["recommended_hotbar"] == tree["starting_unlocks"][:6]
    assert any(ability["kind"] == "passive" and ability["hooks"] for ability in tree["abilities"])
    assert any(ability["kind"] == "narrative_trait" and ability["influence_tags"] for ability in tree["abilities"])
    assert any(ability["kind"] == "active" and ability["effect_ops"] for ability in tree["abilities"])


def test_active_abilities_must_have_dimension_effects() -> None:
    tree = {
        "abilities": [
            {
                "ability_id": "flavor_only",
                "kind": "active",
                "name": "Flavor Only",
                "description": "No mechanics.",
                "capability": "knowledge",
                "power_source": "magic",
                "purpose": "utility",
                "dimensions": ["narrative"],
                "effect_ops": [],
            }
        ]
    }

    result = validate_ability_tree(tree)

    assert result.ok is False
    assert any("active ability has no effect_ops" in error for error in result.errors)


def test_validator_accepts_valid_active_passive_and_narrative_trait() -> None:
    tree = {
        "abilities": [
            _base_active_ability(),
            {
                "ability_id": "keen_eye",
                "kind": "passive",
                "name": "Keen Eye",
                "description": "Improves clue discovery through a deterministic hook.",
                "capability": "recon",
                "power_source": "mundane",
                "purpose": "information_gathering",
                "dimensions": ["information"],
                "resource_cost": {},
                "cooldown_turns": 0,
                "level_required": 1,
                "rank": 1,
                "max_rank": 3,
                "prerequisites": [],
                "hooks": ["on_investigation_check"],
                "effect_ops": [],
            },
            {
                "ability_id": "former_detective",
                "kind": "narrative_trait",
                "name": "Former Detective",
                "description": "A saved grounded fact that unlocks investigative context.",
                "capability": "recon",
                "power_source": "mundane",
                "purpose": "information_gathering",
                "dimensions": ["information", "relationships", "narrative"],
                "resource_cost": {},
                "cooldown_turns": 0,
                "level_required": 1,
                "rank": 1,
                "max_rank": 1,
                "prerequisites": [],
                "influence_tags": ["recognize_police_procedure", "unlock_detective_dialogue_paths"],
                "effect_ops": [],
            },
        ]
    }

    result = validate_ability_tree(tree)

    assert result.ok is True
    assert result.errors == []


def test_validator_rejects_unsupported_schema_values() -> None:
    tree = {
        "abilities": [
            _base_active_ability(
                capability="alchemy",
                power_source="vibes",
                purpose="flavor",
                dimensions=["mood"],
                effect_ops=[{"dimension": "mood", "op": "invent_mechanic"}],
            )
        ]
    }

    result = validate_ability_tree(tree)

    assert result.ok is False
    assert any("unsupported capability alchemy" in error for error in result.errors)
    assert any("unsupported power_source vibes" in error for error in result.errors)
    assert any("unsupported purpose flavor" in error for error in result.errors)
    assert any("invalid dimensions" in error for error in result.errors)
    assert any("unsupported effect op invent_mechanic" in error for error in result.errors)


def test_validator_rejects_bad_cost_cooldown_and_gates() -> None:
    tree = {
        "abilities": [
            _base_active_ability(
                resource_cost={"story_tokens": 1, "mana": -1},
                cooldown_turns=-1,
                level_required=0,
                rank=3,
                max_rank=2,
            )
        ]
    }

    result = validate_ability_tree(tree)

    assert result.ok is False
    assert any("invalid cost resource story_tokens" in error for error in result.errors)
    assert any("invalid cost value for mana" in error for error in result.errors)
    assert any("invalid cooldown_turns" in error for error in result.errors)
    assert any("invalid level_required" in error for error in result.errors)
    assert any("rank exceeds max_rank" in error for error in result.errors)


def test_validator_rejects_invalid_prerequisites() -> None:
    tree = {
        "abilities": [
            _base_active_ability(prerequisites=["test_active", "missing_ability", "missing_ability", 42]),
        ]
    }

    result = validate_ability_tree(tree)

    assert result.ok is False
    assert any("prerequisite cannot reference itself" in error for error in result.errors)
    assert any("missing prerequisite missing_ability" in error for error in result.errors)
    assert any("duplicate prerequisite missing_ability" in error for error in result.errors)
    assert any("invalid prerequisite 42" in error for error in result.errors)


def test_narrative_trait_without_effect_ops_requires_deterministic_hooks() -> None:
    tree = {
        "abilities": [
            {
                "ability_id": "flavor_trait",
                "kind": "narrative_trait",
                "name": "Flavor Trait",
                "description": "Pure prose without deterministic hooks.",
                "capability": "knowledge",
                "power_source": "mundane",
                "purpose": "utility",
                "dimensions": ["narrative"],
                "resource_cost": {},
                "cooldown_turns": 0,
                "level_required": 1,
                "rank": 1,
                "max_rank": 1,
                "prerequisites": [],
                "effect_ops": [],
            }
        ]
    }

    result = validate_ability_tree(tree)

    assert result.ok is False
    assert any("narrative_trait without effect_ops requires deterministic influence_tags or hooks" in error for error in result.errors)
