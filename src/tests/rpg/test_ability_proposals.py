from __future__ import annotations

from typing import Any

from app.rpg.session.ability_proposals import build_progression_package_from_ai_proposal, compile_ai_ability_tree_proposal
from app.rpg.session.ability_system import validate_ability_tree


def _identity() -> dict[str, Any]:
    return {
        "genre": "cyberpunk",
        "primary_capability": "technical",
        "secondary_capabilities": ["knowledge", "recon"],
        "power_source": "technology",
        "generated_class_name": "Netrunner",
    }


def test_ai_ability_tree_proposal_compiles_fiction_onto_engine_mechanics() -> None:
    result = compile_ai_ability_tree_proposal(
        _identity(),
        {
            "class_name": "Ghostwalker",
            "class_summary": "A covert systems intruder with stolen corporate ghosts in their deck.",
            "categories": [
                {
                    "capability": "technical",
                    "name": "Corporate Backdoors",
                    "abilities": [
                        {
                            "name": "Ghost Door",
                            "description": "Spoof an access system into briefly accepting you as authorized.",
                            "purpose": "access_bypass",
                            "flavor_tags": ["corporate", "stealth protocol"],
                            "resource_cost": {"mana": 999},
                            "cooldown_turns": 99,
                            "effect_ops": [{"dimension": "access", "op": "invent_freeform_hack"}],
                        }
                    ],
                }
            ],
        },
        seed=77,
    )

    assert result.ok is True
    assert result.fallback_used is False
    assert result.source == "ai_proposal_validated_v1"
    assert validate_ability_tree(result.tree).ok is True
    assert result.tree["class_name"] == "Ghostwalker"
    assert result.tree["categories"][0]["name"] == "Corporate Backdoors"

    renamed = next(ability for ability in result.tree["abilities"] if ability["ability_id"] == "technical_signal_probe")
    assert renamed["name"] == "Ghost Door"
    assert renamed["description"].startswith("Spoof an access system")
    assert renamed["purpose"] == "access_bypass"
    assert renamed["resource_cost"] != {"mana": 999}
    assert all(effect["op"] != "invent_freeform_hack" for effect in renamed["effect_ops"])
    assert any("ignored engine-owned field effect_ops" in repair for repair in result.repairs)
    assert result.tree["proposal_trace"]["mechanics_source"] == "template_family_v1"


def test_ai_ability_tree_proposal_falls_back_when_no_usable_fiction_is_supplied() -> None:
    result = compile_ai_ability_tree_proposal(_identity(), {"categories": [{"abilities": [{"effect_ops": []}]}]}, seed=12)

    assert result.ok is True
    assert result.fallback_used is True
    assert result.source == "template_family_v1"
    assert result.tree["class_name"] == "Netrunner"
    assert validate_ability_tree(result.tree).ok is True
    assert "no usable fiction" in result.errors[0]


def test_ai_ability_tree_proposal_ignores_unsupported_purpose_without_invalidating_tree() -> None:
    result = compile_ai_ability_tree_proposal(
        _identity(),
        {
            "class_name": "Signal Witch",
            "categories": [
                {
                    "capability": "technical",
                    "abilities": [
                        {
                            "name": "Hex the Camera",
                            "purpose": "vibes",
                        }
                    ],
                }
            ],
        },
    )

    assert result.ok is True
    assert result.fallback_used is False
    assert validate_ability_tree(result.tree).ok is True
    ability = next(ability for ability in result.tree["abilities"] if ability["ability_id"] == "technical_signal_probe")
    assert ability["name"] == "Hex the Camera"
    assert ability["purpose"] == "information_gathering"
    assert any("unsupported purpose vibes" in repair for repair in result.repairs)


def test_progression_package_from_ai_proposal_records_validation_result_without_storing_duplicate_tree() -> None:
    package = build_progression_package_from_ai_proposal(
        {
            "genre": "detective_noir",
            "primary_capability": "recon",
            "power_source": "mundane",
            "player": {"background": "ex-police investigator"},
        },
        {
            "class_name": "Cold Case Hound",
            "categories": [{"capability": "recon", "name": "Case Pressure", "abilities": [{"name": "Read the Lie"}]}],
        },
        build_id="balanced_adventurer",
        level=1,
        seed=5,
    )

    assert package["character_identity"]["genre"] == "detective_noir"
    assert package["ability_tree"]["source"] == "ai_proposal_validated_v1"
    assert package["ability_tree"]["class_name"] == "Cold Case Hound"
    assert package["ability_state"]["unlocked"]
    assert "tree" not in package["ability_tree_proposal_result"]
    assert package["ability_tree_proposal_result"]["source"] == "ai_proposal_validated_v1"
