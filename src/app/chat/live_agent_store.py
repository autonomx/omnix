"""Install governed Live Agent routing around authoritative Chat stores."""
from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from app.assist_core.live_agent_planner import (
    LiveAgentUnavailable,
    plan_live_agent_proposal,
)
from app.assist_core.live_agent_router import (
    LiveAgentRouteDecision,
    live_agent_runtime_config,
    resolve_live_agent_route,
)
from app.assist_core.mode_chat import ModeChatRequest, plan_mode_chat
from app.assistant_tools.hermes_bridge import hermes_assistant_tool_execute_payload
from app.assistant_tools.kasa_plan import first_pending_kasa_write
from app.assistant_tools.live_agent_proposals import (
    live_agent_planner_context,
    live_agent_tool_proposals,
)
from app.assistant_tools.models import AssistantToolRequest

from .assistant_turns import default_assistant_turn_coordinator
from .models import ChatMessage, ChatSession
from .store import _pop_ready_sentences

_HOOK = "_omnix_live_agent_stream_installed"
_CONFIRM = re.compile(
    r"^(?:yes|yes[, ]+do it|confirm|confirmed|approve|go ahead|proceed|do it)[.!\s]*$",
    re.IGNORECASE,
)
_REJECT = re.compile(
    r"^(?:no|nope|cancel|reject|do not|don't do it|never mind|nevermind)[.!\s]*$",
    re.IGNORECASE,
)


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
            governed_pending = _pending_governed_proposal(session, user_message.id)
            governed_choice = _confirmation_choice(user_message.content) if governed_pending else None
            if governed_pending and governed_choice == "approve":
                proposal_message, request = governed_pending
                payload = hermes_assistant_tool_execute_payload(
                    user_message.content,
                    request.model_copy(update={"approved": True, "session_id": session.id}),
                )
                status = "executed" if payload.execution_result.error is None else "failed"
                _mark_governed_proposal(
                    self,
                    session.id,
                    proposal_message.id,
                    status=status,
                    result=payload.model_dump(mode="json"),
                )
                yield from _governed_execution_events(user_message, payload)
                return
            if governed_pending and governed_choice == "reject":
                proposal_message, request = governed_pending
                _mark_governed_proposal(
                    self,
                    session.id,
                    proposal_message.id,
                    status="rejected",
                    result={"tool_id": request.tool_id, "action_id": request.action_id},
                )
                yield from _governed_rejection_events(user_message, request)
                return

            from app.agent_runtime.chat_bridge import route_typed_chat_turn

            generalized = route_typed_chat_turn(
                session,
                user_message,
                provider_id=provider_id,
                model_id=model_id,
                context_items=context_items,
            )
            if generalized is not None:
                _persist_omnix_route(
                    self,
                    session.id,
                    user_message,
                    generalized.metadata.get("omnix_route"),
                )
                yield from _generalized_result_events(user_message, generalized.content, generalized.metadata)
                return

            pending = _pending_kasa_proposal(session, user_message.id)
            choice = _confirmation_choice(user_message.content) if pending else None
            if pending and choice == "approve":
                proposal_message, request = pending
                payload = hermes_assistant_tool_execute_payload(
                    user_message.content,
                    request.model_copy(update={"approved": True, "session_id": session.id}),
                )
                status = "executed" if payload.execution_result.error is None else "failed"
                _mark_kasa_proposal(
                    self,
                    session.id,
                    proposal_message.id,
                    status=status,
                    result=payload.model_dump(mode="json"),
                )
                yield from _kasa_execution_events(user_message, payload)
                return
            if pending and choice == "reject":
                proposal_message, request = pending
                _mark_kasa_proposal(
                    self,
                    session.id,
                    proposal_message.id,
                    status="rejected",
                    result={"tool_id": request.tool_id, "action_id": request.action_id},
                )
                yield from _kasa_rejection_events(user_message, request)
                return

            decision = _decision(user_message)
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
                    persist_route=lambda: _persist_route(
                        self,
                        session.id,
                        user_message,
                        decision,
                    ),
                )
                return

            _persist_route(self, session.id, user_message, decision)
            if decision.automatic:
                try:
                    response = plan_live_agent_proposal(
                        content=_contextual_content(
                            user_message.content,
                            context_items or [],
                        ),
                        session_id=session.id,
                        context={
                            "route_reason": decision.reason,
                            **live_agent_planner_context(),
                        },
                        timeout_seconds=(
                            live_agent_runtime_config().planner_timeout_seconds
                        ),
                    )
                except LiveAgentUnavailable as exc:
                    fallback_error = str(exc)
                    fallback = decision.model_copy(
                        update={
                            "route": "direct_chat",
                            "reason": "hermes_unavailable_fallback",
                            "review_required": False,
                        }
                    )
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
                        error=fallback_error,
                        persist_route=lambda fallback_error=fallback_error: _persist_route(
                            self,
                            session.id,
                            user_message,
                            fallback,
                            error=fallback_error,
                        ),
                    )
                    return
            else:
                response = plan_mode_chat(
                    ModeChatRequest(
                        content=_contextual_content(
                            user_message.content,
                            context_items or [],
                        ),
                        session_id=session.id,
                        dry_run=True,
                        metadata={
                            "source": "explicit_live_agent",
                            "proposal_only": True,
                        },
                    )
                )
            yield from _agent_events(
                user_message,
                decision,
                response,
                session_id=session.id,
            )

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
        speech_segment_id=(
            str(user_message.metadata.get("speech_segment_id") or "") or None
        ),
    )


def _agent_events(
    user_message: ChatMessage,
    decision: LiveAgentRouteDecision,
    response,
    *,
    session_id: str,
):
    coordinator = default_assistant_turn_coordinator()
    assistant_turn_id = str(
        user_message.metadata.get("assistant_turn_id") or ""
    ).strip()
    if assistant_turn_id:
        coordinator.mark_streaming(assistant_turn_id)
    payload = response.result
    tool_proposals = live_agent_tool_proposals(
        user_request=user_message.content,
        session_id=session_id,
        source_message_id=user_message.id,
        mode_result=payload,
    )
    pending = first_pending_kasa_write(
        payload,
        session_id=session_id,
        approved=False,
    )
    read_executed = any(
        bool(row.get("executed"))
        for row in payload.get("tool_results", [])
        if isinstance(row, dict)
    )
    review_required = pending is not None or bool(payload.get("requires_confirmation"))
    proposal_only = review_required or not read_executed
    content = str(
        payload.get("response") or "Live Agent returned no proposal."
    ).strip()
    if pending is not None:
        content = f"{content} {_confirmation_prompt(pending)}".strip()
    try:
        if assistant_turn_id and coordinator.is_cancelled(assistant_turn_id):
            yield _interrupted(assistant_turn_id, "")
            return
        pending_text = content
        ready, pending_text = _pop_ready_sentences(pending_text)
        emitted: list[str] = []
        for sentence in ready:
            if assistant_turn_id and coordinator.is_cancelled(assistant_turn_id):
                yield _interrupted(assistant_turn_id, " ".join(emitted))
                return
            emitted.append(sentence)
            yield {"type": "text_chunk", "text": sentence}
        if pending_text.strip():
            if assistant_turn_id and coordinator.is_cancelled(assistant_turn_id):
                yield _interrupted(assistant_turn_id, " ".join(emitted))
                return
            yield {"type": "text_chunk", "text": pending_text.strip()}
        yield {
            "type": "complete",
            "content": content,
            "metadata": {
                "generation_status": "completed",
                "agent_mode": True,
                "live_agent": True,
                "backend": response.backend,
                "mode_result": payload,
                "assistant_tool_proposals": tool_proposals,
                "error": response.error,
                "proposal_only": proposal_only,
                "review_required": review_required,
                "executes": read_executed,
                "pending_tool_request": (
                    pending.model_dump(mode="json") if pending else None
                ),
                "kasa_execution_status": "pending" if pending else None,
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
    persist_route: Callable[[], None] | None = None,
):
    for event in events:
        if event.get("type") == "complete":
            if persist_route is not None:
                persist_route()
                persist_route = None
            metadata = (
                event.get("metadata")
                if isinstance(event.get("metadata"), dict)
                else {}
            )
            event = {
                **event,
                "metadata": {
                    **metadata,
                    "live_agent": False,
                    "live_agent_route": decision.model_dump(mode="json"),
                    **(
                        {"live_agent_fallback_error": error[:500]}
                        if error
                        else {}
                    ),
                },
            }
        yield event


def _persist_route(
    store,
    session_id: str,
    user_message: ChatMessage,
    decision: LiveAgentRouteDecision,
    *,
    error: str | None = None,
) -> None:
    message_id = user_message.id
    patch: dict[str, object] = {
        "live_agent_route": decision.model_dump(mode="json"),
        "agent_mode": decision.route == "agent_plan",
        "dry_run": decision.route == "agent_plan",
    }
    if error:
        patch["live_agent_fallback_error"] = error[:500]
    # The provider-completion boundary must not load and rewrite every chat just
    # to annotate the accepted user turn. Keep the in-flight message aligned
    # with the targeted PostgreSQL write so terminal persistence keeps the same
    # metadata without delaying the final stream event.
    user_message.metadata.update(patch)
    targeted_update = getattr(store, "update_user_message_metadata", None)
    if callable(targeted_update):
        targeted_update(
            session_id=session_id,
            message_id=message_id,
            metadata=patch,
        )
        return
    sessions = store._load_sessions()
    for index, session in enumerate(sessions):
        if session.id != session_id:
            continue
        for message in session.messages:
            if message.id != message_id:
                continue
            message.metadata.update(patch)
            break
        sessions[index] = session
        store._save_sessions(sessions)
        return


def _persist_omnix_route(
    store,
    session_id: str,
    user_message: ChatMessage,
    route: object,
) -> None:
    if not isinstance(route, dict):
        return
    patch: dict[str, object] = {"omnix_route": route}
    user_message.metadata.update(patch)
    targeted_update = getattr(store, "update_user_message_metadata", None)
    if callable(targeted_update):
        targeted_update(session_id=session_id, message_id=user_message.id, metadata=patch)
        return
    sessions = store._load_sessions()
    for index, session in enumerate(sessions):
        if session.id != session_id:
            continue
        for message in session.messages:
            if message.id == user_message.id:
                message.metadata.update(patch)
                break
        sessions[index] = session
        store._save_sessions(sessions)
        return


def _pending_governed_proposal(
    session: ChatSession,
    current_user_message_id: str,
) -> tuple[ChatMessage, AssistantToolRequest] | None:
    for message in reversed(session.messages):
        if message.id == current_user_message_id or message.role != "assistant":
            continue
        if message.metadata.get("governed_tool_execution_status") != "pending":
            continue
        raw = message.metadata.get("pending_governed_tool_request")
        if not isinstance(raw, dict):
            continue
        try:
            return message, AssistantToolRequest.model_validate(raw)
        except ValidationError:
            continue
    return None


def _mark_governed_proposal(
    store,
    session_id: str,
    assistant_message_id: str,
    *,
    status: str,
    result: dict[str, Any],
) -> None:
    sessions = store._load_sessions()
    for index, session in enumerate(sessions):
        if session.id != session_id:
            continue
        for message in session.messages:
            if message.id != assistant_message_id:
                continue
            message.metadata["governed_tool_execution_status"] = status
            message.metadata["governed_tool_execution_result"] = result
            message.metadata["governed_tool_execution_updated_at"] = datetime.now(timezone.utc).isoformat()
            break
        sessions[index] = session
        store._save_sessions(sessions)
        return


def _generalized_result_events(
    user_message: ChatMessage,
    content: str,
    metadata: dict[str, Any],
):
    coordinator = default_assistant_turn_coordinator()
    assistant_turn_id = str(user_message.metadata.get("assistant_turn_id") or "").strip()
    if assistant_turn_id:
        coordinator.mark_streaming(assistant_turn_id)
    if assistant_turn_id and coordinator.is_cancelled(assistant_turn_id):
        yield _interrupted(assistant_turn_id, "")
        return
    pending_text = content
    ready, pending_text = _pop_ready_sentences(pending_text)
    emitted: list[str] = []
    for sentence in ready:
        if assistant_turn_id and coordinator.is_cancelled(assistant_turn_id):
            yield _interrupted(assistant_turn_id, " ".join(emitted))
            return
        emitted.append(sentence)
        yield {"type": "text_chunk", "text": sentence}
    if pending_text.strip():
        yield {"type": "text_chunk", "text": pending_text.strip()}
    yield {
        "type": "complete",
        "content": content,
        "metadata": {
            **metadata,
            "assistant_turn_id": assistant_turn_id or None,
            "live_agent": False,
        },
    }


def _governed_execution_events(user_message: ChatMessage, payload):
    result = payload.execution_result
    content = result.result_summary or ("Governed action failed." if result.error else "Governed action completed.")
    if result.error:
        content = f"{content} {result.error}".strip()
    yield {"type": "text_chunk", "text": content}
    yield {
        "type": "complete",
        "content": content,
        "metadata": {
            "generation_status": "completed",
            "agent_mode": False,
            "live_agent": False,
            "review_required": False,
            "executes": result.error is None,
            "direct_execution": payload.model_dump(mode="json"),
        },
    }


def _governed_rejection_events(user_message: ChatMessage, request: AssistantToolRequest):
    del user_message
    content = f"Cancelled. I did not execute {request.action_id}."
    yield {"type": "text_chunk", "text": content}
    yield {
        "type": "complete",
        "content": content,
        "metadata": {
            "generation_status": "completed",
            "agent_mode": False,
            "live_agent": False,
            "review_required": False,
            "executes": False,
            "tool_request": request.model_dump(mode="json"),
            "direct_execution": {"status": "rejected"},
        },
    }


def _pending_kasa_proposal(
    session: ChatSession,
    current_user_message_id: str,
) -> tuple[ChatMessage, AssistantToolRequest] | None:
    for message in reversed(session.messages):
        if message.id == current_user_message_id or message.role != "assistant":
            continue
        if message.metadata.get("kasa_execution_status") != "pending":
            continue
        raw = message.metadata.get("pending_tool_request")
        if not isinstance(raw, dict):
            continue
        try:
            request = AssistantToolRequest.model_validate(raw)
        except ValidationError:
            continue
        if request.tool_id == "kasa" and request.action_id in {
            "kasa.turn_on",
            "kasa.turn_off",
        }:
            return message, request
    return None


def _mark_kasa_proposal(
    store,
    session_id: str,
    assistant_message_id: str,
    *,
    status: str,
    result: dict[str, Any],
) -> None:
    sessions = store._load_sessions()
    for index, session in enumerate(sessions):
        if session.id != session_id:
            continue
        for message in session.messages:
            if message.id != assistant_message_id:
                continue
            message.metadata["kasa_execution_status"] = status
            message.metadata["kasa_execution_result"] = result
            message.metadata["kasa_execution_updated_at"] = datetime.now(
                timezone.utc
            ).isoformat()
            break
        sessions[index] = session
        store._save_sessions(sessions)
        return


def _kasa_execution_events(user_message: ChatMessage, payload):
    coordinator = default_assistant_turn_coordinator()
    assistant_turn_id = str(
        user_message.metadata.get("assistant_turn_id") or ""
    ).strip()
    if assistant_turn_id:
        coordinator.mark_streaming(assistant_turn_id)
    result = payload.execution_result
    content = result.result_summary or (
        "Kasa action failed." if result.error else "Kasa action completed."
    )
    if result.error:
        content = f"{content} {result.error}".strip()
    try:
        if assistant_turn_id and coordinator.is_cancelled(assistant_turn_id):
            yield _interrupted(assistant_turn_id, "")
            return
        yield {"type": "text_chunk", "text": content}
        yield {
            "type": "complete",
            "content": content,
            "metadata": {
                "generation_status": "completed",
                "agent_mode": True,
                "live_agent": True,
                "backend": "omnix_kasa",
                "proposal_only": False,
                "review_required": False,
                "executes": result.error is None,
                "tool_execution": payload.model_dump(mode="json"),
            },
        }
    except GeneratorExit:
        if assistant_turn_id:
            coordinator.request_cancel(assistant_turn_id, "client_disconnected")
            coordinator.mark_provider_cancelled(assistant_turn_id)
        raise


def _kasa_rejection_events(
    user_message: ChatMessage,
    request: AssistantToolRequest,
):
    assistant_turn_id = str(
        user_message.metadata.get("assistant_turn_id") or ""
    ).strip()
    content = "Cancelled. I did not change the Kasa plug."
    yield {"type": "text_chunk", "text": content}
    yield {
        "type": "complete",
        "content": content,
        "metadata": {
            "generation_status": "completed",
            "assistant_turn_id": assistant_turn_id or None,
            "agent_mode": True,
            "live_agent": True,
            "backend": "omnix_kasa",
            "proposal_only": False,
            "review_required": False,
            "executes": False,
            "tool_request": request.model_dump(mode="json"),
            "tool_execution": {"status": "rejected"},
        },
    }


def _confirmation_choice(content: str) -> str | None:
    text = " ".join(str(content or "").strip().split())
    if _CONFIRM.fullmatch(text):
        return "approve"
    if _REJECT.fullmatch(text):
        return "reject"
    return None


def _confirmation_prompt(request: AssistantToolRequest) -> str:
    action = "turn on" if request.action_id == "kasa.turn_on" else "turn off"
    target = str(request.input.get("target") or "the selected Kasa plug")
    return (
        f"This will {action} {target}. "
        "Say 'confirm' to run it or 'cancel' to reject it."
    )


def _contextual_content(
    content: str,
    context_items: list[dict[str, Any]],
) -> str:
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
