"""Phase 8.5 — Save Migration / Packaging Interoperability.

Stable export surface for the migration subsystem.
"""

from .models import (
    CURRENT_PACK_FORMAT_VERSION,
    CURRENT_SAVE_FORMAT_VERSION,
    SUPPORTED_MIGRATION_SCOPES,
    CompatibilityReport,
    MigratedPayload,
    MigrationReport,
    MigrationStep,
    PackCompatibilityResult,
)
from .pack_migrator import PackMigrator
from .registry import MigrationRegistry
from .save_migrator import SaveMigrator

__all__ = [
    "CURRENT_PACK_FORMAT_VERSION",
    "CURRENT_SAVE_FORMAT_VERSION",
    "SUPPORTED_MIGRATION_SCOPES",
    "CompatibilityReport",
    "MigratedPayload",
    "MigrationRegistry",
    "MigrationReport",
    "MigrationStep",
    "PackCompatibilityResult",
    "PackMigrator",
    "SaveMigrator",
]
