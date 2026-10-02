"""Always-on persistence repository specs for composition."""
from __future__ import annotations

from .repository_registry import RepositorySpec


def shared_repository_specs() -> tuple[RepositorySpec, ...]:
    from .module_repositories import (
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
