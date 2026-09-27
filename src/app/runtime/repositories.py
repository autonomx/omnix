"""Composition-time registration of feature repositories.

This module is intentionally outside app.persistence. Feature packages can
replace these legacy registrations with FeatureModule.repositories without
changing UnitOfWork.
"""
from __future__ import annotations

from app.persistence.repository_registry import RepositorySpec, install_repository_specs


def install_legacy_feature_repository_specs() -> None:
    from app.persistence.conversation_repositories import (
        PostgresCharacterRepository,
        PostgresChatRepository,
        PostgresMemoryRepository,
    )
    from app.persistence.module_repositories import (
        PostgresModuleRecordRepository,
        PostgresProjectionRepository,
        PostgresPromptRepository,
        PostgresProviderRepository,
        PostgresResearchReportRepository,
    )
    from app.persistence.rpg_campaign_bible_repository import PostgresRpgCampaignBibleRepository
    from app.persistence.rpg_campaign_genesis_repository import PostgresRpgCampaignGenesisRepository
    from app.persistence.rpg_hermes_research_repository import PostgresRpgHermesResearchRepository
    from app.persistence.rpg_map_instance_repository import PostgresRpgMapInstanceRepository
    from app.persistence.rpg_narrative_delivery_repository import PostgresRpgNarrativeDeliveryRepository
    from app.persistence.rpg_narrative_response_repository import PostgresRpgNarrativeResponseRepository
    from app.persistence.rpg_narrative_retirement_repository import PostgresRpgNarrativeRetirementRepository
    from app.persistence.rpg_npc_spatial_repository import PostgresRpgNpcSpatialRepository
    from app.persistence.rpg_observer_repository import PostgresRpgObserverRepository
    from app.persistence.rpg_repository import PostgresRpgRepository
    from app.persistence.rpg_trusted_world_scenario_repository import PostgresTrustedRpgWorldScenarioRepository
    from app.persistence.rpg_world_forge_repository import PostgresRpgWorldForgeRepository
    from app.persistence.rpg_world_generation_repository import PostgresRpgWorldGenerationRepository
    from app.persistence.rpg_world_library_repository import PostgresRpgWorldLibraryRepository

    specs = (
        RepositorySpec(PostgresCharacterRepository, PostgresCharacterRepository, "characters"),
        RepositorySpec(PostgresMemoryRepository, PostgresMemoryRepository, "memories"),
        RepositorySpec(PostgresChatRepository, PostgresChatRepository, "chats"),
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
        RepositorySpec(PostgresModuleRecordRepository, PostgresModuleRecordRepository, "module_records"),
        RepositorySpec(PostgresProjectionRepository, PostgresProjectionRepository, "projections"),
        RepositorySpec(PostgresProviderRepository, PostgresProviderRepository, "providers"),
        RepositorySpec(PostgresPromptRepository, PostgresPromptRepository, "prompts"),
        RepositorySpec(PostgresResearchReportRepository, PostgresResearchReportRepository, "research_reports"),
    )
    install_repository_specs(specs)
