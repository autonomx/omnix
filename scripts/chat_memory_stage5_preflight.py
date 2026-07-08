#!/usr/bin/env python3
"""Temporary-store Stage 5 preflight for long-session compaction."""
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

from app.assistant_memory import MemoryService, SQLiteMemoryRepository
from app.chat import ChatMessage, ChatSession
from app.chat.compaction import (
    DEFAULT_RECENT_MESSAGE_LIMIT,
    HISTORY_COMPACT_JOB_TYPE,
    SQLiteConversationSummaryRepository,
    enqueue_compaction_job,
    process_compaction_job,
)
from app.chat.history_search import SQLiteHistorySearchService
from app.chat.repository import SQLiteChatRepository
from app.chat.sqlite_store import SQLiteChatSessionStore
from app.jobs import SQLiteJobStore

_NOW = "2026-07-08T00:00:00+00:00"
_STAGE_FLAGS = {
    "OMNIX_CHAT_SQLITE_STORE_ENABLED": "1",
    "OMNIX_CHAT_MEMORY_ENABLED": "1",
    "OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED": "1",
    "OMNIX_CHAT_HISTORY_RECALL_ENABLED": "1",
    "OMNIX_CHAT_COMPACTION_ENABLED": "1",
    "OMNIX_HERMES_MEMORY_SYNC_ENABLED": "0",
    "OMNIX_CHAT_COMPACTION_THRESHOLD": "40",
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


def _long_session(session_id: str, count: int) -> ChatSession:
    messages = [
        ChatMessage(
            id=f"{session_id}:msg:{index}",
            role="user" if index % 2 == 0 else "assistant",
            content=(
                f"Always preserve rollout decision {index}; next pending checkpoint {index}."
                if index % 10 == 0
                else f"Long-session conversation detail {index}."
            ),
            created_at=_NOW,
        )
        for index in range(count)
    ]
    return ChatSession(
        id=session_id,
        title="Stage 5 long conversation",
        created_at=_NOW,
        updated_at=_NOW,
        message_count=len(messages),
        messages=messages,
    )


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
            "SQLite Chat storage is not currently enabled; Stage 5 assumes Stage 1 is complete"
        )
    if not _enabled(os.environ.get("OMNIX_CHAT_MEMORY_ENABLED")):
        report["warnings"].append(
            "curated memory is not currently enabled; Stage 5 assumes Stage 2 is complete"
        )
    if not _enabled(os.environ.get("OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED")):
        report["warnings"].append(
            "memory suggestions are not currently enabled; Stage 5 assumes Stage 3 is complete"
        )
    if not _enabled(os.environ.get("OMNIX_CHAT_HISTORY_RECALL_ENABLED")):
        report["warnings"].append(
            "history recall is not currently enabled; Stage 5 assumes Stage 4 is complete"
        )
    if _enabled(os.environ.get("OMNIX_HERMES_MEMORY_SYNC_ENABLED")):
        report["warnings"].append(
            "Hermes sync is enabled; Stage 5 should keep it disabled"
        )

    try:
        with tempfile.TemporaryDirectory(
            prefix="omnix-chat-memory-stage5-"
        ) as temp_raw:
            temp_dir = Path(temp_raw)
            with _temporary_stage_environment(temp_dir):
                chat_db = temp_dir / "chat.sqlite3"
                memory_db = temp_dir / "memory.sqlite3"
                job_db = temp_dir / "jobs.sqlite3"
                repository = SQLiteChatRepository(chat_db)
                memory_service = MemoryService(SQLiteMemoryRepository(memory_db))
                summary_repository = SQLiteConversationSummaryRepository(chat_db)
                history_service = SQLiteHistorySearchService(chat_db)
                job_store = SQLiteJobStore(job_db)
                store = SQLiteChatSessionStore(
                    chat_db,
                    import_legacy=False,
                    memory_service_factory=lambda: memory_service,
                    history_search_factory=lambda: history_service,
                    summary_repository_factory=lambda: summary_repository,
                )

                short_session = _long_session("chat:short", 39)
                long_session = _long_session("chat:long", 60)
                repository.save_sessions([short_session, long_session])

                below_threshold_job = enqueue_compaction_job(
                    short_session,
                    job_store=job_store,
                )
                first_job = enqueue_compaction_job(
                    long_session,
                    job_store=job_store,
                )
                retry_job = enqueue_compaction_job(
                    long_session,
                    job_store=job_store,
                )
                if first_job is None or retry_job is None:
                    raise RuntimeError(
                        "long session did not enqueue a Stage 5 compaction job"
                    )

                current_message = ChatMessage(
                    id="msg:stage5-current",
                    role="user",
                    content="Continue the rollout checkpoint.",
                    created_at=_NOW,
                )
                pending_assembly, pending_rendered = store.build_provider_prompt(
                    long_session,
                    current_message,
                    [],
                )
                pending_text = "\n".join(
                    item.content for item in pending_rendered.messages
                )

                summary = process_compaction_job(
                    first_job,
                    chat_store=store,
                    summary_repository=summary_repository,
                    job_store=job_store,
                )
                if summary is None:
                    raise RuntimeError("compaction job did not persist a summary")

                completed_job = job_store.get_job(first_job.id)
                compacted_assembly, compacted_rendered = store.build_provider_prompt(
                    long_session,
                    current_message,
                    [],
                )
                compacted_text = "\n".join(
                    item.content for item in compacted_rendered.messages
                )

                os.environ["OMNIX_CHAT_COMPACTION_ENABLED"] = "0"
                disabled_assembly, disabled_rendered = store.build_provider_prompt(
                    long_session,
                    current_message,
                    [],
                )
                disabled_text = "\n".join(
                    item.content for item in disabled_rendered.messages
                )
                os.environ["OMNIX_CHAT_COMPACTION_ENABLED"] = "1"

                expected_through_id = (
                    f"{long_session.id}:msg:"
                    f"{len(long_session.messages) - DEFAULT_RECENT_MESSAGE_LIMIT - 1}"
                )
                expected_first_recent_id = (
                    f"{long_session.id}:msg:"
                    f"{len(long_session.messages) - DEFAULT_RECENT_MESSAGE_LIMIT}"
                )
                latest_summary = summary_repository.latest(long_session.id)

                report["rehearsal"] = {
                    "chat_db_path": str(chat_db),
                    "memory_db_path": str(memory_db),
                    "job_db_path": str(job_db),
                    "below_threshold_job_created": below_threshold_job is not None,
                    "job_id": first_job.id,
                    "retry_job_id": retry_job.id,
                    "job_type": first_job.type,
                    "job_count": len(job_store.list_jobs()),
                    "job_through_message_id": first_job.input_payload.get(
                        "through_message_id"
                    ),
                    "expected_through_message_id": expected_through_id,
                    "pending_summary_id": pending_assembly.diagnostics[
                        "compaction"
                    ].get("summary_id"),
                    "pending_recent_message_count": len(
                        pending_assembly.recent_messages
                    ),
                    "pending_prompt_has_oldest_message": (
                        "rollout decision 0" in pending_text
                    ),
                    "summary_id": summary.id,
                    "summary_revision": summary.revision,
                    "summary_through_message_id": summary.through_message_id,
                    "summary_source_message_count": summary.source_message_count,
                    "summary_has_durable_decisions": bool(
                        summary.durable_decisions
                    ),
                    "summary_has_unresolved_items": bool(
                        summary.unresolved_items
                    ),
                    "latest_summary_id": (
                        latest_summary.id if latest_summary else None
                    ),
                    "completed_job_status": (
                        completed_job.status if completed_job else None
                    ),
                    "completed_job_output_refs": (
                        completed_job.output_refs if completed_job else []
                    ),
                    "compacted_summary_id": compacted_assembly.diagnostics[
                        "compaction"
                    ].get("summary_id"),
                    "compacted_recent_message_count": len(
                        compacted_assembly.recent_messages
                    ),
                    "compacted_first_recent_message_id": (
                        compacted_assembly.recent_messages[0].message_id
                        if compacted_assembly.recent_messages
                        else None
                    ),
                    "expected_first_recent_message_id": expected_first_recent_id,
                    "compacted_prompt_has_summary": "Session summary:" in compacted_text,
                    "compacted_prompt_has_recent_tail": (
                        "Long-session conversation detail 59" in compacted_text
                    ),
                    "compacted_prompt_has_oldest_message": (
                        "rollout decision 0" in compacted_text
                    ),
                    "disabled_compaction_diagnostics": disabled_assembly.diagnostics[
                        "compaction"
                    ],
                    "disabled_recent_message_count": len(
                        disabled_assembly.recent_messages
                    ),
                    "disabled_prompt_has_summary": "Session summary:" in disabled_text,
                    "disabled_prompt_has_oldest_message": (
                        "rollout decision 0" in disabled_text
                    ),
                }

                if below_threshold_job is not None:
                    report["errors"].append(
                        "session below the threshold created a compaction job"
                    )
                if first_job.id != retry_job.id:
                    report["errors"].append(
                        "compaction enqueue retry created a duplicate job"
                    )
                if first_job.type != HISTORY_COMPACT_JOB_TYPE:
                    report["errors"].append(
                        "compaction job used the wrong durable job type"
                    )
                if len(job_store.list_jobs()) != 1:
                    report["errors"].append(
                        "compaction rehearsal created an unexpected number of jobs"
                    )
                if first_job.input_payload.get("through_message_id") != expected_through_id:
                    report["errors"].append(
                        "compaction job used the wrong through-message boundary"
                    )
                if pending_assembly.session_summary is not None:
                    report["errors"].append(
                        "pending compaction silently introduced a session summary"
                    )
                if len(pending_assembly.recent_messages) != len(long_session.messages):
                    report["errors"].append(
                        "pending compaction dropped current-session history"
                    )
                if "rollout decision 0" not in pending_text:
                    report["errors"].append(
                        "pending compaction prompt omitted the oldest conversation context"
                    )
                if summary.through_message_id != expected_through_id:
                    report["errors"].append(
                        "persisted summary used the wrong through-message boundary"
                    )
                if summary.source_message_count != (
                    len(long_session.messages) - DEFAULT_RECENT_MESSAGE_LIMIT
                ):
                    report["errors"].append(
                        "persisted summary used the wrong source-message count"
                    )
                if not summary.durable_decisions or not summary.unresolved_items:
                    report["errors"].append(
                        "deterministic summary did not preserve decisions and unresolved items"
                    )
                if latest_summary is None or latest_summary.id != summary.id:
                    report["errors"].append(
                        "persisted summary was not available as the latest session summary"
                    )
                if completed_job is None or completed_job.status != "completed":
                    report["errors"].append(
                        "compaction job was not marked completed"
                    )
                if completed_job and completed_job.output_refs != [
                    {"type": "conversation_summary", "id": summary.id}
                ]:
                    report["errors"].append(
                        "compaction job did not reference the persisted summary"
                    )
                if compacted_assembly.session_summary != summary.summary:
                    report["errors"].append(
                        "prompt assembly did not use the persisted summary"
                    )
                if len(compacted_assembly.recent_messages) != DEFAULT_RECENT_MESSAGE_LIMIT:
                    report["errors"].append(
                        "compacted prompt did not retain the configured recent-message window"
                    )
                if (
                    not compacted_assembly.recent_messages
                    or compacted_assembly.recent_messages[0].message_id
                    != expected_first_recent_id
                ):
                    report["errors"].append(
                        "compacted prompt used the wrong recent-message boundary"
                    )
                if "Session summary:" not in compacted_text:
                    report["errors"].append(
                        "persisted summary was not rendered into the prompt"
                    )
                if "Long-session conversation detail 59" not in compacted_text:
                    report["errors"].append(
                        "compacted prompt omitted the latest conversation tail"
                    )
                if "rollout decision 0" in compacted_text:
                    report["errors"].append(
                        "compacted prompt retained old raw history outside the summary"
                    )
                if disabled_assembly.diagnostics["compaction"] != {
                    "enabled": False,
                    "summary_id": None,
                }:
                    report["errors"].append(
                        "disabling compaction did not restore disabled diagnostics"
                    )
                if len(disabled_assembly.recent_messages) != len(long_session.messages):
                    report["errors"].append(
                        "disabled compaction did not restore the complete transcript"
                    )
                if "Session summary:" in disabled_text:
                    report["errors"].append(
                        "disabled compaction still rendered a session summary"
                    )
                if "rollout decision 0" not in disabled_text:
                    report["errors"].append(
                        "disabled compaction did not restore the oldest conversation context"
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
