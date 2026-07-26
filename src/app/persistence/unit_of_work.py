from __future__ import annotations

import os
import sys
from types import TracebackType
from typing import Any, Literal

from .authority import (
    AuthorityOperation,
    initialize_fresh_install_authority,
    require_authority_operation,
)
from .asset_repository import (
    PostgresAssetRepository,
    PostgresSecretReferenceRepository,
    PostgresSettingsRepository,
)
from .conversation_repositories import (
    PostgresCharacterRepository,
    PostgresChatRepository,
    PostgresMemoryRepository,
)
from .database import PostgresDatabase, default_database
from .execution_repositories import PostgresForegroundSubmissionRepository
from .job_repository import PostgresJobRepository
from .module_repositories import (
    PostgresModuleRecordRepository,
    PostgresProjectionRepository,
    PostgresPromptRepository,
    PostgresProviderRepository,
    PostgresResearchReportRepository,
)
from .outbox_repository import (
    PostgresOutboxConsumerRepository,
    PostgresOutboxRepository,
    PostgresSideEffectRepository,
)
from .repositories import (
    PostgresAuditRepository,
    PostgresIdempotencyRepository,
    PostgresIdentityRepository,
)
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
from .rpg_trusted_world_scenario_repository import (
    PostgresTrustedRpgWorldScenarioRepository,
)
from .rpg_world_forge_repository import PostgresRpgWorldForgeRepository
from .rpg_world_generation_repository import PostgresRpgWorldGenerationRepository
from .rpg_world_library_repository import PostgresRpgWorldLibraryRepository
from .transaction_policy import transaction_scope


class UnitOfWorkClosedError(RuntimeError):
    pass


class PostgresUnitOfWork:
    """One explicit transaction shared by all repositories in an operation."""

    def __init__(
        self,
        database: PostgresDatabase | None = None,
        *,
        authority_operation: AuthorityOperation = AuthorityOperation.RUNTIME_MUTATION,
    ) -> None:
        self.database = database or default_database()
        self.authority_operation = authority_operation
        self.connection: Any | None = None
        self.identities: PostgresIdentityRepository
        self.audit: PostgresAuditRepository
        self.idempotency: PostgresIdempotencyRepository
        self.assets: PostgresAssetRepository
        self.settings: PostgresSettingsRepository
        self.secret_references: PostgresSecretReferenceRepository
        self.characters: PostgresCharacterRepository
        self.memories: PostgresMemoryRepository
        self.chats: PostgresChatRepository
        self.jobs: PostgresJobRepository
        self.outbox: PostgresOutboxRepository
        self.outbox_consumers: PostgresOutboxConsumerRepository
        self.side_effects: PostgresSideEffectRepository
        self.foreground_submissions: PostgresForegroundSubmissionRepository
        self.rpg: PostgresRpgRepository
        self.campaign_bibles: PostgresRpgCampaignBibleRepository
        self.campaign_genesis: PostgresRpgCampaignGenesisRepository
        self.world_forge: PostgresRpgWorldForgeRepository
        self.world_scenarios: PostgresTrustedRpgWorldScenarioRepository
        self.world_generation: PostgresRpgWorldGenerationRepository
        self.world_library: PostgresRpgWorldLibraryRepository
        self.map_instances: PostgresRpgMapInstanceRepository
        self.npc_spatial: PostgresRpgNpcSpatialRepository
        self.observers: PostgresRpgObserverRepository
        self.hermes_research: PostgresRpgHermesResearchRepository
        self.narrative_responses: PostgresRpgNarrativeResponseRepository
        self.narrative_deliveries: PostgresRpgNarrativeDeliveryRepository
        self.narrative_retirement: PostgresRpgNarrativeRetirementRepository
        self.module_records: PostgresModuleRecordRepository
        self.projections: PostgresProjectionRepository
        self.providers: PostgresProviderRepository
        self.prompts: PostgresPromptRepository
        self.research_reports: PostgresResearchReportRepository
        self._connection_context: Any | None = None
        self._transaction_scope_context: Any | None = None
        self._completed = False

    def __enter__(self) -> "PostgresUnitOfWork":
        if self.connection is not None:
            raise RuntimeError("Unit of Work cannot be entered twice")
        self._connection_context = self.database.connection()
        self.connection = self._connection_context.__enter__()
        try:
            if self.authority_operation == AuthorityOperation.RUNTIME_MUTATION:
                schema_row = self.connection.execute(
                    "SELECT version FROM omnix_schema_migrations ORDER BY version DESC LIMIT 1"
                ).fetchone()
                initialize_fresh_install_authority(
                    self.connection,
                    software_revision=(
                        os.environ.get("OMNIX_SOFTWARE_REVISION")
                        or "fresh-install-unversioned"
                    ).strip(),
                    schema_version=(
                        str(schema_row[0]) if schema_row is not None else "unknown-schema"
                    ),
                )
            require_authority_operation(self.connection, self.authority_operation)
        except BaseException:
            context, self._connection_context = self._connection_context, None
            self.connection = None
            if context is not None:
                context.__exit__(*sys.exc_info())
            raise
        self._transaction_scope_context = transaction_scope()
        self._transaction_scope_context.__enter__()
        self.identities = PostgresIdentityRepository(self.connection)
        self.audit = PostgresAuditRepository(self.connection)
        self.idempotency = PostgresIdempotencyRepository(self.connection)
        self.assets = PostgresAssetRepository(self.connection)
        self.settings = PostgresSettingsRepository(self.connection)
        self.secret_references = PostgresSecretReferenceRepository(self.connection)
        self.characters = PostgresCharacterRepository(self.connection)
        self.memories = PostgresMemoryRepository(self.connection)
        self.chats = PostgresChatRepository(self.connection)
        self.jobs = PostgresJobRepository(self.connection)
        self.outbox = PostgresOutboxRepository(self.connection)
        self.outbox_consumers = PostgresOutboxConsumerRepository(self.connection)
        self.side_effects = PostgresSideEffectRepository(self.connection)
        self.foreground_submissions = PostgresForegroundSubmissionRepository(self.connection)
        self.rpg = PostgresRpgRepository(self.connection)
        self.campaign_bibles = PostgresRpgCampaignBibleRepository(self.connection)
        self.campaign_genesis = PostgresRpgCampaignGenesisRepository(self.connection)
        self.world_forge = PostgresRpgWorldForgeRepository(self.connection)
        self.world_scenarios = PostgresTrustedRpgWorldScenarioRepository(self.connection)
        self.world_generation = PostgresRpgWorldGenerationRepository(self.connection)
        self.world_library = PostgresRpgWorldLibraryRepository(self.connection)
        self.map_instances = PostgresRpgMapInstanceRepository(self.connection)
        self.npc_spatial = PostgresRpgNpcSpatialRepository(self.connection)
        self.observers = PostgresRpgObserverRepository(self.connection)
        self.hermes_research = PostgresRpgHermesResearchRepository(self.connection)
        self.narrative_responses = PostgresRpgNarrativeResponseRepository(self.connection)
        self.narrative_deliveries = PostgresRpgNarrativeDeliveryRepository(
            self.connection
        )
        self.narrative_retirement = PostgresRpgNarrativeRetirementRepository(
            self.connection
        )
        self.module_records = PostgresModuleRecordRepository(self.connection)
        self.projections = PostgresProjectionRepository(self.connection)
        self.providers = PostgresProviderRepository(self.connection)
        self.prompts = PostgresPromptRepository(self.connection)
        self.research_reports = PostgresResearchReportRepository(self.connection)
        return self

    def commit(self) -> None:
        connection = self._require_connection()
        connection.commit()
        self._completed = True

    def rollback(self) -> None:
        connection = self._require_connection()
        connection.rollback()
        self._completed = True

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        connection = self._require_connection()
        try:
            if exc_type is not None or not self._completed:
                connection.rollback()
        finally:
            transaction_context, self._transaction_scope_context = (
                self._transaction_scope_context,
                None,
            )
            context, self._connection_context = self._connection_context, None
            self.connection = None
            self._completed = True
            if transaction_context is not None:
                transaction_context.__exit__(exc_type, exc, traceback)
            if context is not None:
                context.__exit__(exc_type, exc, traceback)
        return False

    def _require_connection(self) -> Any:
        if self.connection is None:
            raise UnitOfWorkClosedError("Unit of Work is not active")
        return self.connection


def unit_of_work(
    database: PostgresDatabase | None = None,
    *,
    authority_operation: AuthorityOperation = AuthorityOperation.RUNTIME_MUTATION,
) -> PostgresUnitOfWork:
    return PostgresUnitOfWork(database, authority_operation=authority_operation)
