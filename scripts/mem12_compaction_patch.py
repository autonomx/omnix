from pathlib import Path

compaction = Path("src/app/chat/compaction.py")
text = compaction.read_text(encoding="utf-8")
old = """    def save(self, summary: ConversationSummary) -> ConversationSummary:
        with self._connect() as connection:
            connection.execute(
"""
new = """    def save(self, summary: ConversationSummary) -> ConversationSummary:
        with self._connect() as connection:
            existing = connection.execute(
                \"SELECT revision FROM chat_conversation_summaries WHERE session_id = ? AND through_message_id = ?\",
                (summary.session_id, summary.through_message_id),
            ).fetchone()
            if existing is None:
                latest = connection.execute(
                    \"SELECT COALESCE(MAX(revision), 0) FROM chat_conversation_summaries WHERE session_id = ?\",
                    (summary.session_id,),
                ).fetchone()
                summary = summary.model_copy(update={\"revision\": int(latest[0]) + 1})
            connection.execute(
"""
if text.count(old) != 1:
    raise SystemExit("summary save marker missing")
compaction.write_text(text.replace(old, new, 1), encoding="utf-8")

assembly = Path("src/app/chat/prompt_assembly.py")
text = assembly.read_text(encoding="utf-8")
old = """    assistant_identity: list[str] | None = None,
    budget: PromptBudget | None = None,
) -> PromptAssembly:
"""
new = """    assistant_identity: list[str] | None = None,
    budget: PromptBudget | None = None,
    recent_message_limit: int | None = None,
) -> PromptAssembly:
"""
if text.count(old) != 1:
    raise SystemExit("prompt assembly signature marker missing")
text = text.replace(old, new, 1)
old = """    recent_messages = [
        PromptTurn(role=message.role, content=message.content, message_id=message.id)
        for message in session.messages
        if message.id != user_message.id and message.role != \"system\"
    ]
"""
new = """    eligible_recent_messages = [
        message
        for message in session.messages
        if message.id != user_message.id and message.role != \"system\"
    ]
    if recent_message_limit is not None:
        eligible_recent_messages = eligible_recent_messages[-max(0, recent_message_limit):]
    recent_messages = [
        PromptTurn(role=message.role, content=message.content, message_id=message.id)
        for message in eligible_recent_messages
    ]
"""
if text.count(old) != 1:
    raise SystemExit("recent message block missing")
assembly.write_text(text.replace(old, new, 1), encoding="utf-8")

store = Path("src/app/chat/prompt_store.py")
text = store.read_text(encoding="utf-8")
text = text.replace(
    "from .history_search import (\n",
    "from .compaction import (\n    DEFAULT_RECENT_MESSAGE_LIMIT,\n    SQLiteConversationSummaryRepository,\n    compaction_enabled,\n    enqueue_compaction_job,\n)\nfrom .history_search import (\n",
    1,
)
old = """        history_search_factory: Callable[[], SQLiteHistorySearchService] = default_history_search_service,
    ) -> None:
        super().__init__(path)
        self.memory_service_factory = memory_service_factory
        self.history_search_factory = history_search_factory
"""
new = """        history_search_factory: Callable[[], SQLiteHistorySearchService] = default_history_search_service,
        summary_repository_factory: Callable[[], SQLiteConversationSummaryRepository] = SQLiteConversationSummaryRepository,
    ) -> None:
        super().__init__(path)
        self.memory_service_factory = memory_service_factory
        self.history_search_factory = history_search_factory
        self.summary_repository_factory = summary_repository_factory
"""
if text.count(old) != 1:
    raise SystemExit("prompt store constructor missing")
text = text.replace(old, new, 1)
old = """        assembly = build_prompt_assembly(
            session,
            user_message,
            global_system_prompt=shared.get_global_system_prompt(),
            context_items=context_items or [],
            approved_memory=approved_memory,
            retrieved_history=history_result.items if history_result is not None else [],
        )
"""
new = """        summary_record = (
            self.summary_repository_factory().latest(session.id)
            if compaction_enabled() else None
        )
        assembly = build_prompt_assembly(
            session,
            user_message,
            global_system_prompt=shared.get_global_system_prompt(),
            context_items=context_items or [],
            approved_memory=approved_memory,
            retrieved_history=history_result.items if history_result is not None else [],
            session_summary=summary_record.summary if summary_record is not None else None,
            recent_message_limit=(DEFAULT_RECENT_MESSAGE_LIMIT if summary_record is not None else None),
        )
"""
if text.count(old) != 1:
    raise SystemExit("prompt assembly call missing")
text = text.replace(old, new, 1)
old = """        assembly.diagnostics[\"history_recall\"] = (
"""
insert = """        assembly.diagnostics[\"compaction\"] = (
            {
                \"enabled\": True,
                \"summary_id\": summary_record.id,
                \"summary_revision\": summary_record.revision,
                \"through_message_id\": summary_record.through_message_id,
                \"source_message_count\": summary_record.source_message_count,
                \"recent_message_limit\": DEFAULT_RECENT_MESSAGE_LIMIT,
            }
            if summary_record is not None
            else {\"enabled\": compaction_enabled(), \"summary_id\": None}
        )
        assembly.diagnostics[\"history_recall\"] = (
"""
if text.count(old) != 1:
    raise SystemExit("diagnostics marker missing")
text = text.replace(old, insert, 1)
old = """            if appended is not None:
                enqueue_memory_suggestion_job(session_id, appended[1].id)
            return appended
"""
new = """            if appended is not None:
                enqueue_memory_suggestion_job(session_id, appended[1].id)
                enqueue_compaction_job(appended[0])
            return appended
"""
if text.count(old) != 1:
    raise SystemExit("nonstream hook missing")
text = text.replace(old, new, 1)
old = """            if user_message is not None and not user_message.metadata.get(\"memory_command\"):
                enqueue_memory_suggestion_job(session_id, user_message_id)
        return completed
"""
new = """            if user_message is not None and not user_message.metadata.get(\"memory_command\"):
                enqueue_memory_suggestion_job(session_id, user_message_id)
                enqueue_compaction_job(completed)
        return completed
"""
if text.count(old) != 1:
    raise SystemExit("stream hook missing")
store.write_text(text.replace(old, new, 1), encoding="utf-8")

sqlite = Path("src/app/chat/sqlite_store.py")
text = sqlite.read_text(encoding="utf-8")
text = text.replace(
    "from .history_search import SQLiteHistorySearchService, default_history_search_service\n",
    "from .compaction import SQLiteConversationSummaryRepository\nfrom .history_search import SQLiteHistorySearchService, default_history_search_service\n",
    1,
)
old = """        history_search_factory: Callable[[], SQLiteHistorySearchService] = default_history_search_service,
    ) -> None:
"""
new = """        history_search_factory: Callable[[], SQLiteHistorySearchService] = default_history_search_service,
        summary_repository_factory: Callable[[], SQLiteConversationSummaryRepository] = SQLiteConversationSummaryRepository,
    ) -> None:
"""
if text.count(old) != 1:
    raise SystemExit("sqlite signature missing")
text = text.replace(old, new, 1)
old = """        self.history_search_factory = history_search_factory
        self.import_state: ChatImportState | None = None
"""
new = """        self.history_search_factory = history_search_factory
        self.summary_repository_factory = summary_repository_factory
        self.import_state: ChatImportState | None = None
"""
if text.count(old) != 1:
    raise SystemExit("sqlite assignment missing")
sqlite.write_text(text.replace(old, new, 1), encoding="utf-8")
