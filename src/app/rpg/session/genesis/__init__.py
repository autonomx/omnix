"""Campaign genesis contract helpers for deterministic RPG session creation."""

from .contract import (
    CAMPAIGN_GENESIS_CONTRACT_VERSION,
    DEFAULT_GENESIS_CREATED_BY,
    CampaignGenesisContract,
    GenesisDrivers,
    GenesisIdentity,
    GenesisInitialStats,
    GenesisMotivation,
    GenesisStoryOptions,
    GenesisSystemOptions,
    GenesisTalent,
    GenesisWorldOptions,
    canonical_genesis_payload,
    genesis_contract_hash,
)
from .legacy_adapter import (
    adapt_genesis_payload_to_new_game_payload,
    attach_genesis_to_created_session,
    create_new_game_from_genesis_payload,
)

__all__ = [
    "CAMPAIGN_GENESIS_CONTRACT_VERSION",
    "DEFAULT_GENESIS_CREATED_BY",
    "CampaignGenesisContract",
    "GenesisDrivers",
    "GenesisIdentity",
    "GenesisInitialStats",
    "GenesisMotivation",
    "GenesisStoryOptions",
    "GenesisSystemOptions",
    "GenesisTalent",
    "GenesisWorldOptions",
    "adapt_genesis_payload_to_new_game_payload",
    "attach_genesis_to_created_session",
    "canonical_genesis_payload",
    "create_new_game_from_genesis_payload",
    "genesis_contract_hash",
]
