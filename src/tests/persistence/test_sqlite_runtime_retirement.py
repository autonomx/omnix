from __future__ import annotations

import ast
from pathlib import Path

from app.persistence.legacy_authority_block import RETIRED_MUTABLE_AUTHORITY_MODULES
from app.persistence.runtime import PersistenceMode


ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = ROOT / "src" / "app"

LEGACY_SQLITE_ADAPTER_FILES = {
    "assistant_memory/repository.py",
    "characters/avatar_generation_repository.py",
    "characters/avatar_repository.py",
    "characters/avatar_viseme_generation.py",
    "characters/repository.py",
    "chat/compaction.py",
    "chat/history_search.py",
    "chat/repository.py",
    "jobs/residency.py",
    "jobs/rpg_foreground_submission_store.py",
    "jobs/store.py",
    "providers/cache_status.py",
    "research/cache.py",
    "rpg/narrative/narrative_persistence.py",
}

EXPECTED_RETIRED_MUTABLE_MODULES = {
    "app.assist_core.policy_store",
    "app.assistant_tools.config_store",
    "app.chat.prompt_store",
    "app.gateway.live_chat_evaluation_store",
    "app.image.asset_store",
    "app.research.source_store",
    "app.rpg.narrative.narrative_persistence",
    "app.rpg.npc_evolution.profile_store",
}


def _sqlite_connect_sites() -> set[str]:
    sites: set[str] = set()
    for path in APP_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            if (
                isinstance(function, ast.Attribute)
                and isinstance(function.value, ast.Name)
                and function.value.id == "sqlite3"
                and function.attr == "connect"
            ):
                sites.add(path.relative_to(APP_ROOT).as_posix())
    return sites


def test_sqlite_connections_are_confined_to_frozen_legacy_adapters() -> None:
    assert _sqlite_connect_sites() == LEGACY_SQLITE_ADAPTER_FILES


def test_postgresql_runtime_modules_do_not_import_sqlite() -> None:
    persistence_root = APP_ROOT / "persistence"
    offenders: list[str] = []
    for path in persistence_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if path.name == "runtime_install.py":
            # runtime_install imports sqlite3 only to replace connect with a fail-closed sentinel.
            continue
        if "import sqlite3" in text or "from sqlite3" in text:
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []


def test_production_default_is_postgresql_only() -> None:
    runtime_text = (APP_ROOT / "persistence" / "runtime.py").read_text(encoding="utf-8")
    sitecustomize = (ROOT / "src" / "sitecustomize.py").read_text(encoding="utf-8")
    installer = (APP_ROOT / "persistence" / "runtime_install.py").read_text(encoding="utf-8")

    assert PersistenceMode.POSTGRESQL.value == "postgresql"
    assert 'or "postgresql"' in runtime_text
    assert "install_postgresql_runtime_adapters" in sitecustomize
    assert "sqlite3.connect = _retired_sqlite_connect" in installer
    assert "PostgresChatRepositoryAdapter" in installer
    assert "PostgresMemoryRepositoryAdapter" in installer
    assert "PostgresCharacterRepositoryAdapter" in installer
    assert "PostgresJobStoreAdapter" in installer
    assert "PostgresSharedAssetStoreAdapter" in installer
    assert "save_session_to_postgres" in installer


def test_mutable_json_authorities_are_import_blocked() -> None:
    assert set(RETIRED_MUTABLE_AUTHORITY_MODULES) == EXPECTED_RETIRED_MUTABLE_MODULES
    barrier = (APP_ROOT / "persistence" / "legacy_authority_block.py").read_text(
        encoding="utf-8"
    )
    usercustomize = (ROOT / "src" / "usercustomize.py").read_text(encoding="utf-8")
    assert "RetiredMutableAuthority" in barrier
    assert "install_legacy_authority_block" in usercustomize


def test_legacy_access_is_explicitly_limited_to_test_or_import() -> None:
    runtime_text = (APP_ROOT / "persistence" / "runtime.py").read_text(encoding="utf-8")
    assert "OMNIX_ALLOW_LEGACY_TEST_PERSISTENCE" in runtime_text
    assert "OMNIX_ALLOW_LEGACY_IMPORT" in runtime_text
    assert "legacy_test persistence is restricted" in runtime_text
    assert "legacy_import persistence requires" in runtime_text
