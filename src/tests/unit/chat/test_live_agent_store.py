from __future__ import annotations

from datetime import datetime, timezone

from app.assist_core.mode_chat import ModeChatResponse
from app.chat.live_agent_store import install_live_agent_store_hooks
from app.chat.models import ChatMessage, ChatSession


class DummyStore:
    def __init__(self, session: ChatSession) -> None:
        self.sessions = [session]
        self.provider_calls = 0
        self.save_calls = 0

    def _load_sessions(self):
        return self.sessions

    def _save_sessions(self, sessions):
        self.save_calls += 1
        self.sessions = sessions

    def stream_provider_reply_chunks(
        self,
        session,
        user_message,
        *,
        provider_id=None,
        model_id=None,
        context_items=None,
    ):
        self.provider_calls += 1
        yield {"type": "text_chunk", "text": "Direct provider answer."}
        yield {
            "type": "complete",
            "content": "Direct provider answer.",
            "metadata": {"generation_status": "completed", "provider_id": provider_id},
        }


class TargetedMetadataStore(DummyStore):
    def __init__(self, session: ChatSession) -> None:
        super().__init__(session)
        self.targeted_updates: list[dict[str, object]] = []

    def update_user_message_metadata(
        self,
        *,
        session_id: str,
        message_id: str,
        metadata: dict[str, object],
    ) -> bool:
        self.targeted_updates.append(
            {
                "session_id": session_id,
                "message_id": message_id,
                "metadata": dict(metadata),
            }
        )
        return True


def _session(content: str, *, voice: bool = True, explicit_agent: bool = False):
    now = datetime.now(timezone.utc).isoformat()
    metadata = {
        "agent_mode": explicit_agent,
        "assistant_turn_id": "assistant-turn:test",
    }
    if voice:
        metadata.update({
            "user_turn_id": "voice-user-turn:test",
            "speech_segment_id": "voice-segment:test",
        })
    message = ChatMessage(
        id="msg:user",
        role="user",
        content=content,
        created_at=now,
        metadata=metadata,
    )
    session = ChatSession(
        id="chat:test",
        title="Test",
        messages=[message],
        message_count=1,
        created_at=now,
        updated_at=now,
    )
    return session, message


def test_auto_live_agent_returns_proposal_without_provider_execution(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_LIVE_AGENT_ENABLED", "1")
    monkeypatch.setenv("OMNIX_LIVE_AGENT_AUTO_ROUTE_ENABLED", "1")
    monkeypatch.setenv("HERMES_ENABLED", "1")
    session, message = _session("Turn off the kitchen light")
    store = DummyStore(session)
    install_live_agent_store_hooks(DummyStore)
    monkeypatch.setattr(
        "app.chat.live_agent_store.plan_live_agent_proposal",
        lambda **kwargs: ModeChatResponse(
            ok=True,
            mode="agent",
            backend="hermes",
            result={
                "success": True,
                "response": "Proposal: turn off the kitchen light after approval.",
                "domain": "house",
                "tool_calls": [
                    {
                        "name": "set_light",
                        "args": {"room": "kitchen", "state": "off"},
                    }
                ],
                "tool_results": [],
                "requires_confirmation": True,
                "error": None,
            },
        ),
    )

    events = list(store.stream_provider_reply_chunks(
        session,
        message,
        provider_id="lmstudio",
        model_id="test-model",
    ))

    completion = next(event for event in events if event["type"] == "complete")
    assert store.provider_calls == 0
    assert completion["metadata"]["backend"] == "hermes"
    assert completion["metadata"]["proposal_only"] is True
    assert completion["metadata"]["review_required"] is True
    assert completion["metadata"]["executes"] is False
    assert completion["metadata"]["live_agent_route"]["route"] == "agent_plan"
    saved = store.sessions[0].messages[0].metadata
    assert saved["dry_run"] is True
    assert saved["live_agent_route"]["automatic"] is True


def test_hermes_failure_falls_back_to_original_provider_stream(monkeypatch) -> None:
    from app.assist_core.live_agent_planner import LiveAgentUnavailable

    monkeypatch.setenv("OMNIX_LIVE_AGENT_ENABLED", "1")
    monkeypatch.setenv("OMNIX_LIVE_AGENT_AUTO_ROUTE_ENABLED", "1")
    monkeypatch.setenv("HERMES_ENABLED", "1")
    session, message = _session("Schedule a meeting for tomorrow")
    store = DummyStore(session)
    install_live_agent_store_hooks(DummyStore)

    def unavailable(**kwargs):
        raise LiveAgentUnavailable("offline")

    monkeypatch.setattr("app.chat.live_agent_store.plan_live_agent_proposal", unavailable)
    events = list(store.stream_provider_reply_chunks(
        session,
        message,
        provider_id="lmstudio",
        model_id="test-model",
    ))

    completion = next(event for event in events if event["type"] == "complete")
    assert store.provider_calls == 1
    assert completion["content"] == "Direct provider answer."
    assert completion["metadata"]["live_agent"] is False
    assert completion["metadata"]["live_agent_route"]["route"] == "direct_chat"
    assert completion["metadata"]["live_agent_route"]["reason"] == (
        "hermes_unavailable_fallback"
    )
    assert completion["metadata"]["live_agent_fallback_error"] == "offline"


def test_casual_live_voice_stays_on_original_provider_path(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_LIVE_AGENT_ENABLED", "1")
    monkeypatch.setenv("OMNIX_LIVE_AGENT_AUTO_ROUTE_ENABLED", "1")
    monkeypatch.setenv("HERMES_ENABLED", "1")
    session, message = _session("How are you?")
    store = DummyStore(session)
    install_live_agent_store_hooks(DummyStore)

    events = list(store.stream_provider_reply_chunks(
        session,
        message,
        provider_id="lmstudio",
        model_id="test-model",
    ))

    completion = next(event for event in events if event["type"] == "complete")
    assert store.provider_calls == 1
    assert completion["metadata"]["live_agent_route"]["route"] == "direct_chat"
    assert completion["metadata"]["live_agent_route"]["reason"] == (
        "casual_conversation"
    )


def test_direct_route_persistence_does_not_block_first_provider_chunk(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OMNIX_LIVE_AGENT_ENABLED", "1")
    monkeypatch.setenv("OMNIX_LIVE_AGENT_AUTO_ROUTE_ENABLED", "1")
    monkeypatch.setenv("HERMES_ENABLED", "1")
    session, message = _session("How are you?")
    store = DummyStore(session)
    install_live_agent_store_hooks(DummyStore)

    stream = store.stream_provider_reply_chunks(
        session,
        message,
        provider_id="lmstudio",
        model_id="test-model",
    )

    first = next(stream)
    assert first == {"type": "text_chunk", "text": "Direct provider answer."}
    assert store.provider_calls == 1
    assert store.save_calls == 0

    completion = next(stream)
    assert completion["type"] == "complete"
    assert store.save_calls == 1
    assert store.sessions[0].messages[0].metadata["live_agent_route"]["route"] == (
        "direct_chat"
    )


def test_direct_route_uses_targeted_user_metadata_update(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_LIVE_AGENT_ENABLED", "1")
    monkeypatch.setenv("OMNIX_LIVE_AGENT_AUTO_ROUTE_ENABLED", "1")
    monkeypatch.setenv("HERMES_ENABLED", "1")
    session, message = _session("How are you?")
    store = TargetedMetadataStore(session)
    install_live_agent_store_hooks(TargetedMetadataStore)

    events = list(store.stream_provider_reply_chunks(
        session,
        message,
        provider_id="lmstudio",
        model_id="test-model",
    ))

    assert events[-1]["type"] == "complete"
    assert store.save_calls == 0
    assert store.targeted_updates == [{
        "session_id": session.id,
        "message_id": message.id,
        "metadata": {
            "agent_mode": False,
            "dry_run": False,
            "live_agent_route": events[-1]["metadata"]["live_agent_route"],
        },
    }]


def test_typed_chat_uses_generalized_chat_route_before_legacy_live_agent(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_LIVE_AGENT_ENABLED", "1")
    monkeypatch.setenv("OMNIX_LIVE_AGENT_AUTO_ROUTE_ENABLED", "1")
    monkeypatch.setenv("HERMES_ENABLED", "1")
    session, message = _session("Delete the file", voice=False)
    store = DummyStore(session)
    install_live_agent_store_hooks(DummyStore)

    events = list(store.stream_provider_reply_chunks(
        session,
        message,
        provider_id="lmstudio",
        model_id="test-model",
    ))

    completion = next(event for event in events if event["type"] == "complete")
    assert store.provider_calls == 1
    assert "live_agent_route" not in completion["metadata"]
    assert message.metadata["omnix_route"]["lane"] == "chat"
    assert message.metadata["omnix_chat_routed"] is True
