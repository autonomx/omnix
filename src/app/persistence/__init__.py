"""Centralized PostgreSQL persistence for Omnix.

Domain services should acquire repositories through a Unit of Work rather than
constructing database connections directly.
"""

from .config import DatabaseSettings, database_settings
from .database import PostgresDatabase, default_database
from .migrations import MigrationError, apply_migrations, migration_status

__all__ = [
    "DatabaseSettings",
    "MigrationError",
    "PostgresDatabase",
    "apply_migrations",
    "database_settings",
    "default_database",
    "migration_status",
]
