from __future__ import annotations

from app.rpg.session.genesis import (
    GENESIS_COMPILER_VERSION,
    CampaignGenesisContract,
    bootstrap_session_from_compiled_genesis,
    compile_campaign_genesis,
)


def _contract() -> CampaignGenesisContract:
    return CampaignGenesisContract.model_validate(
        {
            "identity": {"name": "Kara", "origin": "frontier_village"},
            "drivers": {"archetype": "scout"},
            "initial_stats": {"strength": 14, "agility": 12, "survival": 15},
            "starter_gear_tags": ["ranged_weapon", "travel_supplies"],
            "world_options": {
                "world_profile": "harsh_frontier",
                "difficulty": "harsh",
                "world_activity": "living_world",
                "economy_pressure": "strict",
                "combat_lethality": "deadly",
                "seed": 99,
            },
            "system_options": {"companions": False, "tts": True},
        }
    )


def test_compile_campaign_genesis_builds_versioned_snapshot() -> None:
    compiled = compile_campaign_genesis(_contract())

    assert compiled["compiler_version"] == GENESIS_COMPILER_VERSION
    assert compiled["compiled_stats"]["strength"] == 14
    assert compiled["compiled_feature_flags"]["companions"] is False
    assert compiled["compiled_feature_flags"]["tts"] is True
    assert "scarce_resources" in compiled["compiled_world_traits"]
    assert compiled["compiled_goals"][0]["id"] == "establish_foothold"
    assert compiled["compiled_gear_intents"][0]["tag"] == "ranged_weapon"
    assert compiled["compiled_provenance"]["compiler_version"] == GENESIS_COMPILER_VERSION


def test_bootstrap_session_from_compiled_genesis_projects_runtime_seed_state() -> None:
    compiled = compile_campaign_genesis(_contract())
    bootstrap = bootstrap_session_from_compiled_genesis(compiled)

    assert bootstrap["bootstrap_version"] == "rpg_genesis_bootstrap_v1"
    assert bootstrap["active_goals"] == compiled["compiled_goals"]
    assert bootstrap["gear_intents"] == compiled["compiled_gear_intents"]
    assert bootstrap["world_traits"] == compiled["compiled_world_traits"]
    assert bootstrap["feature_flags"]["companions"] is False
    assert bootstrap["provenance"]["compiler_version"] == GENESIS_COMPILER_VERSION
