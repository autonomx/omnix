from __future__ import annotations

from datetime import datetime, timezone

from app.chat.assist.live_agent import LiveAgentUnavailable
from app.chat.assist.modes import ModeChatResponse
from app.chat.character_store import _CharacterSessionMixin
from app.chat.live_agent_store import LiveAgentPlanner
from app.chat.models import ChatMessage, ChatSession


class StaticPlanner:
    def __init__(self, result) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    def plan_proposal(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class UnusedPlanner:
    def plan_proposal(self, **kwargs):
        raise AssertionError("the provider route should not invoke Live Agent planning")


class DummyStore(_CharacterSessionMixin):
    def __init__(self, session: ChatSession, planner=None) -> None:
        self.sessions = [session]
        self.provider_calls = 0
        self.save_calls = 0
        self.live_agent_planner: LiveAgentPlanner = planner or UnusedPlanner()

    def get_session(self, session_id):
        return next((item for item in self.sessions if item.id == session_id), None)

    def _save_session(self, session):
        self.save_calls += 1
        self.sessions = [
            session if item.id == session.id else item for item in self.sessions
        ]

    def _stream_provider_reply_chunks_with_turn(
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

    def update_message_metadata(
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


def _use_test_turn_coordinator(monkeypatch, tmp_path) -> None:
    from app.chat.assistant_turns import AssistantTurnCoordinator

    coordinator = AssistantTurnCoordinator(tmp_path / "assistant-turns.json")
    monkeypatch.setattr(
        "app.chat.live_agent_store.default_assistant_turn_coordinator",
        lambda: coordinator,
    )


def test_auto_live_agent_returns_proposal_without_provider_execution(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("OMNIX_LIVE_AGENT_ENABLED", "1")
    monkeypatch.setenv("OMNIX_LIVE_AGENT_AUTO_ROUTE_ENABLED", "1")
    monkeypatch.setenv("HERMES_ENABLED", "1")
    _use_test_turn_coordinator(monkeypatch, tmp_path)
    session, message = _session("Turn off the kitchen light")
    planner = StaticPlanner(
        ModeChatResponse(
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
        )
    )
    store = DummyStore(session, planner=planner)

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
    assert planner.calls[0]["session_id"] == session.id


def test_hermes_failure_falls_back_to_original_provider_stream(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_LIVE_AGENT_ENABLED", "1")
    monkeypatch.setenv("OMNIX_LIVE_AGENT_AUTO_ROUTE_ENABLED", "1")
    monkeypatch.setenv("HERMES_ENABLED", "1")
    session, message = _session("Schedule a meeting for tomorrow")
    store = DummyStore(
        session,
        planner=StaticPlanner(LiveAgentUnavailable("offline")),
    )
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


def test_typed_chat_fails_closed_when_semantic_parser_is_unavailable(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("OMNIX_LIVE_AGENT_ENABLED", "1")
    monkeypatch.setenv("OMNIX_LIVE_AGENT_AUTO_ROUTE_ENABLED", "1")
    monkeypatch.setenv("HERMES_ENABLED", "1")
    _use_test_turn_coordinator(monkeypatch, tmp_path)
    session, message = _session("Delete the file", voice=False)
    store = DummyStore(session)

    events = list(store.stream_provider_reply_chunks(
        session,
        message,
        provider_id="lmstudio",
        model_id="test-model",
    ))

    completion = next(event for event in events if event["type"] == "complete")
    assert store.provider_calls == 0
    assert "live_agent_route" not in completion["metadata"]
    assert completion["metadata"]["omnix_route"]["lane"] == "chat"
    assert completion["metadata"]["routing_decision"]["production_router"] == "semantic_v2"
    assert completion["metadata"]["semantic_gate"]["reason"] == "semantic_parser_unavailable"
