"""Install proposal-only Live Agent routing around authoritative Chat stores."""
from __future__ import annotations

from typing import Any, Callable, Iterable

from app.assist_core.live_agent_planner import LiveAgentUnavailable, plan_live_agent_proposal
from app.assist_core.live_agent_router import (
    LiveAgentRouteDecision,
    live_agent_runtime_config,
    resolve_live_agent_route,
)
from app.assist_core.mode_chat import ModeChatRequest, plan_mode_chat

from .assistant_turns import default_assistant_turn_coordinator
from .models import ChatMessage, ChatSession
from .store import _pop_ready_sentences

_HOOK = "_omnix_live_agent_stream_installed"


def install_live_agent_store_hooks(*store_classes: type) -> None:
    for store_class in store_classes:
        if getattr(store_class, _HOOK, False):
            continue
        original = store_class.stream_provider_reply_chunks

        def wrapped(
            self,
            session: ChatSession,
            user_message: ChatMessage,
            *,
            provider_id: str | None,
            model_id: str | None,
            context_items: list[dict[str, Any]] | None = None,
            _original: Callable[..., Iterable[dict[str, Any]]] = original,
        ):
            decision = _decision(user_message)
            _persist_route(self, session.id, user_message.id, decision)
            if decision.route != "agent_plan":
                yield from _provider_with_route(
                    _original(
                        self,
                        session,
                        user_message,
                        provider_id=provider_id,
                        model_id=model_id,
                        context_items=context_items,
                    ),
                    decision,
                )
                return
            if decision.automatic:
                try:
                    response = plan_live_agent_proposal(
                        content=_contextual_content(user_message.content, context_items or []),
                        session_id=session.id,
                        context={"route_reason": decision.reason},
                        timeout_seconds=live_agent_runtime_config().planner_timeout_seconds,
                    )
                except LiveAgentUnavailable as exc:
                    fallback = decision.model_copy(update={
                        "route": "direct_chat",
                        "reason": "hermes_unavailable_fallback",
                        "review_required": False,
                    })
                    _persist_route(self, session.id, user_message.id, fallback, error=str(exc))
                    yield from _provider_with_route(
                        _original(
                            self,
                            session,
                            user_message,
                            provider_id=provider_id,
                            model_id=model_id,
                            context_items=context_items,
                        ),
                        fallback,
                        error=str(exc),
                    )
                    return
            else:
                response = plan_mode_chat(ModeChatRequest(
                    content=_contextual_content(user_message.content, context_items or []),
                    session_id=session.id,
                    dry_run=True,
                    metadata={"source": "explicit_live_agent", "proposal_only": True},
                ))
            yield from _agent_events(user_message, decision, response)

        store_class.stream_provider_reply_chunks = wrapped
        setattr(store_class, _HOOK, True)


def _decision(user_message: ChatMessage) -> LiveAgentRouteDecision:
    requested = user_message.metadata.get("live_agent_route")
    requested_mode = requested if requested in {"off", "auto", "agent"} else "off"
    return resolve_live_agent_route(
        content=user_message.content,
        requested_mode=requested_mode,
        agent_mode=bool(user_message.metadata.get("agent_mode")),
        user_turn_id=str(user_message.metadata.get("user_turn_id") or "") or None,
        speech_segment_id=str(user_message.metadata.get("speech_segment_id") or "") or None,
    )


def _agent_events(user_message: ChatMessage, decision: LiveAgentRouteDecision, response):
    coordinator = default_assistant_turn_coordinator()
    assistant_turn_id = str(user_message.metadata.get("assistant_turn_id") or "").strip()
    if assistant_turn_id:
        coordinator.mark_streaming(assistant_turn_id)
    payload = response.result
    content = str(payload.get("response") or "Live Agent returned no proposal.").strip()
    try:
        if assistant_turn_id and coordinator.is_cancelled(assistant_turn_id):
            yield _interrupted(assistant_turn_id, "")
            return
        pending = content
        ready, pending = _pop_ready_sentences(pending)
        for sentence in ready:
            if assistant_turn_id and coordinator.is_cancelled(assistant_turn_id):
                yield _interrupted(assistant_turn_id, " ".join(ready[:ready.index(sentence)]))
                return
            yield {"type": "text_chunk", "text": sentence}
        if pending.strip():
            if assistant_turn_id and coordinator.is_cancelled(assistant_turn_id):
                yield _interrupted(assistant_turn_id, " ".join(ready))
                return
            yield {"type": "text_chunk", "text": pending.strip()}
        yield {
            "type": "complete",
            "content": content,
            "metadata": {
                "generation_status": "completed",
                "agent_mode": True,
                "live_agent": True,
                "backend": response.backend,
                "mode_result": payload,
                "error": response.error,
                "proposal_only": True,
                "review_required": True,
                "executes": False,
                "live_agent_route": decision.model_dump(mode="json"),
            },
        }
    except GeneratorExit:
        if assistant_turn_id:
            coordinator.request_cancel(assistant_turn_id, "client_disconnected")
            coordinator.mark_provider_cancelled(assistant_turn_id)
        raise


def _provider_with_route(
    events: Iterable[dict[str, Any]],
    decision: LiveAgentRouteDecision,
    *,
    error: str | None = None,
):
    for event in events:
        if event.get("type") == "complete":
            metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
            event = {
                **event,
                "metadata": {
                    **metadata,
                    "live_agent": False,
                    "live_agent_route": decision.model_dump(mode="json"),
                    **({"live_agent_fallback_error": error[:500]} if error else {}),
                },
            }
        yield event


def _persist_route(
    store,
    session_id: str,
    message_id: str,
    decision: LiveAgentRouteDecision,
    *,
    error: str | None = None,
) -> None:
    sessions = store._load_sessions()
    for index, session in enumerate(sessions):
        if session.id != session_id:
            continue
        for message in session.messages:
            if message.id != message_id:
                continue
            message.metadata["live_agent_route"] = decision.model_dump(mode="json")
            message.metadata["agent_mode"] = decision.route == "agent_plan"
            message.metadata["dry_run"] = decision.route == "agent_plan"
            if error:
                message.metadata["live_agent_fallback_error"] = error[:500]
            break
        sessions[index] = session
        store._save_sessions(sessions)
        return


def _contextual_content(content: str, context_items: list[dict[str, Any]]) -> str:
    if not context_items:
        return content
    sources = [
        {
            "source_id": str(item.get("source_id") or "context"),
            "title": str(item.get("title") or "context"),
        }
        for item in context_items
    ]
    return f"User request: {content}\nAvailable untrusted context sources: {sources}"


def _interrupted(assistant_turn_id: str, content: str) -> dict[str, Any]:
    return {
        "type": "complete",
        "content": content.strip(),
        "metadata": {
            "generation_status": "interrupted",
            "delivery_status": "interrupted",
            "assistant_turn_id": assistant_turn_id,
            "agent_mode": True,
            "live_agent": True,
            "proposal_only": True,
            "review_required": True,
            "executes": False,
        },
    }
