"""Chat store adapter that routes provider generation through PromptAssembly."""
from __future__ import annotations

import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.assistant_memory import MemoryService, default_memory_service
from app.assistant_memory.jobs import (
    enqueue_memory_suggestion_job,
    process_memory_suggestion_job,
)

from .compaction import (
    DEFAULT_RECENT_MESSAGE_LIMIT,
    InMemoryConversationSummaryRepository,
    compaction_enabled,
    enqueue_compaction_job,
)
from .history_search import (
    InMemoryHistorySearchService,
    default_history_search_service,
    history_recall_enabled,
)
from .memory_commands import execute_memory_command, parse_memory_command
from .memory_prompt import resolve_prompt_memory
from .models import ChatMessage, ChatSession, ChatSessionSummary, SendChatMessageRequest
from .prompt_assembly import PromptAssembly, build_prompt_assembly
from .prompt_rendering import RenderedPrompt, render_prompt_assembly
from .store import (
    ChatSessionStore as JsonChatSessionStore,
    _model_key,
    _pop_ready_sentences,
    _provider_message,
    _provider_key,
)

logger = logging.getLogger(__name__)


def _memory_suggestions_allowed(session: ChatSession) -> bool:
    return session.interaction_mode != "character" or session.write_memory


class ChatSessionStore(JsonChatSessionStore):
    """Compatibility store with one provider prompt path for every generation mode."""

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        memory_service_factory: Callable[[], MemoryService] = default_memory_service,
        history_search_factory: Callable[[], InMemoryHistorySearchService] = default_history_search_service,
        summary_repository_factory: Callable[[], InMemoryConversationSummaryRepository] = InMemoryConversationSummaryRepository,
    ) -> None:
        super().__init__(path)
        self.memory_service_factory = memory_service_factory
        self.history_search_factory = history_search_factory
        self.summary_repository_factory = summary_repository_factory

    def build_provider_prompt(
        self,
        session: ChatSession,
        user_message: ChatMessage,
        context_items: list[dict[str, Any]] | None = None,
    ) -> tuple[PromptAssembly, RenderedPrompt]:
        from app import shared

        approved_memory, memory_diagnostics = resolve_prompt_memory(
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
        summary_record = (
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
        assembly.diagnostics["memory"] = memory_diagnostics
        assembly.diagnostics["compaction"] = (
            {
                "enabled": True,
                "summary_id": summary_record.id,
                "summary_revision": summary_record.revision,
                "through_message_id": summary_record.through_message_id,
                "source_message_count": summary_record.source_message_count,
                "recent_message_limit": DEFAULT_RECENT_MESSAGE_LIMIT,
            }
            if summary_record is not None
            else {"enabled": compaction_enabled(), "summary_id": None}
        )
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
        return assembly, render_prompt_assembly(assembly)

    def _provider_messages(
        self,
        session: ChatSession,
        user_message: ChatMessage,
        context_items: list[dict[str, Any]],
    ):
        _, rendered = self.build_provider_prompt(session, user_message, context_items)
        return self._provider_messages_from_rendered(session, user_message, rendered)

    @staticmethod
    def _provider_messages_from_rendered(
        session: ChatSession,
        user_message: ChatMessage,
        rendered: RenderedPrompt,
    ):
        source_messages = {message.id: message for message in session.messages}
        source_messages[user_message.id] = user_message
        return [
            _provider_message(
                source_messages.get(message.message_id, message),
                content=message.content,
            )
            for message in rendered.messages
        ]

    @staticmethod
    def _active_history_metadata(assembly: PromptAssembly) -> dict[str, Any]:
        history = assembly.diagnostics.get("history_recall")
        if not isinstance(history, dict) or not history.get("enabled"):
            return {}
        return {"history_recall": history}

    @staticmethod
    def _active_memory_metadata(
        assembly: PromptAssembly,
        rendered: RenderedPrompt,
    ) -> dict[str, Any]:
        memory = assembly.diagnostics.get("memory")
        if not isinstance(memory, dict) or not memory.get("memory_enabled"):
            return {}
        return {
            "memory_context": {
                **memory,
                "budget": rendered.diagnostics.model_dump(mode="json"),
            }
        }

    def _mark_memory_command(self, session_id: str, message_id: str, command: dict[str, Any]) -> None:
        sessions = self._load_sessions()
        for index, session in enumerate(sessions):
            if session.id != session_id:
                continue
            for message in session.messages:
                if message.id == message_id:
                    message.metadata["memory_command"] = command
                    break
            sessions[index] = session
            self._save_sessions(sessions)
            return

    def _enqueue_memory_suggestion_job(self, session_id: str, user_message_id: str) -> None:
        job = enqueue_memory_suggestion_job(session_id, user_message_id)
        if job is None:
            return
        try:
            process_memory_suggestion_job(
                job,
                chat_store=self,
                memory_service=self.memory_service_factory(),
            )
        except Exception as exc:
            from app.jobs import FailJobRequest, default_job_store

            default_job_store().fail_job(
                job.id,
                FailJobRequest(
                    code="memory_suggestion_inline_failed",
                    message=str(exc)[:500] or "Memory suggestion job failed.",
                    retryable=True,
                ),
            )

    def _run_post_turn_maintenance(self, session: ChatSession, user_message_id: str) -> None:
        """Run optional memory maintenance without changing chat delivery success."""
        if _memory_suggestions_allowed(session):
            try:
                self._enqueue_memory_suggestion_job(session.id, user_message_id)
            except Exception:
                logger.warning(
                    "memory suggestion maintenance unavailable after completed chat turn",
                    exc_info=True,
                )
        try:
            enqueue_compaction_job(session)
        except Exception:
            logger.warning(
                "history compaction maintenance unavailable after completed chat turn",
                exc_info=True,
            )

    def begin_user_message(
        self,
        session_id: str,
        request: SendChatMessageRequest,
        *,
        context_items: list[dict[str, Any]] | None = None,
        context_diagnostics: dict[str, Any] | None = None,
    ) -> tuple[ChatSession, ChatMessage] | None:
        appended = super().begin_user_message(
            session_id,
            request,
            context_items=context_items,
            context_diagnostics=context_diagnostics,
        )
        if appended is None:
            return None
        session, message = appended
        command = parse_memory_command(message.content)
        if command is not None:
            payload = command.model_dump(mode="json")
            message.metadata["memory_command"] = payload
            self._mark_memory_command(session.id, message.id, payload)
        return session, message

    def append_user_message(
        self,
        session_id: str,
        request: SendChatMessageRequest,
        *,
        context_items: list[dict[str, Any]] | None = None,
        context_diagnostics: dict[str, Any] | None = None,
    ) -> tuple[ChatSession, ChatMessage] | None:
        command = parse_memory_command(request.content)
        if command is None:
            appended = super().append_user_message(
                session_id,
                request,
                context_items=context_items,
                context_diagnostics=context_diagnostics,
            )
            if appended is not None:
                self._run_post_turn_maintenance(appended[0], appended[1].id)
            return appended
        appended = self.begin_user_message(
            session_id,
            request,
            context_items=context_items,
            context_diagnostics=context_diagnostics,
        )
        if appended is None:
            return None
        _, user_message = appended
        result = execute_memory_command(
            self,
            self.memory_service_factory(),
            session_id,
            user_message.id,
            command,
        )
        completed = self.complete_streamed_reply(
            session_id,
            user_message.id,
            result.content,
            {
                "generation_status": "completed",
                "memory_command": result.model_dump(mode="json"),
            },
        )
        return (completed, user_message) if completed is not None else None

    def complete_streamed_reply(
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
                self._run_post_turn_maintenance(completed, user_message_id)
        return completed

    def _generate_provider_reply(
        self,
        session: ChatSession,
        user_message: ChatMessage,
        *,
        provider_id: str | None,
        model_id: str | None,
        context_items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        from app import shared

        provider = shared.get_provider(_provider_key(provider_id))
        if provider is None:
            raise RuntimeError("Chat provider is not available")
        assembly, rendered = self.build_provider_prompt(session, user_message, context_items)
        messages = self._provider_messages_from_rendered(session, user_message, rendered)
        model_name = _model_key(model_id)
        response = provider.chat_completion(messages=messages, model=model_name, stream=False)
        content = (getattr(response, "content", "") or "").strip()
        if not content:
            raise RuntimeError("Chat response was empty")
        metadata: dict[str, Any] = {
            "generation_status": "completed",
            "provider_id": provider_id,
            "model_id": model_id,
            "resolved_model": getattr(response, "model", None) or model_name,
            **self._active_memory_metadata(assembly, rendered),
            **self._active_history_metadata(assembly),
        }
        usage = getattr(response, "usage", None)
        if usage:
            metadata["usage"] = usage
        thinking = getattr(response, "thinking", None) or getattr(response, "reasoning", None)
        if thinking:
            metadata["thinking"] = thinking
        return {"content": content, "metadata": metadata}

    def stream_provider_reply_chunks(
        self,
        session: ChatSession,
        user_message: ChatMessage,
        *,
        provider_id: str | None,
        model_id: str | None,
        context_items: list[dict[str, Any]] | None = None,
    ):
        command = parse_memory_command(user_message.content)
        if command is not None:
            result = execute_memory_command(
                self,
                self.memory_service_factory(),
                session.id,
                user_message.id,
                command,
            )
            yield {"type": "text_chunk", "text": result.content}
            yield {
                "type": "complete",
                "content": result.content,
                "metadata": {
                    "generation_status": "completed",
                    "memory_command": result.model_dump(mode="json"),
                },
            }
            return

        from app import shared

        provider = shared.get_provider(_provider_key(provider_id))
        if provider is None:
            raise RuntimeError("Chat provider is not available")
        assembly, rendered = self.build_provider_prompt(
            session,
            user_message,
            context_items or [],
        )
        messages = self._provider_messages_from_rendered(session, user_message, rendered)
        model_name = _model_key(model_id)
        response = provider.chat_completion(messages=messages, model=model_name, stream=True)
        pending = ""
        full_text = ""
        resolved_model = model_name
        usage = None
        for chunk in response:
            text = getattr(chunk, "content", "") or ""
            if not text:
                continue
            resolved_model = getattr(chunk, "model", None) or resolved_model
            usage = getattr(chunk, "usage", None) or usage
            full_text += text
            pending += text
            ready, pending = _pop_ready_sentences(pending)
            for sentence in ready:
                yield {"type": "text_chunk", "text": sentence}
        if pending.strip():
            yield {"type": "text_chunk", "text": pending.strip()}
        yield {
            "type": "complete",
            "content": full_text.strip(),
            "metadata": {
                "generation_status": "completed",
                "provider_id": provider_id,
                "model_id": model_id,
                "resolved_model": resolved_model,
                **self._active_memory_metadata(assembly, rendered),
                **self._active_history_metadata(assembly),
                **({"usage": usage} if usage else {}),
            },
        }

    @staticmethod
    def _summary(session: ChatSession) -> ChatSessionSummary:
        return ChatSessionSummary(
            id=session.id,
            title=session.title,
            provider_id=session.provider_id,
            model_id=session.model_id,
            research_mode_override=session.research_mode_override,
            profile_id=session.profile_id,
            workspace_id=session.workspace_id,
            project_id=session.project_id,
            memory_enabled=session.memory_enabled,
            memory_snapshot_id=session.memory_snapshot_id,
            memory_snapshot_revision=session.memory_snapshot_revision,
            memory_record_count=session.memory_record_count,
            memory_last_refreshed_at=session.memory_last_refreshed_at,
            message_count=session.message_count,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )


def chat_sqlite_store_enabled() -> bool:
    return (os.environ.get("OMNIX_CHAT_SQLITE_STORE_ENABLED") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def default_chat_store() -> ChatSessionStore:
    if chat_sqlite_store_enabled():
        from .sqlite_store import InMemoryChatSessionStore

        return InMemoryChatSessionStore()
    return ChatSessionStore()
