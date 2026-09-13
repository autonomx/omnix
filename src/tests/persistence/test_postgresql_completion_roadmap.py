from __future__ import annotations

from pathlib import Path


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_authoritative_postgresql_documents_exist() -> None:
    expected_paths = (
        "docs/architecture/ADR-0001-centralized-postgresql-authority.md",
        "docs/architecture/PERSISTENCE_INVENTORY.md",
        "docs/architecture/LOCAL_POSTGRESQL_OPERATIONS.md",
        "docs/architecture/POSTGRESQL_CUTOVER_RUNBOOK.md",
        "docs/architecture/POSTGRESQL_RUNTIME_RETIREMENT.md",
    )

    for relative in expected_paths:
        assert (_REPOSITORY_ROOT / relative).is_file(), relative


def test_postgresql_authority_document_defines_the_runtime_boundary() -> None:
    text = (
        _REPOSITORY_ROOT
        / "docs"
        / "architecture"
        / "ADR-0001-centralized-postgresql-authority.md"
    ).read_text(encoding="utf-8")

    assert "PostgreSQL" in text
    assert "authoritative" in text.lower()
