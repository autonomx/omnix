from __future__ import annotations

from app.persistence.migrations import discover_migrations


def test_audiobook_character_metadata_migration_is_append_only_schema_extension() -> None:
    migration = next(
        item
        for item in discover_migrations()
        if item.version == "0092_audiobook_character_analysis_metadata"
    )

    assert "ALTER TABLE omnix_audiobook_speakers" in migration.sql
    assert "ADD COLUMN IF NOT EXISTS analysis_metadata JSONB" in migration.sql
    assert "DEFAULT '{}'::jsonb" in migration.sql
