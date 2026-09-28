"""Repository specs that are always available to the composition root."""
from __future__ import annotations

from app.persistence.repository_registry import RepositorySpec


def shared_repository_specs() -> tuple[RepositorySpec, ...]:
    from app.persistence.module_repositories import (
        PostgresModuleRecordRepository,
        PostgresProjectionRepository,
        PostgresPromptRepository,
        PostgresProviderRepository,
    )

    return (
        RepositorySpec(PostgresModuleRecordRepository, PostgresModuleRecordRepository, "module_records"),
        RepositorySpec(PostgresProjectionRepository, PostgresProjectionRepository, "projections"),
        RepositorySpec(PostgresProviderRepository, PostgresProviderRepository, "providers"),
        RepositorySpec(PostgresPromptRepository, PostgresPromptRepository, "prompts"),
    )
