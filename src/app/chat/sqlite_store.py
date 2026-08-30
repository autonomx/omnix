"""ChatSessionStore adapter backed by the provider-free Chat repository."""
from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path

from app.assistant_memory import MemoryService, default_memory_service

from .compaction import InMemoryConversationSummaryRepository
from .history_search import InMemoryHistorySearchService, default_history_search_service
from .json_import import import_legacy_chat_json
from .models import ChatSession
from .prompt_store import ChatSessionStore as PromptAssemblyChatSessionStore
from .repository import ChatImportState, InMemoryChatRepository


class InMemoryChatSessionStore(PromptAssemblyChatSessionStore):
    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        legacy_json_path: str | Path | None = None,
        import_legacy: bool = True,
        memory_service_factory: Callable[[], MemoryService] = default_memory_service,
        history_search_factory: Callable[[], InMemoryHistorySearchService] = default_history_search_service,
        summary_repository_factory: Callable[[], InMemoryConversationSummaryRepository] = InMemoryConversationSummaryRepository,
    ) -> None:
        self.repository = InMemoryChatRepository(db_path)
        self.path = Path(legacy_json_path) if legacy_json_path is not None else Path(":memory:chat")
        self.memory_service_factory = memory_service_factory
        self.history_search_factory = history_search_factory
        self.summary_repository_factory = summary_repository_factory
        self._prompt_context_cache = OrderedDict()
        self._prompt_context_cache_lock = threading.Lock()
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
