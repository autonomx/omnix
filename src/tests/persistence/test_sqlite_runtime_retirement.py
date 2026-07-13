from __future__ import annotations

import ast
from pathlib import Path

from app.persistence.legacy_authority_block import (
    RETIRED_MUTABLE_AUTHORITY_MODULES,
    install_legacy_authority_block,
)
from app.persistence.runtime import PersistenceMode


ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = ROOT / "src" / "app"

# Runtime has zero SQLite connection sites. The one-shot migration extractor is
# the only application module allowed to read a legacy SQLite file.
LEGACY_SQLITE_ADAPTER_FILES = {
    "persistence/legacy_export.py",
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


def test_sqlite_connections_exist_only_in_one_shot_legacy_extractor() -> None:
    assert _sqlite_connect_sites() == LEGACY_SQLITE_ADAPTER_FILES


def test_postgresql_runtime_modules_do_not_open_sqlite() -> None:
    persistence_root = APP_ROOT / "persistence"
    offenders: list[str] = []
    for path in persistence_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if path.name in {"runtime_install.py", "legacy_export.py"}:
            continue
        if "import sqlite3" in text or "from sqlite3" in text:
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []


def test_application_startup_is_explicit_and_postgresql_only() -> None:
    startup = (APP_ROOT / "persistence" / "startup.py").read_text(encoding="utf-8")
    launcher = (ROOT / "scripts" / "run_omnix_gateway.py").read_text(encoding="utf-8")
    usercustomize = (ROOT / "src" / "usercustomize.py").read_text(encoding="utf-8")
    installer = (APP_ROOT / "persistence" / "runtime_install.py").read_text(encoding="utf-8")

    assert PersistenceMode.POSTGRESQL.value == "postgresql"
    assert "bootstrap_postgresql_runtime" in startup
    assert "install_postgresql_runtime_adapters" in startup
    assert "bootstrap_status_payload" in launcher
    assert "install_legacy_authority_block" not in usercustomize
    assert "sqlite3.connect = _retired_sqlite_connect" in installer


def test_heuristic_import_blocker_is_disabled() -> None:
    assert RETIRED_MUTABLE_AUTHORITY_MODULES == frozenset()
    assert install_legacy_authority_block() is False


def test_legacy_access_is_explicitly_limited_to_test_or_import() -> None:
    runtime_text = (APP_ROOT / "persistence" / "runtime.py").read_text(encoding="utf-8")
    assert "OMNIX_ALLOW_LEGACY_TEST_PERSISTENCE" in runtime_text
    assert "OMNIX_ALLOW_LEGACY_IMPORT" in runtime_text
    assert "legacy_test persistence is restricted" in runtime_text
    assert "legacy_import persistence requires" in runtime_text
