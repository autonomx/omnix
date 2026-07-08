#!/usr/bin/env python3
"""Read-only Stage 1 preflight for enabling SQLite-backed Chat storage."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_ROOT = _REPO_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from app.chat.json_import import import_legacy_chat_json
from app.chat.repository import SQLiteChatRepository, default_chat_db_path
from app.chat.store import default_chat_store_path

_MEMORY_FLAGS = [
    "OMNIX_CHAT_SQLITE_STORE_ENABLED",
    "OMNIX_CHAT_MEMORY_ENABLED",
    "OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED",
    "OMNIX_CHAT_HISTORY_RECALL_ENABLED",
    "OMNIX_CHAT_COMPACTION_ENABLED",
    "OMNIX_HERMES_MEMORY_SYNC_ENABLED",
]


def _enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _flag_report() -> dict[str, dict[str, Any]]:
    return {
        name: {
            "value": os.environ.get(name),
            "enabled": _enabled(os.environ.get(name)),
        }
        for name in _MEMORY_FLAGS
    }


def _legacy_summary(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "path": str(path),
            "exists": False,
            "bytes": 0,
            "sessions_in_json": 0,
            "messages_in_json": 0,
        }
    raw = path.read_bytes()
    sessions = 0
    messages = 0
    try:
        payload = json.loads(raw.decode("utf-8"))
        raw_sessions = payload.get("sessions", []) if isinstance(payload, dict) else []
        if isinstance(raw_sessions, list):
            sessions = len(raw_sessions)
            messages = sum(
                len(item.get("messages", []))
                for item in raw_sessions
                if isinstance(item, dict) and isinstance(item.get("messages", []), list)
            )
    except (OSError, ValueError, TypeError):
        pass
    return {
        "path": str(path),
        "exists": True,
        "bytes": len(raw),
        "sessions_in_json": sessions,
        "messages_in_json": messages,
    }


def run_preflight() -> dict[str, Any]:
    legacy_path = default_chat_store_path()
    target_db_path = default_chat_db_path()
    report: dict[str, Any] = {
        "ok": False,
        "legacy_json": _legacy_summary(legacy_path),
        "target_sqlite_db": str(target_db_path),
        "flags": _flag_report(),
        "rehearsal": None,
        "warnings": [],
        "errors": [],
    }
    if _enabled(os.environ.get("OMNIX_CHAT_MEMORY_ENABLED")):
        report["warnings"].append("curated memory is enabled; Stage 1 should keep it disabled")
    for name in _MEMORY_FLAGS[2:]:
        if _enabled(os.environ.get(name)):
            report["warnings"].append(f"{name} is enabled; Stage 1 should keep this disabled")

    try:
        with tempfile.TemporaryDirectory(prefix="omnix-chat-sqlite-preflight-") as temp_dir:
            rehearsal_db = Path(temp_dir) / "chat.sqlite3"
            repository = SQLiteChatRepository(rehearsal_db)
            import_state = import_legacy_chat_json(repository, legacy_path)
            session_count, message_count = repository.counts()
            report["rehearsal"] = {
                "db_path": str(rehearsal_db),
                "schema_initialized": True,
                "import_state": import_state.model_dump(mode="json") if import_state else None,
                "sessions_after_import": session_count,
                "messages_after_import": message_count,
            }
            if import_state and import_state.status != "completed":
                report["errors"].append(f"legacy import status was {import_state.status}")
            if report["legacy_json"]["exists"] and import_state is None:
                report["errors"].append("legacy JSON file exists but was not imported")
    except Exception as exc:  # pragma: no cover - surfaced as CLI JSON diagnostics.
        report["errors"].append(f"{type(exc).__name__}: {exc}")

    report["ok"] = not report["errors"]
    return report


def main() -> int:
    report = run_preflight()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
