from __future__ import annotations

from app.rpg.session.genesis.request_promoter import promote_new_game_request_to_genesis


def test_promote_legacy_new_game_payload_to_genesis_contract() -> None:
    contract = promote_new_game_request_to_genesis(
        {
            "campaign_template": "deterministic_rpg_campaign",
            "tone": "Road scout",
            "background": "wanderer",
            "starting_location": "rusty_flagon_tavern",
            "player": {"name": "Mira", "pronouns": "she/her", "build": "ranger"},
            "primary_capability": "recon",
            "secondary_capabilities": ["survival"],
            "power_source": "magic",
            "initial_stats": {"strength": 9, "agility": 11, "perception": 12},
            "starter_gear_tags": ["field_notes", "travel_supplies"],
            "opening_hook": "tavern_rumor",
            "difficulty": "harsh",
            "world_activity": "living_world",
            "economy_pressure": "strict",
            "seed": 9137,
            "companions_enabled": False,
            "permadeath": True,
            "features": {"image_generation": True, "tts": True},
        }
    )

    assert contract.contract_version == "rpg_genesis_v2"
    assert contract.identity.name == "Mira"
    assert contract.identity.origin == "open_road"
    assert contract.drivers.motivation.primary == "survival"
    assert contract.drivers.talents[0].id == "recon"
    assert contract.drivers.talents[0].rank == 2
    assert contract.initial_stats.perception == 12
    assert contract.starter_gear_tags == ["field_notes", "travel_supplies"]
    assert contract.world_options.starting_location == "rusty_flagon_tavern"
    assert contract.world_options.seed == 9137
    assert contract.system_options.companions is False
    assert contract.system_options.permadeath is True
    assert contract.system_options.image_generation is True
    assert contract.system_options.tts is True
