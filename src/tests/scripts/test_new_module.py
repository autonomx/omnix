"""scripts/new_module.py names and validation (PA-4.2); the recipe test scaffolds for real."""
from __future__ import annotations

import pytest

from scripts import new_module


def test_names_follow_the_module_id() -> None:
    assert new_module.names("field-notes") == {
        "id": "field-notes", "pkg": "field_notes", "title": "Field Notes", "pascal": "FieldNotes", "camel": "fieldNotes",
    }


@pytest.mark.parametrize("module_id", ["Field", "field_notes", "-field", "field--notes", "1field"])
def test_a_malformed_id_is_refused(module_id: str) -> None:
    with pytest.raises(new_module.ScaffoldError, match="lowercase words"):
        new_module.scaffold(module_id, tier="app", web=False)


def test_an_existing_module_is_refused() -> None:
    with pytest.raises(new_module.ScaffoldError, match="already exists"):
        new_module.scaffold("trading", tier="app", web=False)


def test_the_migration_version_follows_every_known_migration() -> None:
    from app.persistence.migrations import discover_migrations

    newest = int(discover_migrations()[-1].version.split("_", 1)[0])

    assert new_module.next_migration_version() > newest
