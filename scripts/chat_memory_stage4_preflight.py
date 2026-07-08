#!/usr/bin/env python3
"""Temporary-store Stage 4 preflight for scoped historical Chat recall."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_ROOT = _REPO_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from app.assistant_memory import MemoryService, SQLiteMemoryRepository
from app.chat import ChatMessage, ChatSession
from app.chat.history_search import SQLiteHistorySearchService
from app.chat.repository import SQLiteChatRepository
from app.chat.sqlite_store import SQLiteChatSessionStore

_NOW = "2026-07-08T00:00:00+00:00"
_STAGE_FLAGS = {
    "OMNIX_CHAT_SQLITE_STORE_ENABLED": "1",
    "OMNIX_CHAT_MEMORY_ENABLED": "1",
    "OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED": "1",
    "OMNIX_CHAT_HISTORY_RECALL_ENABLED": "1",
    "OMNIX_CHAT_COMPACTION_ENABLED": "0",
    "OMNIX_HERMES_MEMORY_SYNC_ENABLED": "0",
}


def _enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _flag_report() -> dict[str, dict[str, Any]]:
    return {
        name: {"value": os.environ.get(name), "enabled": _enabled(os.environ.get(name))}
        for name in _STAGE_FLAGS
    }


@contextmanager
def _temporary_stage_environment(temp_dir: Path) -> Iterator[None]:
    names = [*_STAGE_FLAGS, "OMNIX_CHAT_MEMORY_SETTINGS_PATH"]
    saved = {name: os.environ.get(name) for name in names}
    try:
        for name, value in _STAGE_FLAGS.items():
            os.environ[name] = value
        os.environ["OMNIX_CHAT_MEMORY_SETTINGS_PATH"] = str(
            temp_dir / "memory-settings.json"
        )
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _session(
    session_id: str,
    content: str,
    *,
    profile_id: str = "profile:local",
    workspace_id: str = "workspace:default",
    project_id: str | None = "project:omnix",
) -> ChatSession:
    messages = [
        ChatMessage(
            id=f"{session_id}:user",
            role="user",
            content=content,
            created_at=_NOW,
        ),
        ChatMessage(
            id=f"{session_id}:assistant",
            role="assistant",
            content=f"Prior answer about {content}",
            created_at=_NOW,
        ),
    ]
    return ChatSession(
        id=session_id,
        title=session_id,
        profile_id=profile_id,
        workspace_id=workspace_id,
        project_id=project_id,
        created_at=_NOW,
        updated_at=_NOW,
        message_count=len(messages),
        messages=messages,
    )


class _UnavailableHistorySearch(SQLiteHistorySearchService):
    def _connect(self):
        raise sqlite3.OperationalError("no such module: fts5")


def run_preflight() -> dict[str, Any]:
    report: dict[str, Any] = {
        "ok": False,
        "original_flags": _flag_report(),
        "stage_flags": dict(_STAGE_FLAGS),
        "rehearsal": None,
        "warnings": [],
        "errors": [],
    }
    if not _enabled(os.environ.get("OMNIX_CHAT_SQLITE_STORE_ENABLED")):
        report["warnings"].append(
            "SQLite Chat storage is not currently enabled; Stage 4 assumes Stage 1 is complete"
        )
    if not _enabled(os.environ.get("OMNIX_CHAT_MEMORY_ENABLED")):
        report["warnings"].append(
            "curated memory is not currently enabled; Stage 4 assumes Stage 2 is complete"
        )
    if not _enabled(os.environ.get("OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED")):
        report["warnings"].append(
            "memory suggestions are not currently enabled; Stage 4 assumes Stage 3 is complete"
        )
    if _enabled(os.environ.get("OMNIX_CHAT_COMPACTION_ENABLED")):
        report["warnings"].append(
            "compaction is enabled; Stage 4 should keep it disabled"
        )
    if _enabled(os.environ.get("OMNIX_HERMES_MEMORY_SYNC_ENABLED")):
        report["warnings"].append(
            "Hermes sync is enabled; Stage 4 should keep it disabled"
        )

    try:
        with tempfile.TemporaryDirectory(
            prefix="omnix-chat-memory-stage4-"
        ) as temp_raw:
            temp_dir = Path(temp_raw)
            with _temporary_stage_environment(temp_dir):
                chat_db = temp_dir / "chat.sqlite3"
                memory_db = temp_dir / "memory.sqlite3"
                repository = SQLiteChatRepository(chat_db)
                memory_service = MemoryService(SQLiteMemoryRepository(memory_db))

                same_scope = _session(
                    "chat:same-scope",
                    "The audio streaming timeout waited for the complete response.",
                )
                current = _session(
                    "chat:current",
                    "Current-session audio streaming timeout marker.",
                )
                cross_project = _session(
                    "chat:cross-project",
                    "CLASSIFIED-CROSS-PROJECT audio streaming timeout detail.",
                    project_id="project:other",
                )
                cross_workspace = _session(
                    "chat:cross-workspace",
                    "CLASSIFIED-CROSS-WORKSPACE audio streaming timeout detail.",
                    workspace_id="workspace:other",
                )
                cross_profile = _session(
                    "chat:cross-profile",
                    "CLASSIFIED-CROSS-PROFILE audio streaming timeout detail.",
                    profile_id="profile:other",
                )
                deleted = _session(
                    "chat:deleted",
                    "Obsolete comet recall marker.",
                )
                sessions = [
                    same_scope,
                    current,
                    cross_project,
                    cross_workspace,
                    cross_profile,
                    deleted,
                ]
                repository.save_sessions(sessions)

                history = SQLiteHistorySearchService(chat_db)
                result = history.search(
                    "audio streaming timeout",
                    profile_id=current.profile_id,
                    workspace_id=current.workspace_id,
                    project_id=current.project_id,
                    exclude_session_id=current.id,
                    limit=2,
                )
                retrieved_session_ids = [item.session_id for item in result.items]

                store = SQLiteChatSessionStore(
                    chat_db,
                    import_legacy=False,
                    memory_service_factory=lambda: memory_service,
                    history_search_factory=lambda: history,
                )
                user_message = ChatMessage(
                    id="msg:stage4-current",
                    role="user",
                    content="What was the audio streaming timeout?",
                    created_at=_NOW,
                )
                assembly, rendered = store.build_provider_prompt(
                    current,
                    user_message,
                    [],
                )
                rendered_text = "\n".join(item.content for item in rendered.messages)
                history_diagnostics = assembly.diagnostics["history_recall"]

                before_delete = history.search(
                    "obsolete comet",
                    profile_id=current.profile_id,
                    workspace_id=current.workspace_id,
                    project_id=current.project_id,
                    exclude_session_id=current.id,
                )
                repository.save_sessions(
                    [item for item in sessions if item.id != deleted.id]
                )
                after_delete = history.search(
                    "obsolete comet",
                    profile_id=current.profile_id,
                    workspace_id=current.workspace_id,
                    project_id=current.project_id,
                    exclude_session_id=current.id,
                )

                os.environ["OMNIX_CHAT_HISTORY_RECALL_ENABLED"] = "0"
                disabled, disabled_rendered = store.build_provider_prompt(
                    current,
                    user_message,
                    [],
                )
                disabled_text = "\n".join(
                    item.content for item in disabled_rendered.messages
                )
                os.environ["OMNIX_CHAT_HISTORY_RECALL_ENABLED"] = "1"

                degraded_store = SQLiteChatSessionStore(
                    chat_db,
                    import_legacy=False,
                    memory_service_factory=lambda: memory_service,
                    history_search_factory=lambda: _UnavailableHistorySearch(chat_db),
                )
                degraded, degraded_rendered = degraded_store.build_provider_prompt(
                    current,
                    user_message,
                    [],
                )
                degraded_text = "\n".join(
                    item.content for item in degraded_rendered.messages
                )
                degraded_diagnostics = degraded.diagnostics["history_recall"]

                report["rehearsal"] = {
                    "chat_db_path": str(chat_db),
                    "memory_db_path": str(memory_db),
                    "history_status": result.status.model_dump(mode="json"),
                    "query_terms": result.query_terms,
                    "retrieved_session_ids": retrieved_session_ids,
                    "retrieved_message_ids": [item.message_id for item in result.items],
                    "retrieved_count": len(result.items),
                    "prompt_history_diagnostics": history_diagnostics,
                    "prompt_has_history_label": (
                        "Relevant excerpts retrieved from earlier conversations"
                        in rendered_text
                    ),
                    "prompt_has_same_scope_excerpt": (
                        "waited for the complete response" in rendered_text
                    ),
                    "prompt_has_approved_memory_label": (
                        "Approved remembered context follows" in rendered_text
                    ),
                    "deleted_match_count_before": len(before_delete.items),
                    "deleted_match_count_after": len(after_delete.items),
                    "disabled_history_diagnostics": disabled.diagnostics[
                        "history_recall"
                    ],
                    "disabled_prompt_has_history_label": (
                        "Relevant excerpts retrieved from earlier conversations"
                        in disabled_text
                    ),
                    "degraded_history_diagnostics": degraded_diagnostics,
                    "degraded_prompt_has_history_label": (
                        "Relevant excerpts retrieved from earlier conversations"
                        in degraded_text
                    ),
                }

                if not result.status.available:
                    report["errors"].append(
                        f"FTS5 history search unavailable: {result.status.reason}"
                    )
                if set(retrieved_session_ids) != {same_scope.id}:
                    report["errors"].append(
                        "history search did not return only the earlier same-scope session"
                    )
                if current.id in retrieved_session_ids:
                    report["errors"].append(
                        "active session was returned as historical context"
                    )
                if len(result.items) > 2:
                    report["errors"].append("history search exceeded its result limit")
                if history_diagnostics.get("retrieved_count", 0) < 1:
                    report["errors"].append(
                        "prompt assembly did not include same-scope historical context"
                    )
                if "waited for the complete response" not in rendered_text:
                    report["errors"].append(
                        "same-scope historical excerpt was not rendered"
                    )
                if any(
                    marker in rendered_text
                    for marker in (
                        "CLASSIFIED-CROSS-PROJECT",
                        "CLASSIFIED-CROSS-WORKSPACE",
                        "CLASSIFIED-CROSS-PROFILE",
                    )
                ):
                    report["errors"].append(
                        "cross-scope historical content leaked into the prompt"
                    )
                if "Approved remembered context follows" in rendered_text:
                    report["errors"].append(
                        "historical context was rendered as approved memory"
                    )
                if not before_delete.items or after_delete.items:
                    report["errors"].append(
                        "deleted session did not disappear after index synchronization"
                    )
                if disabled.diagnostics["history_recall"] != {
                    "enabled": False,
                    "retrieved_count": 0,
                }:
                    report["errors"].append(
                        "disabling history recall did not restore empty-history behavior"
                    )
                if (
                    "Relevant excerpts retrieved from earlier conversations"
                    in disabled_text
                ):
                    report["errors"].append(
                        "disabled history recall still rendered historical excerpts"
                    )
                if degraded_diagnostics["status"]["available"] is not False:
                    report["errors"].append(
                        "FTS5 failure did not report degraded availability"
                    )
                if degraded_diagnostics.get("retrieved_count") != 0:
                    report["errors"].append(
                        "degraded FTS5 returned historical excerpts"
                    )
                if (
                    "Relevant excerpts retrieved from earlier conversations"
                    in degraded_text
                ):
                    report["errors"].append(
                        "degraded FTS5 rendered a historical section"
                    )
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
