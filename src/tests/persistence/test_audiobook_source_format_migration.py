from __future__ import annotations

from app.persistence.migrations import discover_migrations


def test_audiobook_source_format_migration_allows_supported_ingestion_formats() -> None:
    migration = next(
        item
        for item in discover_migrations()
        if item.version == "0090_audiobook_source_format_expansion"
    )

    for source_format in (
        "docx", "epub", "htm", "html", "markdown", "md", "pdf", "text", "txt",
    ):
        assert f"'{source_format}'" in migration.sql
    assert "DROP CONSTRAINT IF EXISTS omnix_audiobook_source_revisions_source_format_check" in migration.sql
    assert "ADD CONSTRAINT omnix_audiobook_source_revisions_source_format_check" in migration.sql
