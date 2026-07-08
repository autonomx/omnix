"""Read-only preflight for enabling the SQLite Chat store.

The preflight imports the legacy JSON store into an isolated temporary SQLite
file, compares source/imported counts, and verifies that the source bytes were
not modified. It never opens the configured production Chat SQLite database.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .json_import import LegacyChatImportError, import_legacy_chat_json
from .repository import SQLiteChatRepository
from .store import default_chat_store_path


class ChatSQLitePreflightReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_path: str
    source_exists: bool
    source_sha256: str | None = None
    status: str
    imported_session_count: int = Field(default=0, ge=0)
    imported_message_count: int = Field(default=0, ge=0)
    sqlite_session_count: int = Field(default=0, ge=0)
    sqlite_message_count: int = Field(default=0, ge=0)
    skipped_session_count: int = Field(default=0, ge=0)
    validation_errors: list[str] = Field(default_factory=list)
    counts_match: bool = False
    source_preserved: bool = True
    production_database_touched: bool = False
    ready: bool = False
    generated_at: str


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def run_chat_sqlite_preflight(
    source_path: str | Path | None = None,
) -> ChatSQLitePreflightReport:
    """Validate a legacy JSON migration using only an isolated temporary DB."""

    source = Path(source_path) if source_path is not None else default_chat_store_path()
    resolved_source = str(source.resolve())
    if not source.is_file():
        return ChatSQLitePreflightReport(
            source_path=resolved_source,
            source_exists=False,
            status="no_legacy_store",
            counts_match=True,
            source_preserved=True,
            production_database_touched=False,
            ready=True,
            generated_at=_utcnow(),
        )

    before = source.read_bytes()
    digest = _sha256(before)
    with tempfile.TemporaryDirectory(prefix="omnix-chat-preflight-") as temporary:
        repository = SQLiteChatRepository(Path(temporary) / "preflight.sqlite3")
        try:
            state = import_legacy_chat_json(repository, source)
        except LegacyChatImportError as exc:
            after = source.read_bytes() if source.is_file() else b""
            return ChatSQLitePreflightReport(
                source_path=resolved_source,
                source_exists=True,
                source_sha256=digest,
                status="validation_failed",
                validation_errors=[str(exc)],
                counts_match=False,
                source_preserved=after == before,
                production_database_touched=False,
                ready=False,
                generated_at=_utcnow(),
            )

        sqlite_sessions, sqlite_messages = repository.counts()
        imported_sessions = state.imported_session_count if state is not None else 0
        imported_messages = state.imported_message_count if state is not None else 0
        skipped = state.skipped_session_count if state is not None else 0
        errors = list(state.errors) if state is not None else []
        after = source.read_bytes() if source.is_file() else b""
        source_preserved = after == before
        counts_match = (
            imported_sessions == sqlite_sessions
            and imported_messages == sqlite_messages
        )
        ready = bool(
            state is not None
            and state.status == "completed"
            and counts_match
            and source_preserved
            and skipped == 0
            and not errors
        )
        return ChatSQLitePreflightReport(
            source_path=resolved_source,
            source_exists=True,
            source_sha256=digest,
            status="ready" if ready else "review_required",
            imported_session_count=imported_sessions,
            imported_message_count=imported_messages,
            sqlite_session_count=sqlite_sessions,
            sqlite_message_count=sqlite_messages,
            skipped_session_count=skipped,
            validation_errors=errors,
            counts_match=counts_match,
            source_preserved=source_preserved,
            production_database_touched=False,
            ready=ready,
            generated_at=_utcnow(),
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the legacy Chat JSON store against an isolated temporary SQLite migration.",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help="Legacy JSON Chat store. Defaults to OMNIX_CHAT_STORE_PATH or the standard data path.",
    )
    args = parser.parse_args(argv)
    report = run_chat_sqlite_preflight(args.source)
    print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
    return 0 if report.ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
