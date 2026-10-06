"""scripts/retire_module.py refusals and tombstone (PA-4.3); the recipe test retires a module for real."""
from __future__ import annotations

import types

from pydantic import BaseModel, ConfigDict

from app.persistence.declarations import SettingsSection
from app.runtime import feature_catalog
from app.runtime.config import RuntimeConfig
from scripts import retire_module, table_ownership


class _NotesSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    greeting: str = "Hello"


def _tombstone(described: dict) -> types.ModuleType:
    module = types.ModuleType("tombstone")
    exec(compile(retire_module.tombstone_source("field-notes", described, "2026-10-05"), "tombstone.py", "exec"),
         module.__dict__)
    return module


def test_the_tombstone_keeps_job_types_consumers_tools_and_stored_settings() -> None:
    described = {
        "job_types": ("field_notes.note",), "consumers": (("field-notes.items", ("item",), "item.*"),),
        "tool_ids": ("field-notes",), "capability_ids": ("field_notes.read",),
        "settings": (SettingsSection("field_notes", _NotesSettings, order=50, alias="fieldNotes"),),
    }

    tombstone = _tombstone(described)

    assert tombstone.MODULE_ID == "field-notes"
    assert tombstone.JOB_TYPES == ("field_notes.note",)
    assert tombstone.OUTBOX_CONSUMERS == (("field-notes.items", ("item",), "item.*"),)
    assert (tombstone.TOOL_IDS, tombstone.CAPABILITY_IDS) == (("field-notes",), ("field_notes.read",))
    (section,) = tombstone.SETTINGS
    assert (section.field, section.order, section.alias) == ("field_notes", 50, "fieldNotes")
    assert section.model.model_validate({"greeting": "Hi", "later": 1}).model_dump() == {"greeting": "Hi", "later": 1}


def test_a_module_without_settings_gets_a_tombstone_without_them() -> None:
    described = {"job_types": (), "consumers": (), "tool_ids": (), "capability_ids": (), "settings": ()}

    tombstone = _tombstone(described)

    assert not hasattr(tombstone, "SETTINGS") and tombstone.OUTBOX_CONSUMERS == ()


def test_a_module_others_need_is_refused(capsys) -> None:
    assert retire_module.main(["image", "--files-only", "--no-generate"]) == 2

    error = capsys.readouterr().err
    assert "catalog module characters depends on it" in error
    assert "web feature image-generation lists it in backendModules" in error


def test_an_unknown_module_is_refused(capsys) -> None:
    assert retire_module.main(["no-such-module", "--files-only"]) == 2
    assert "is not a catalog module" in capsys.readouterr().err


def test_a_retired_module_owns_its_tables_as_retired() -> None:
    sources = {"src/app/persistence/retired/field_notes/tombstone.py": 'MODULE_ID = "field-notes"\n'}

    assert table_ownership.retired_owner("src/app/persistence/retired/field_notes/migrations/0200_x.sql", sources) == (
        "retired:field-notes"
    )
    assert table_ownership.retired_owner("src/app/field_notes/migrations/0200_x.sql", sources) is None


def test_a_configuration_naming_a_retired_module_still_starts(monkeypatch) -> None:
    monkeypatch.setattr(feature_catalog, "retired_module_ids", lambda: frozenset({"field-notes"}))

    selected = feature_catalog.enabled_feature_ids(RuntimeConfig(enabled_features=("chat", "field-notes"),
                                                                 disabled_features=("field-notes",)))

    assert selected == ("chat",)
