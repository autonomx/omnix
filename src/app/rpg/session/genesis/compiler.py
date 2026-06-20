"""First-class deterministic compiler for Campaign Genesis contracts."""

from __future__ import annotations

from typing import Any

from .contract import CampaignGenesisContract, genesis_contract_hash

GENESIS_COMPILER_VERSION = "rpg_genesis_compiler_v1"
_WORLD_PROFILE_TRAITS = {
    "harsh_frontier": ["scarce_resources", "remote_start", "active_factions"],
    "quiet_start": ["low_pressure", "local_rumors"],
}


def _normal_key(value: object) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _world_traits(contract: CampaignGenesisContract) -> list[str]:
    world = contract.world_options
    traits = list(_WORLD_PROFILE_TRAITS.get(_normal_key(world.world_profile), []))
    if world.difficulty == "harsh":
        traits.append("high_risk")
    if world.world_activity == "living_world":
        traits.append("active_world")
    if world.economy_pressure == "strict":
        traits.append("scarce_resources")
    if world.combat_lethality == "deadly":
        traits.append("high_consequence")
    return list(dict.fromkeys(traits))


def _gear_intents(contract: CampaignGenesisContract) -> list[dict[str, str]]:
    return [
        {"tag": _normal_key(tag), "quality": "starter", "role": "starter"}
        for tag in contract.starter_gear_tags
    ]


def compile_campaign_genesis(contract: CampaignGenesisContract) -> dict[str, Any]:
    """Compile declarative genesis into deterministic pre-bootstrap state."""

    return {
        "compiler_version": GENESIS_COMPILER_VERSION,
        "compiled_stats": contract.initial_stats.model_dump(mode="json"),
        "compiled_resources": {},
        "compiled_world_traits": _world_traits(contract),
        "compiled_goals": [
            {
                "id": "establish_foothold",
                "source": "genesis:bootstrap",
                "priority": 50,
                "status": "active",
            }
        ],
        "compiled_decision_biases": {},
        "compiled_gear_intents": _gear_intents(contract),
        "compiled_story_state": contract.story_options.model_dump(mode="json", exclude_none=True),
        "compiled_feature_flags": contract.system_options.model_dump(mode="json"),
        "compiled_provenance": {
            "contract_version": contract.contract_version,
            "compiler_version": GENESIS_COMPILER_VERSION,
            "contract_hash": genesis_contract_hash(contract),
        },
    }
