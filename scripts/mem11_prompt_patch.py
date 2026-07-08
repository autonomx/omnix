from pathlib import Path

path = Path("src/app/chat/prompt_store.py")
text = path.read_text(encoding="utf-8")
text = text.replace(
    "from app.assistant_memory.jobs import enqueue_memory_suggestion_job\n\n",
    "from app.assistant_memory.jobs import enqueue_memory_suggestion_job\n\nfrom .history_search import (\n    SQLiteHistorySearchService,\n    default_history_search_service,\n    history_recall_enabled,\n)\n",
    1,
)
old = """        *,
        memory_service_factory: Callable[[], MemoryService] = default_memory_service,
    ) -> None:
        super().__init__(path)
        self.memory_service_factory = memory_service_factory
"""
new = """        *,
        memory_service_factory: Callable[[], MemoryService] = default_memory_service,
        history_search_factory: Callable[[], SQLiteHistorySearchService] = default_history_search_service,
    ) -> None:
        super().__init__(path)
        self.memory_service_factory = memory_service_factory
        self.history_search_factory = history_search_factory
"""
if text.count(old) != 1:
    raise SystemExit("constructor pattern missing")
text = text.replace(old, new, 1)
old = """        approved_memory, memory_diagnostics = resolve_prompt_memory(
            session,
            memory_service_factory=self.memory_service_factory,
        )
        assembly = build_prompt_assembly(
            session,
            user_message,
            global_system_prompt=shared.get_global_system_prompt(),
            context_items=context_items or [],
            approved_memory=approved_memory,
        )
        assembly.diagnostics["memory"] = memory_diagnostics
"""
new = """        approved_memory, memory_diagnostics = resolve_prompt_memory(
            session,
            memory_service_factory=self.memory_service_factory,
        )
        history_result = None
        if history_recall_enabled():
            history_result = self.history_search_factory().search(
                user_message.content,
                profile_id=session.profile_id,
                workspace_id=session.workspace_id,
                project_id=session.project_id,
                exclude_session_id=session.id,
            )
        assembly = build_prompt_assembly(
            session,
            user_message,
            global_system_prompt=shared.get_global_system_prompt(),
            context_items=context_items or [],
            approved_memory=approved_memory,
            retrieved_history=history_result.items if history_result is not None else [],
        )
        assembly.diagnostics["memory"] = memory_diagnostics
        assembly.diagnostics["history_recall"] = (
            {
                "enabled": True,
                "status": history_result.status.model_dump(mode="json"),
                "query_terms": history_result.query_terms,
                "retrieved_message_ids": [item.message_id for item in history_result.items],
                "retrieved_count": len(history_result.items),
            }
            if history_result is not None
            else {"enabled": False, "retrieved_count": 0}
        )
"""
if text.count(old) != 1:
    raise SystemExit("assembly pattern missing")
text = text.replace(old, new, 1)
old = """    @staticmethod
    def _active_memory_metadata(
"""
insert = """    @staticmethod
    def _active_history_metadata(assembly: PromptAssembly) -> dict[str, Any]:
        history = assembly.diagnostics.get("history_recall")
        if not isinstance(history, dict) or not history.get("enabled"):
            return {}
        return {"history_recall": history}

    @staticmethod
    def _active_memory_metadata(
"""
if text.count(old) != 1:
    raise SystemExit("metadata method marker missing")
text = text.replace(old, insert, 1)
text = text.replace(
    "            **self._active_memory_metadata(assembly, rendered),\n",
    "            **self._active_memory_metadata(assembly, rendered),\n            **self._active_history_metadata(assembly),\n",
)
path.write_text(text, encoding="utf-8")

sqlite = Path("src/app/chat/sqlite_store.py")
text = sqlite.read_text(encoding="utf-8")
text = text.replace(
    "from .json_import import import_legacy_chat_json\n",
    "from .history_search import SQLiteHistorySearchService, default_history_search_service\nfrom .json_import import import_legacy_chat_json\n",
    1,
)
old = """        memory_service_factory: Callable[[], MemoryService] = default_memory_service,
    ) -> None:
"""
new = """        memory_service_factory: Callable[[], MemoryService] = default_memory_service,
        history_search_factory: Callable[[], SQLiteHistorySearchService] = default_history_search_service,
    ) -> None:
"""
if text.count(old) != 1:
    raise SystemExit("sqlite constructor signature missing")
text = text.replace(old, new, 1)
old = """        self.memory_service_factory = memory_service_factory
        self.import_state: ChatImportState | None = None
"""
new = """        self.memory_service_factory = memory_service_factory
        self.history_search_factory = history_search_factory
        self.import_state: ChatImportState | None = None
"""
if text.count(old) != 1:
    raise SystemExit("sqlite factory assignment missing")
text = text.replace(old, new, 1)
sqlite.write_text(text, encoding="utf-8")
