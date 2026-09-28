"""Repository registrations owned by the RPG feature."""
from __future__ import annotations

from app.persistence.repository_registry import RepositorySpec

from .rpg_campaign_bible_repository import PostgresRpgCampaignBibleRepository
from .rpg_campaign_genesis_repository import PostgresRpgCampaignGenesisRepository
from .rpg_hermes_research_repository import PostgresRpgHermesResearchRepository
from .rpg_map_instance_repository import PostgresRpgMapInstanceRepository
from .rpg_narrative_delivery_repository import PostgresRpgNarrativeDeliveryRepository
from .rpg_narrative_response_repository import PostgresRpgNarrativeResponseRepository
from .rpg_narrative_retirement_repository import PostgresRpgNarrativeRetirementRepository
from .rpg_npc_spatial_repository import PostgresRpgNpcSpatialRepository
from .rpg_observer_repository import PostgresRpgObserverRepository
from .rpg_repository import PostgresRpgRepository
from .rpg_trusted_world_scenario_repository import PostgresTrustedRpgWorldScenarioRepository
from .rpg_world_forge_repository import PostgresRpgWorldForgeRepository
from .rpg_world_generation_repository import PostgresRpgWorldGenerationRepository
from .rpg_world_library_repository import PostgresRpgWorldLibraryRepository

RPG_REPOSITORY_SPECS = (
    RepositorySpec(PostgresRpgRepository, PostgresRpgRepository, "rpg"),
    RepositorySpec(PostgresRpgCampaignBibleRepository, PostgresRpgCampaignBibleRepository, "campaign_bibles"),
    RepositorySpec(PostgresRpgCampaignGenesisRepository, PostgresRpgCampaignGenesisRepository, "campaign_genesis"),
    RepositorySpec(PostgresRpgWorldForgeRepository, PostgresRpgWorldForgeRepository, "world_forge"),
    RepositorySpec(PostgresTrustedRpgWorldScenarioRepository, PostgresTrustedRpgWorldScenarioRepository, "world_scenarios"),
    RepositorySpec(PostgresRpgWorldGenerationRepository, PostgresRpgWorldGenerationRepository, "world_generation"),
    RepositorySpec(PostgresRpgWorldLibraryRepository, PostgresRpgWorldLibraryRepository, "world_library"),
    RepositorySpec(PostgresRpgMapInstanceRepository, PostgresRpgMapInstanceRepository, "map_instances"),
    RepositorySpec(PostgresRpgNpcSpatialRepository, PostgresRpgNpcSpatialRepository, "npc_spatial"),
    RepositorySpec(PostgresRpgObserverRepository, PostgresRpgObserverRepository, "observers"),
    RepositorySpec(PostgresRpgHermesResearchRepository, PostgresRpgHermesResearchRepository, "hermes_research"),
    RepositorySpec(PostgresRpgNarrativeResponseRepository, PostgresRpgNarrativeResponseRepository, "narrative_responses"),
    RepositorySpec(PostgresRpgNarrativeDeliveryRepository, PostgresRpgNarrativeDeliveryRepository, "narrative_deliveries"),
    RepositorySpec(PostgresRpgNarrativeRetirementRepository, PostgresRpgNarrativeRetirementRepository, "narrative_retirement"),
)
