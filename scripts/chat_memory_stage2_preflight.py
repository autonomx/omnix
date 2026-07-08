#!/usr/bin/env python3
"""Temporary-store Stage 2 preflight for explicit approved-memory rollout."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_ROOT = _REPO_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from app.assistant_memory import MemoryService, SQLiteMemoryRepository, resolve_chat_scope
from app.chat import ChatMessage, ChatSessionStore, CreateChatSessionRequest
from app.chat.memory_session import RefreshSessionMemoryRequest, refresh_session_memory

_STAGE_FLAGS = {
    "OMNIX_CHAT_SQLITE_STORE_ENABLED": "1",
    "OMNIX_CHAT_MEMORY_ENABLED": "1",
    "OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED": "0",
    "OMNIX_CHAT_HISTORY_RECALL_ENABLED": "0",
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
    saved = {name: os.environ.get(name) for name in [*_STAGE_FLAGS, "OMNIX_CHAT_MEMORY_SETTINGS_PATH"]}
    try:
        for name, value in _STAGE_FLAGS.items():
            os.environ[name] = value
        os.environ["OMNIX_CHAT_MEMORY_SETTINGS_PATH"] = str(temp_dir / "memory-settings.json")
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


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
        report["warnings"].append("SQLite Chat storage is not currently enabled; Stage 2 assumes Stage 1 is complete")
    if _enabled(os.environ.get("OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED")):
        report["warnings"].append("suggestions are enabled; Stage 2 should keep them disabled")
    if _enabled(os.environ.get("OMNIX_CHAT_HISTORY_RECALL_ENABLED")):
        report["warnings"].append("history recall is enabled; Stage 2 should keep it disabled")
    if _enabled(os.environ.get("OMNIX_CHAT_COMPACTION_ENABLED")):
        report["warnings"].append("compaction is enabled; Stage 2 should keep it disabled")
    if _enabled(os.environ.get("OMNIX_HERMES_MEMORY_SYNC_ENABLED")):
        report["warnings"].append("Hermes sync is enabled; Stage 2 should keep it disabled")

    try:
        with tempfile.TemporaryDirectory(prefix="omnix-chat-memory-stage2-") as temp_raw:
            temp_dir = Path(temp_raw)
            with _temporary_stage_environment(temp_dir):
                memory_service = MemoryService(SQLiteMemoryRepository(temp_dir / "memory.sqlite3"))
                chat_store = ChatSessionStore(
                    temp_dir / "chat.json",
                    memory_service_factory=lambda: memory_service,
                )
                session = chat_store.create_session(CreateChatSessionRequest(title="Stage 2 explicit memory"))
                context = resolve_chat_scope(
                    session.id,
                    profile_id=session.profile_id,
                    workspace_id=session.workspace_id,
                    project_id=session.project_id,
                )
                record = memory_service.create_explicit_memory(
                    context,
                    scope="session",
                    category="instruction",
                    content="Use exact-head CI as verification truth.",
                    provenance_id="stage2-preflight",
                )
                snapshot_state = refresh_session_memory(
                    chat_store,
                    memory_service,
                    session.id,
                    RefreshSessionMemoryRequest(token_budget=4_000),
                )
                refreshed_session = chat_store.get_session(session.id)
                if refreshed_session is None:
                    raise RuntimeError("refreshed session missing")
                user_message = ChatMessage(
                    id="msg:stage2-current",
                    role="user",
                    content="Continue the rollout.",
                    created_at="2026-07-08T00:00:00+00:00",
                )
                assembly, rendered = chat_store.build_provider_prompt(refreshed_session, user_message, [])
                rendered_text = "\n".join(message.content for message in rendered.messages)
                selected_ids = assembly.diagnostics.get("memory", {}).get("selected_memory_ids", [])
                candidates_before_forget = memory_service.repository.list_candidates(status="pending")
                memory_service.forget_memory(context, record.id, expected_revision=record.revision)
                after_forget_session = chat_store.get_session(session.id)
                if after_forget_session is None:
                    raise RuntimeError("session missing after forget")
                after_forget, after_rendered = chat_store.build_provider_prompt(after_forget_session, user_message, [])
                after_text = "\n".join(message.content for message in after_rendered.messages)
                report["rehearsal"] = {
                    "chat_store_path": str(temp_dir / "chat.json"),
                    "memory_db_path": str(temp_dir / "memory.sqlite3"),
                    "saved_memory_id": record.id,
                    "snapshot_revision": snapshot_state.snapshot_revision if snapshot_state else None,
                    "snapshot_record_count": snapshot_state.memory_record_count if snapshot_state else 0,
                    "selected_memory_ids": selected_ids,
                    "pending_candidate_count": len(candidates_before_forget),
                    "memory_present_in_prompt": record.content in rendered_text,
                    "memory_present_after_forget": record.content in after_text,
                    "selected_count_after_forget": after_forget.diagnostics.get("memory", {}).get("selected_memory_count", 0),
                }
                if selected_ids != [record.id]:
                    report["errors"].append("approved explicit memory was not selected for prompt assembly")
                if record.content not in rendered_text:
                    report["errors"].append("approved explicit memory was not rendered into the prompt")
                if candidates_before_forget:
                    report["errors"].append("pending candidates were created during explicit-memory preflight")
                if record.content in after_text:
                    report["errors"].append("forgotten memory remained in prompt assembly")
                if after_forget.diagnostics.get("memory", {}).get("selected_memory_count") != 0:
                    report["errors"].append("forgotten memory remained selected after forget")
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
