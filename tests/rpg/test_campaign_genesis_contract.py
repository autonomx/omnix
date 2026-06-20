from __future__ import annotations

from app.rpg.session.genesis import (
    CAMPAIGN_GENESIS_CONTRACT_VERSION,
    CampaignGenesisContract,
    adapt_genesis_payload_to_new_game_payload,
    canonical_genesis_payload,
    genesis_contract_hash,
)


def _payload() -> dict[str, object]:
    return {
        "identity": {"name": "Kara", "origin": "frontier_village", "background": "Scout"},
        "drivers": {
            "archetype": "scout",
            "motivation": {"primary": "survival", "target": "home", "intensity": 100},
            "flaw": "reckless",
            "talents": [{"id": "tracking", "rank": 1}],
            "values": ["family"],
        },
        "initial_stats": {"strength": 16, "agility": 12, "endurance": 11, "intellect": 9, "charisma": 10, "perception": 14, "archery": 13, "survival": 15},
        "starter_gear_tags": ["ranged_weapon", "starting_coin"],
        "story_options": {"opening_hook": "bandit_trail", "opening_pace": "immediate_action"},
        "world_options": {"starting_location": "northern_road", "difficulty": "harsh", "seed": 4242},
        "system_options": {"companions": False, "image_generation": True},
    }


def test_campaign_genesis_hash_is_stable() -> None:
    contract = CampaignGenesisContract.model_validate(_payload())

    assert canonical_genesis_payload(contract)["contract_version"] == CAMPAIGN_GENESIS_CONTRACT_VERSION
    assert genesis_contract_hash(contract) == genesis_contract_hash(CampaignGenesisContract.model_validate(canonical_genesis_payload(contract)))


def test_genesis_adapter_prefers_typed_fields_over_summary() -> None:
    legacy = adapt_genesis_payload_to_new_game_payload({"request": {"genesis": _payload(), "generated_class_summary": "Stats: strength 8."}})

    assert legacy["starting_location"] == "northern_road"
    assert legacy["difficulty"] == "harsh"
    assert legacy["companions_enabled"] is False
    assert legacy["features"]["image_generation"] is True
    assert "strength 16" in legacy["generated_class_summary"]
    assert "strength 8" not in legacy["generated_class_summary"]
