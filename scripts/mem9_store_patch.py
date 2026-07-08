from pathlib import Path

path = Path("src/app/chat/prompt_store.py")
text = path.read_text(encoding="utf-8")
text = text.replace(
    "from .memory_commands import execute_memory_command, parse_memory_command\n",
    "from .memory_commands import execute_memory_command, parse_memory_command\nfrom app.assistant_memory.jobs import enqueue_memory_suggestion_job\n",
    1,
)
old = """        if command is None:
            return super().append_user_message(
                session_id,
                request,
                context_items=context_items,
                context_diagnostics=context_diagnostics,
            )
"""
new = """        if command is None:
            appended = super().append_user_message(
                session_id,
                request,
                context_items=context_items,
                context_diagnostics=context_diagnostics,
            )
            if appended is not None:
                enqueue_memory_suggestion_job(session_id, appended[1].id)
            return appended
"""
if text.count(old) != 1:
    raise SystemExit("append hook pattern not found exactly once")
text = text.replace(old, new, 1)
marker = "    def _generate_provider_reply(\n"
method = """    def complete_streamed_reply(
        self,
        session_id: str,
        user_message_id: str,
        content: str,
        metadata: dict[str, Any],
    ) -> ChatSession | None:
        completed = super().complete_streamed_reply(
            session_id,
            user_message_id,
            content,
            metadata,
        )
        if completed is not None:
            user_message = next(
                (message for message in completed.messages if message.id == user_message_id),
                None,
            )
            if user_message is not None and not user_message.metadata.get("memory_command"):
                enqueue_memory_suggestion_job(session_id, user_message_id)
        return completed

"""
if text.count(marker) != 1:
    raise SystemExit("generation method marker not found exactly once")
text = text.replace(marker, method + marker, 1)
path.write_text(text, encoding="utf-8")
