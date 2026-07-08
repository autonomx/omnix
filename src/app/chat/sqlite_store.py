"""ChatSessionStore adapter backed by the SQLite Chat repository."""
from __future__ import annotations

from pathlib import Path

from .json_import import import_legacy_chat_json
from .models import ChatSession
from .prompt_store import ChatSessionStore as PromptAssemblyChatSessionStore
from .repository import ChatImportState, SQLiteChatRepository


class SQLiteChatSessionStore(PromptAssemblyChatSessionStore):
    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        legacy_json_path: str | Path | None = None,
        import_legacy: bool = True,
    ) -> None:
        self.repository = SQLiteChatRepository(db_path)
        self.path = Path(legacy_json_path) if legacy_json_path is not None else Path(":sqlite:")
        self.import_state: ChatImportState | None = None
        if import_legacy:
            self.import_state = import_legacy_chat_json(
                self.repository,
                source_path=legacy_json_path,
            )

    def _load_sessions(self) -> list[ChatSession]:
        return self.repository.load_sessions()

    def _save_sessions(self, sessions: list[ChatSession]) -> None:
        self.repository.save_sessions(sessions)
