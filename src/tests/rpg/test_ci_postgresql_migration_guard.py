from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = REPO_ROOT / "src" / "app"

# The only SQLite connection allowed anywhere under the application package is
# the explicit one-shot legacy extractor. Runtime modules must have zero sites.
LEGACY_SQLITE_CONNECTION_FILES = {
    "src/app/persistence/legacy_export.py",
}

# These are known legacy JSON/JSONL authorities. They remain migration inputs
# until the final retirement checkpoint removes or converts each module.
LEGACY_MUTABLE_JSON_STORE_FILES = {
    "src/app/assets/store.py",
    "src/app/assist_core/policy_store.py",
    "src/app/assistant_tools/config_store.py",
    "src/app/chat/prompt_store.py",
    "src/app/chat/store.py",
    "src/app/gateway/live_chat_evaluation_store.py",
    "src/app/image/asset_store.py",
    "src/app/research/source_store.py",
    "src/app/rpg/npc_evolution/profile_store.py",
    "src/app/rpg/session/durable_store.py",
    "src/app/rpg/session/interaction_event_store.py",
}


def _relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _python_files() -> list[Path]:
    return sorted(path for path in APP_ROOT.rglob("*.py") if path.is_file())


def _sqlite_connect_call(node: ast.Call) -> bool:
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "connect"
        and isinstance(func.value, ast.Name)
        and func.value.id == "sqlite3"
    )


def _has_sqlite_connection(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return any(isinstance(node, ast.Call) and _sqlite_connect_call(node) for node in ast.walk(tree))


def _looks_like_mutable_json_store(path: Path) -> bool:
    if not path.name.endswith(("store.py", "repository.py", "persistence.py")):
        return False
    source = path.read_text(encoding="utf-8")
    has_json = "json.dump" in source or "json.dumps" in source or ".json" in source or ".jsonl" in source
    has_write = any(token in source for token in ("write_text(", "writelines(", "os.write(", "open(\"w", "open('w"))
    return has_json and has_write


def test_no_new_sqlite_runtime_connection_sites() -> None:
    actual = {_relative(path) for path in _python_files() if _has_sqlite_connection(path)}
    assert actual == LEGACY_SQLITE_CONNECTION_FILES, (
        "SQLite is retired from runtime. Only the one-shot legacy extractor may "
        f"open it. actual={sorted(actual)}"
    )


def test_no_new_mutable_json_store_files() -> None:
    actual = {_relative(path) for path in _python_files() if _looks_like_mutable_json_store(path)}
    unexpected = sorted(actual - LEGACY_MUTABLE_JSON_STORE_FILES)
    assert unexpected == [], (
        "New mutable JSON/JSONL runtime stores are forbidden. Use PostgreSQL "
        f"metadata and BlobStore content instead: {unexpected}"
    )
