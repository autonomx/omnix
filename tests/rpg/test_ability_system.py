from __future__ import annotations

from typing import Any

from app.rpg.session.ability_system import apply_ability_to_state, build_progression_package, validate_ability_tree


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


def test_ability_use_changes_information_and_access_dimensions() -> None:
    package = build_progression_package(
        {
            "genre": "cyberpunk",
            "player": {"name": "Nyx", "background": "corporate defector", "build": "balanced_adventurer"},
            "primary_capability": "technical",
            "power_source": "technology",
        },
        build_id="balanced_adventurer",
        level=1,
        seed=456,
    )
    state: dict[str, Any] = {
        "player": {"resources": {"mana": {"current": 20, "max": 40}, "stamina": {"current": 50, "max": 50}}},
        "ability_tree": package["ability_tree"],
        "ability_state": package["ability_state"],
        "hotbar": package["hotbar"],
    }

    result = apply_ability_to_state(state, ability_name="Signal Probe", target="locked terminal")

    assert result.ok is True
    assert state["player"]["resources"]["mana"] == {"current": 14, "max": 40}
    assert state["clues"][0]["tag"] == "system_weakness"
    assert state["narrative_affordances"]["scene"][0]["tag"] == "technical_bypass_hint"
    assert result.effects[0]["dimension"] == "information"
