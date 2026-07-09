from __future__ import annotations

from types import SimpleNamespace

from app import shared
from app.chat import ChatSessionStore, CreateChatSessionRequest, SendChatMessageRequest
from app.chat.assistant_turns import AssistantTurnCoordinator


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
