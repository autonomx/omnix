from __future__ import annotations

from datetime import datetime, timezone

from app.assist_core.mode_chat import ModeChatResponse
from app.assistant_tools.hermes_payloads import HermesAssistantToolExecutePayload
from app.assistant_tools.models import (
    AssistantToolRequest,
    AssistantToolResult,
    AssistantToolReviewDecision,
)
from app.chat.live_agent_store import install_live_agent_store_hooks
from app.chat.models import ChatMessage, ChatSession


class KasaFlowStore:
    def __init__(self, session: ChatSession) -> None:
        self.sessions = [session]
        self.provider_calls = 0

    def _load_sessions(self):
        return self.sessions

    def _save_sessions(self, sessions):
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
            "metadata": {"generation_status": "completed"},
        }


def _message(message_id: str, content: str) -> ChatMessage:
    now = datetime.now(timezone.utc).isoformat()
    return ChatMessage(
        id=message_id,
        role="user",
        content=content,
        created_at=now,
        metadata={
            "assistant_turn_id": f"assistant-turn:{message_id}",
            "assistant_turn": {"session_id": "chat:kasa"},
            "user_turn_id": f"voice-user-turn:{message_id}",
            "speech_segment_id": f"voice-segment:{message_id}",
        },
    )


def _session(message: ChatMessage) -> ChatSession:
    now = datetime.now(timezone.utc).isoformat()
    return ChatSession(
        id="chat:kasa",
        title="Kasa",
        messages=[message],
        message_count=1,
        created_at=now,
        updated_at=now,
    )


def _proposal_response() -> ModeChatResponse:
    return ModeChatResponse(
        ok=True,
        mode="agent",
        backend="hermes",
        result={
            "success": True,
            "response": "I prepared a Kasa plug power change.",
            "domain": "house",
            "tool_calls": [
                {
                    "name": "kasa_turn_off",
                    "args": {"target": "Desk Plug"},
                    "risk": "medium",
                    "reason": "User requested the plug be turned off.",
                }
            ],
            "tool_results": [],
            "requires_confirmation": True,
            "error": None,
        },
    )


def _execution_payload(request: AssistantToolRequest) -> HermesAssistantToolExecutePayload:
    return HermesAssistantToolExecutePayload(
        user_request="confirm",
        selected_tool_id="kasa",
        selected_action_id=request.action_id,
        approval_decision=AssistantToolReviewDecision(
            tool_id="kasa",
            action_id=request.action_id,
            session_id=request.session_id,
            allowed=True,
            executable=True,
            approval_required=True,
            risk_level="medium",
            state_changed=True,
            result_summary="Approved and ready to run Turn off plug.",
        ),
        execution_result=AssistantToolResult(
            tool_id="kasa",
            action_id=request.action_id,
            session_id=request.session_id,
            risk_level="medium",
            state_changed=True,
            result_summary="Verified Desk Plug is off.",
            output={
                "before": {"alias": "Desk Plug", "is_on": True},
                "after": {"alias": "Desk Plug", "is_on": False},
                "verified": True,
            },
        ),
        state_changed=True,
    )


def test_kasa_write_proposal_requires_next_turn_confirmation(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_LIVE_AGENT_ENABLED", "1")
    monkeypatch.setenv("OMNIX_LIVE_AGENT_AUTO_ROUTE_ENABLED", "1")
    monkeypatch.setenv("HERMES_ENABLED", "1")
    first = _message("request", "Turn off the Kasa desk plug")
    session = _session(first)
    store = KasaFlowStore(session)
    install_live_agent_store_hooks(KasaFlowStore)
    monkeypatch.setattr(
        "app.chat.live_agent_store.plan_live_agent_proposal",
        lambda **kwargs: _proposal_response(),
    )

    proposal_events = list(
        store.stream_provider_reply_chunks(
            session,
            first,
            provider_id="lmstudio",
            model_id="test-model",
        )
    )
    proposal = next(event for event in proposal_events if event["type"] == "complete")
    assert proposal["metadata"]["review_required"] is True
    assert proposal["metadata"]["executes"] is False
    assert proposal["metadata"]["pending_tool_request"]["action_id"] == "kasa.turn_off"
    assert "Say 'confirm'" in proposal["content"]

    assistant = ChatMessage(
        id="msg:proposal",
        role="assistant",
        content=proposal["content"],
        created_at=datetime.now(timezone.utc).isoformat(),
        metadata=proposal["metadata"],
    )
    session.messages.append(assistant)
    confirm = _message("confirm", "confirm")
    session.messages.append(confirm)
    captured: list[AssistantToolRequest] = []

    def execute(user_request: str, request: AssistantToolRequest):
        captured.append(request)
        return _execution_payload(request)

    monkeypatch.setattr("app.chat.live_agent_store.hermes_assistant_tool_execute_payload", execute)
    execution_events = list(
        store.stream_provider_reply_chunks(
            session,
            confirm,
            provider_id="lmstudio",
            model_id="test-model",
        )
    )
    completed = next(event for event in execution_events if event["type"] == "complete")

    assert captured[0].approved is True
    assert captured[0].action_id == "kasa.turn_off"
    assert captured[0].session_id == "chat:kasa"
    assert completed["content"] == "Verified Desk Plug is off."
    assert completed["metadata"]["executes"] is True
    assert assistant.metadata["kasa_execution_status"] == "executed"

    duplicate = _message("duplicate", "confirm")
    session.messages.append(duplicate)
    list(
        store.stream_provider_reply_chunks(
            session,
            duplicate,
            provider_id="lmstudio",
            model_id="test-model",
        )
    )
    assert len(captured) == 1
    assert store.provider_calls == 1


def test_kasa_write_proposal_can_be_rejected_without_execution(monkeypatch) -> None:
    request = AssistantToolRequest(
        tool_id="kasa",
        action_id="kasa.turn_on",
        session_id="chat:kasa",
        input={"target": "Desk Plug"},
    )
    proposal = ChatMessage(
        id="msg:proposal",
        role="assistant",
        content="Confirm this Kasa change.",
        created_at=datetime.now(timezone.utc).isoformat(),
        metadata={
            "pending_tool_request": request.model_dump(mode="json"),
            "kasa_execution_status": "pending",
        },
    )
    reject = _message("reject", "cancel")
    session = _session(reject)
    session.messages = [proposal, reject]
    store = KasaFlowStore(session)
    install_live_agent_store_hooks(KasaFlowStore)
    monkeypatch.setattr(
        "app.chat.live_agent_store.hermes_assistant_tool_execute_payload",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not execute")),
    )

    events = list(
        store.stream_provider_reply_chunks(
            session,
            reject,
            provider_id="lmstudio",
            model_id="test-model",
        )
    )
    completed = next(event for event in events if event["type"] == "complete")

    assert completed["content"] == "Cancelled. I did not change the Kasa plug."
    assert completed["metadata"]["executes"] is False
    assert proposal.metadata["kasa_execution_status"] == "rejected"
    assert store.provider_calls == 0
