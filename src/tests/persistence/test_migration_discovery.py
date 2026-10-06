"""Migrations are found in the kernel folder and in modules' own folders (PA-2.3)."""
from __future__ import annotations

import pytest

from app.persistence import migrations


def test_schema_known_is_the_newest_discovered_migration():
    assert migrations.SCHEMA_KNOWN == migrations.discover_migrations()[-1].version
    assert migrations.migration_root() in migrations.migration_roots()


def test_versions_must_be_unique_across_folders(tmp_path, monkeypatch):
    kernel, module = tmp_path / "kernel", tmp_path / "module"
    for folder in (kernel, module):
        folder.mkdir()
        (folder / "0001_same.sql").write_text("SELECT 1;\n", encoding="utf-8")
    monkeypatch.setattr(migrations, "migration_roots", lambda: [kernel, module])
    with pytest.raises(migrations.MigrationError, match="0001_same"):
        migrations.discover_migrations()


def test_migrations_from_several_folders_run_in_version_order(tmp_path, monkeypatch):
    kernel, module = tmp_path / "kernel", tmp_path / "module"
    kernel.mkdir()
    module.mkdir()
    (kernel / "0001_first.sql").write_text("SELECT 1;\n", encoding="utf-8")
    (module / "0002_second.sql").write_text("SELECT 2;\n", encoding="utf-8")
    (kernel / "0003_third.sql").write_text("SELECT 3;\n", encoding="utf-8")
    monkeypatch.setattr(migrations, "migration_roots", lambda: [kernel, module])
    assert [item.version for item in migrations.discover_migrations()] == ["0001_first", "0002_second", "0003_third"]
