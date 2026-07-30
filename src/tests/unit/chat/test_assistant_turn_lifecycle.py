from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app import shared
from app.chat import ChatSessionStore, CreateChatSessionRequest, SendChatMessageRequest
from app.chat.assistant_turns import AssistantTurnCoordinator
from app.chat.compaction import build_deterministic_summary
from app.chat.models import (
    ChatMessage,
    ChatSession,
    MessageContentPurpose,
    project_message_content,
)
from app.chat.prompt_assembly import build_prompt_assembly


class StreamingProvider:
    def chat_completion(self, *, messages, model, stream=False):
        assert stream is True
        return iter(
            [
                SimpleNamespace(content="First sentence. ", model=model, usage=None),
                SimpleNamespace(content="Second sentence.", model=model, usage=None),
            ]
        )


def test_assistant_turn_coordinator_persists_terminal_interruption(tmp_path) -> None:
    path = tmp_path / "assistant-turns.json"
    coordinator = AssistantTurnCoordinator(path)
    turn = coordinator.start(
        session_id="chat:s1",
        user_message_id="msg:u1",
        user_turn_id="user-turn:1",
        speech_segment_id="segment:1",
    )

    coordinator.mark_streaming(turn.assistant_turn_id)
    interrupted = coordinator.request_cancel(turn.assistant_turn_id, "confirmed_overlap")
    repeated = coordinator.request_cancel(turn.assistant_turn_id, "duplicate")

    assert interrupted is not None
    assert interrupted.lifecycle == "interrupted"
    assert interrupted.provider_execution == "cancel_requested"
    assert repeated is not None
    assert repeated.terminal_version == interrupted.terminal_version
    assert coordinator.try_complete(turn.assistant_turn_id) is False

    reloaded = AssistantTurnCoordinator(path).get(turn.assistant_turn_id)
    assert reloaded is not None
    assert reloaded.lifecycle == "interrupted"
    assert reloaded.user_turn_id == "user-turn:1"


def test_streamed_turn_ids_are_idempotent_and_interruption_blocks_completion(monkeypatch, tmp_path) -> None:
    provider = StreamingProvider()
    coordinator = AssistantTurnCoordinator(tmp_path / "assistant-turns.json")
    monkeypatch.setattr(shared, "get_provider", lambda provider_name=None: provider)
    monkeypatch.setattr(shared, "get_global_system_prompt", lambda: "System prompt")
    monkeypatch.setattr(
        "app.chat.character_store.default_assistant_turn_coordinator",
        lambda: coordinator,
    )

    store = ChatSessionStore(tmp_path / "chat.json")
    session = store.create_session(CreateChatSessionRequest(title="New chat"))
    request = SendChatMessageRequest(
        content="hello",
        provider_id="lmstudio",
        model_id="test-model",
        user_turn_id="voice-user-turn:1",
        speech_segment_id="voice-segment:1",
    )

    started, user_message = store.begin_user_message(session.id, request)
    duplicate_session, duplicate_message = store.begin_user_message(session.id, request)

    assert duplicate_session.id == started.id
    assert duplicate_message.id == user_message.id
    assistant_turn_id = str(user_message.metadata["assistant_turn_id"])
    assert user_message.metadata["user_turn_id"] == "voice-user-turn:1"

    events = store.stream_provider_reply_chunks(
        started,
        user_message,
        provider_id="lmstudio",
        model_id="test-model",
    )
    first = next(events)
    assert first["type"] == "text_chunk"

    coordinator.request_cancel(assistant_turn_id, "confirmed_overlap")
    remaining = list(events)
    completion = next(event for event in remaining if event["type"] == "complete")
    persisted = store.complete_streamed_reply(
        session.id,
        user_message.id,
        str(completion["content"]),
        dict(completion["metadata"]),
    )

    assert persisted is not None
    saved_user = next(message for message in persisted.messages if message.id == user_message.id)
    assert saved_user.metadata["generation_status"] == "interrupted"
    assistant_messages = [message for message in persisted.messages if message.role == "assistant"]
    assert len(assistant_messages) == 1
    assert assistant_messages[0].metadata["generation_status"] == "interrupted"
    assert assistant_messages[0].metadata["assistant_turn_id"] == assistant_turn_id
    assert coordinator.get(assistant_turn_id).lifecycle == "interrupted"


def test_completed_audio_turn_still_persists_assistant_transcript(monkeypatch, tmp_path) -> None:
    coordinator = AssistantTurnCoordinator(tmp_path / "assistant-turns.json")
    monkeypatch.setattr(
        "app.chat.character_store.default_assistant_turn_coordinator",
        lambda: coordinator,
    )

    store = ChatSessionStore(tmp_path / "chat.json")
    session = store.create_session(CreateChatSessionRequest(title="New chat"))
    started, user_message = store.begin_user_message(
        session.id,
        SendChatMessageRequest(
            content="hello",
            user_turn_id="voice-user-turn:completed-audio",
            speech_segment_id="voice-segment:completed-audio",
        ),
    )
    assistant_turn_id = str(user_message.metadata["assistant_turn_id"])
    coordinator.mark_streaming(assistant_turn_id)
    assert coordinator.try_complete(assistant_turn_id) is True

    persisted = store.complete_streamed_reply(
        started.id,
        user_message.id,
        "The answer was already spoken.",
        {
            "generation_status": "completed",
            "assistant_turn_id": assistant_turn_id,
        },
    )

    assert persisted is not None
    assistants = [message for message in persisted.messages if message.role == "assistant"]
    assert len(assistants) == 1
    assert assistants[0].content == "The answer was already spoken."
    assert assistants[0].metadata["assistant_turn_id"] == assistant_turn_id


def test_client_disconnect_persists_generated_interrupted_transcript(monkeypatch, tmp_path) -> None:
    provider = StreamingProvider()
    coordinator = AssistantTurnCoordinator(tmp_path / "assistant-turns.json")
    monkeypatch.setattr(shared, "get_provider", lambda provider_name=None: provider)
    monkeypatch.setattr(shared, "get_global_system_prompt", lambda: "System prompt")
    monkeypatch.setattr(
        "app.chat.character_store.default_assistant_turn_coordinator",
        lambda: coordinator,
    )

    store = ChatSessionStore(tmp_path / "chat.json")
    session = store.create_session(CreateChatSessionRequest(title="New chat"))
    started, user_message = store.begin_user_message(
        session.id,
        SendChatMessageRequest(
            content="hello",
            provider_id="lmstudio",
            model_id="test-model",
            user_turn_id="voice-user-turn:disconnect",
            speech_segment_id="voice-segment:disconnect",
        ),
    )
    assistant_turn_id = str(user_message.metadata["assistant_turn_id"])
    events = store.stream_provider_reply_chunks(
        started,
        user_message,
        provider_id="lmstudio",
        model_id="test-model",
    )

    first = next(events)
    assert first["type"] == "text_chunk"
    generated_before_disconnect = str(first["text"]).strip()
    events.close()

    persisted = store.get_session(session.id)
    assert persisted is not None
    saved_user = next(message for message in persisted.messages if message.id == user_message.id)
    assistants = [message for message in persisted.messages if message.role == "assistant"]
    assert saved_user.metadata["generation_status"] == "interrupted"
    assert len(assistants) == 1
    assert assistants[0].content == generated_before_disconnect
    assert assistants[0].metadata["generation_status"] == "interrupted"
    assert assistants[0].metadata["assistant_turn_id"] == assistant_turn_id


def test_projection_preserves_audit_text_but_hides_unheard_suffix() -> None:
    text = "Delivered phrase. Unheard phrase."
    delivered_end = len("Delivered phrase.")
    message = ChatMessage(
        id="msg:a1",
        role="assistant",
        content=text,
        created_at=datetime.now(timezone.utc).isoformat(),
        metadata={
            "delivery_status": "interrupted",
            "visual_delivered_text_end": delivered_end,
            "context_delivered_text_end": delivered_end,
        },
    )

    assert project_message_content(message, MessageContentPurpose.MODEL) == "Delivered phrase."
    assert project_message_content(message, MessageContentPurpose.MEMORY) == "Delivered phrase."
    assert project_message_content(message, MessageContentPurpose.SUMMARY) == "Delivered phrase."
    assert project_message_content(message, MessageContentPurpose.SEARCH) == "Delivered phrase."
    assert project_message_content(message, MessageContentPurpose.AUDIT) == text
    assert project_message_content(message, MessageContentPurpose.TRANSCRIPT).endswith("[Response interrupted]")


def test_prompt_and_summary_exclude_unheard_assistant_content() -> None:
    now = datetime.now(timezone.utc).isoformat()
    messages = [
        ChatMessage(id="u0", role="user", content="Earlier question", created_at=now),
        ChatMessage(
            id="a0",
            role="assistant",
            content="Known answer. Hidden continuation.",
            created_at=now,
            metadata={
                "delivery_status": "interrupted",
                "visual_delivered_text_end": len("Known answer."),
                "context_delivered_text_end": len("Known answer."),
            },
        ),
    ]
    for index in range(25):
        messages.append(ChatMessage(
            id=f"u{index + 1}",
            role="user",
            content=f"Follow-up {index}",
            created_at=now,
        ))
    current = messages[-1]
    session = ChatSession(
        id="chat:projection",
        title="Projection",
        messages=messages,
        message_count=len(messages),
        created_at=now,
        updated_at=now,
    )

    assembly = build_prompt_assembly(
        session,
        current,
        global_system_prompt="System",
    )
    rendered_history = "\n".join(item.content for item in assembly.recent_messages)
    assert "Hidden continuation" not in rendered_history

    summary = build_deterministic_summary(session, recent_message_limit=2)
    assert summary is not None
    assert "Known answer." in summary.summary
    assert "Hidden continuation" not in summary.summary
