"""Compatibility adapter from Campaign Genesis v2 to separated world launch data."""
from __future__ import annotations

from typing import Any, Mapping

from app.rpg.session.genesis.contract import CampaignGenesisContract

from .contracts import (
    CampaignLaunchContract,
    LegacyGenesisWorldLaunch,
    ScenarioProjectCreate,
    WorldProjectCreate,
    canonical_content_hash,
)


def adapt_campaign_genesis_to_world_launch(
    contract: CampaignGenesisContract,
    *,
    campaign_id: str,
    world_id: str | None = None,
    scenario_id: str | None = None,
) -> LegacyGenesisWorldLaunch:
    resolved_world_id = world_id or f"world:legacy:{campaign_id}"
    resolved_scenario_id = scenario_id or f"scenario:legacy:{campaign_id}"
    canonical = contract.model_dump(mode="json", exclude_none=True)
    world = WorldProjectCreate(
        world_id=resolved_world_id,
        title=f"{contract.campaign_template.replace('_', ' ').title()} World",
        description="Imported from the combined Campaign Genesis flow.",
        source_mode="imported",
        genre=contract.genre or contract.campaign_template,
        tone=contract.tone,
        seed=int(contract.world_options.seed or 0),
        metadata={
            "legacy_contract_version": contract.contract_version,
            "world_forge": contract.world_forge.model_dump(mode="json"),
        },
    )
    scenario = ScenarioProjectCreate(
        scenario_id=resolved_scenario_id,
        world_id=resolved_world_id,
        title=f"{world.title} Opening",
        description="Legacy campaign opening compatibility scenario.",
        metadata={
            "starting_location": contract.world_options.starting_location,
            "story_options": contract.story_options.model_dump(mode="json"),
        },
    )
    campaign = CampaignLaunchContract(
        campaign_id=campaign_id,
        campaign_title=world.title,
        world_id=resolved_world_id,
        world_revision=1,
        world_release=1,
        scenario_id=resolved_scenario_id,
        scenario_revision=1,
        protagonist={
            "identity": contract.identity.model_dump(mode="json"),
            "drivers": contract.drivers.model_dump(mode="json"),
            "initial_stats": contract.initial_stats.model_dump(mode="json"),
            "starter_gear_tags": list(contract.starter_gear_tags),
        },
        gameplay=contract.world_options.model_dump(mode="json"),
        runtime_features=contract.system_options.model_dump(mode="json"),
    )
    return LegacyGenesisWorldLaunch(
        world=world,
        scenario=scenario,
        campaign=campaign,
        legacy_payload_hash=canonical_content_hash(canonical),
    )


def adapt_genesis_payload_to_world_launch(
    payload: Mapping[str, Any],
    *,
    campaign_id: str,
) -> LegacyGenesisWorldLaunch:
    root = payload.get("request") if isinstance(payload.get("request"), Mapping) else payload
    genesis = root.get("genesis") if isinstance(root.get("genesis"), Mapping) else root
    return adapt_campaign_genesis_to_world_launch(
        CampaignGenesisContract.model_validate(genesis),
        campaign_id=campaign_id,
    )
