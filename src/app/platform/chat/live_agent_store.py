"""Explicit Live Agent routing stage for authoritative Chat stores."""
from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Protocol


from app.platform.chat.assist.live_agent import (
    LiveAgentUnavailable,
)
from app.platform.chat.assist.live_agent import (
    LiveAgentRouteDecision,
    live_agent_runtime_config,
    resolve_live_agent_route,
)
from app.platform.chat.assist.modes import ModeChatRequest, plan_mode_chat
from app.capabilities.approvals import ApproverNotAllowed, current_approver
from app.capabilities.executor import CapabilityGrant, execute_capability
from app.security import audit

from .assistant_turns import default_assistant_turn_coordinator
from app.capabilities.executor import live_agent_tools
from .models import ChatMessage, ChatSession
from .store import _pop_ready_sentences
from app.prompts import prompt_template

_PROMPT_1 = prompt_template('chat.live_agent_store.confirmation_prompt', "1", "This will {v0} {v1}. Say 'confirm' to run it or 'cancel' to reject it.")

_CONFIRM = re.compile(
    r"^(?:yes|yes[, ]+do it|confirm|confirmed|approve|go ahead|proceed|do it)[.!\s]*$",
    re.IGNORECASE,
)
_REJECT = re.compile(
    r"^(?:no|nope|cancel|reject|do not|don't do it|never mind|nevermind)[.!\s]*$",
    re.IGNORECASE,
)


class LiveAgentPlanner(Protocol):
    def plan_proposal(
        self,
        *,
        content: str,
        session_id: str,
        context: dict[str, Any],
        timeout_seconds: float,
    ) -> Any: ...


class AssistCoreLiveAgentPlanner:
    """Adapter from the Chat planner port to the Assist Core implementation."""

    def plan_proposal(
        self,
        *,
        content: str,
        session_id: str,
        context: dict[str, Any],
        timeout_seconds: float,
    ) -> Any:
        from app.platform.chat.assist.live_agent import plan_live_agent_proposal

        return plan_live_agent_proposal(
            content=content,
            session_id=session_id,
            context=context,
            timeout_seconds=timeout_seconds,
        )


def _confirmation_grant(session_id: str) -> CapabilityGrant:
    """A chat "confirm" approves the proposal as the confirming user (WP-4.5).

    Without the approval permission the grant stays unapproved, so a call
    that needs approval is refused by the tool policy.
    """
    try:
        approver: str | None = current_approver("tools:approve")
    except ApproverNotAllowed:
        approver = None
    audit.record("approval.decide", target_type="chat_proposal", target_id=session_id,
                 outcome="success" if approver else "denied", details={"decision": "approve"})
    return CapabilityGrant("live_agent", session_id, approved_by=approver)


def default_live_agent_planner() -> LiveAgentPlanner:
    return AssistCoreLiveAgentPlanner()


def stream_live_agent_turn(
    store: Any,
    session: ChatSession,
    user_message: ChatMessage,
    *,
    provider_id: str | None,
    model_id: str | None,
    context_items: list[dict[str, Any]] | None = None,
    routing_deadline_at: float | None = None,
    planner: LiveAgentPlanner,
    original_stream: Callable[..., Iterable[dict[str, Any]]],
):
    def original(
        _store: Any,
        _session: ChatSession,
        _user_message: ChatMessage,
        **kwargs: Any,
    ) -> Iterable[dict[str, Any]]:
        return original_stream(_session, _user_message, **kwargs)

    def wrapped(
        self,
        session: ChatSession,
        user_message: ChatMessage,
        *,
        provider_id: str | None,
        model_id: str | None,
        context_items: list[dict[str, Any]] | None = None,
        routing_deadline_at: float | None = None,
        _original: Callable[..., Iterable[dict[str, Any]]] = original,
        _planner: LiveAgentPlanner = planner,
    ):
        governed_pending = _pending_governed_proposal(session, user_message)
        governed_choice = _confirmation_choice(user_message.content) if governed_pending else None
        if governed_pending and governed_choice in {"approve", "reject"}:
            proposal_message, request = governed_pending
            decided = decide_governed_proposal(
                self, session.id, proposal_message, request,
                choice=governed_choice, user_request=user_message.content,
            )
            # A proposal decided meanwhile (its button, another turn) leaves this turn to the conversation.
            if decided is not None and governed_choice == "approve":
                yield from _governed_execution_events(user_message, decided)
                return
            if decided is not None:
                yield from _governed_rejection_events(user_message, request)
                return

        from app.platform.chat.turn_routing import route_typed_turn

        generalized = route_typed_turn(
            self,
            session,
            user_message,
            provider_id=provider_id,
            model_id=model_id,
            context_items=context_items,
            routing_deadline_at=routing_deadline_at,
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

        # A generalized Chat decision is still a completed routing decision:
        # continue with the provider, but do not let the legacy Live Agent
        # router reinterpret the same user prompt. Preserve pending legacy
        # Kasa confirmations until they have been approved/rejected.
        routed_chat = bool(user_message.metadata.get("omnix_chat_routed"))
        routed_chat_decision = user_message.metadata.get("omnix_route")
        legacy_pending = _pending_kasa_proposal(session, user_message.id)
        if routed_chat and legacy_pending is None:
            _persist_omnix_route(
                self,
                session.id,
                user_message,
                routed_chat_decision,
            )
            original_kwargs: dict[str, Any] = {
                "provider_id": provider_id,
                "model_id": model_id,
                "context_items": context_items,
            }
            if routing_deadline_at is not None:
                original_kwargs["routing_deadline_at"] = routing_deadline_at
            yield from _original(self, session, user_message, **original_kwargs)
            return

        pending = legacy_pending
        choice = _confirmation_choice(user_message.content) if pending else None
        if pending and choice == "approve":
            proposal_message, request = pending
            payload = execute_capability(
                _confirmation_grant(session.id),
                request.model_copy(update={"session_id": session.id}),
                user_request=user_message.content,
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
                response = _planner.plan_proposal(
                    content=_contextual_content(
                        user_message.content,
                        context_items or [],
                    ),
                    session_id=session.id,
                    context={
                        "route_reason": decision.reason,
                        **live_agent_tools().planner_context(),
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
                def persist_fallback_route(fallback_error: str = fallback_error) -> None:
                    _persist_route(self, session.id, user_message, fallback, error=fallback_error)

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
                    persist_route=persist_fallback_route,
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

    yield from wrapped(
        store,
        session,
        user_message,
        provider_id=provider_id,
        model_id=model_id,
        context_items=context_items,
        routing_deadline_at=routing_deadline_at,
    )


def _decision(user_message: ChatMessage) -> LiveAgentRouteDecision:
    requested = user_message.metadata.get("live_agent_route")
    requested_mode: Literal["off", "auto", "agent"] = requested if requested in {"off", "auto", "agent"} else "off"
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
    tools = live_agent_tools()
    tool_proposals = tools.tool_proposals(
        user_request=user_message.content,
        session_id=session_id,
        source_message_id=user_message.id,
        mode_result=payload,
    )
    pending = tools.first_pending_write(
        payload,
        session_id=session_id,
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
            event_metadata = event.get("metadata")
            metadata: dict[str, Any] = event_metadata if isinstance(event_metadata, dict) else {}
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
    _patch_message_metadata(store, session_id, message_id, patch, role="user")


def _persist_omnix_route(
    store,
    session_id: str,
    user_message: ChatMessage,
    route: object,
) -> None:
    if not isinstance(route, dict):
        return
    from app.platform.chat.turn_routing import patch_user_message_metadata

    user_message.metadata["omnix_route"] = route
    patch_user_message_metadata(store, session_id=session_id, message_id=user_message.id, metadata={"omnix_route": route})


def _patch_message_metadata(
    store: Any,
    session_id: str,
    message_id: str,
    patch: dict[str, Any],
    *,
    role: str | None = None,
) -> bool:
    targeted_update = getattr(store, "update_message_metadata", None)
    if callable(targeted_update):
        return bool(
            targeted_update(
                session_id=session_id,
                message_id=message_id,
                metadata=patch,
            )
        )
    session = store.get_session(session_id)
    if session is None:
        return False
    message = next(
        (
            item for item in session.messages
            if item.id == message_id and (role is None or item.role == role)
        ),
        None,
    )
    if message is None:
        return False
    message.metadata.update(patch)
    store._save_session(session)
    return True


def _is_live_call_proposal(message: ChatMessage) -> bool:
    from app.platform.chat.live_call_tasks import is_call_proposal

    return is_call_proposal(message)


def _pending_governed_proposal(
    session: ChatSession,
    user_message: ChatMessage,
) -> tuple[ChatMessage, Any] | None:
    """The proposal this turn may confirm or cancel: the latest pending one.

    A live call's proposal counts only for the turn that answers its question (``proposal_confirmable``); once that
    has passed it has expired, and it still hides older proposals, which the person was not asked about just now.
    """
    from app.platform.chat.live_call_tasks import proposal_confirmable

    for message in reversed(session.messages):
        if message.id == user_message.id or message.role != "assistant":
            continue
        if message.metadata.get("governed_tool_execution_status") != "pending":
            continue
        raw = message.metadata.get("pending_governed_tool_request")
        if not isinstance(raw, dict):
            continue
        if _is_live_call_proposal(message) and not proposal_confirmable(session, message, user_message):
            return None
        try:
            return message, live_agent_tools().parse_request(raw)
        except ValueError:
            continue
    return None


def is_proposal_answer(text: str) -> bool:
    """Whether ``text`` is a confirm or cancel, as a turn would read it."""
    return _confirmation_choice(text) is not None


def has_pending_proposal(session: ChatSession) -> bool:
    """Whether the session holds a pending proposal (governed or legacy Kasa) a confirm could decide.

    Speculation checks this for a confirm or cancel (``is_proposal_answer``): a speculated reply to one must neither
    start nor be accepted, because only the turn itself decides, and a speculated "confirm" would otherwise commit
    a model reply and run nothing. Other remarks speculate as usual.
    """
    if _pending_kasa_proposal(session, "") is not None:
        return True
    return any(message.role == "assistant"
               and message.metadata.get("governed_tool_execution_status") == "pending"
               and isinstance(message.metadata.get("pending_governed_tool_request"), dict)
               for message in session.messages)


@dataclass(frozen=True)
class _NotRunResult:
    result_summary: str
    error: str
    output: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class _NotRun:
    """A confirmed call proposal that did not run: its proposer no longer holds the ability."""

    execution_result: _NotRunResult

    def model_dump(self, mode: str = "python") -> dict[str, Any]:
        return {"execution_result": asdict(self.execution_result)}


def _proposer_granted(proposal_message: ChatMessage) -> bool:
    """A call's proposal runs only while the speaker who proposed it still holds its ability (companion 5.2)."""
    from app.platform.chat.contracts import CHAT_CALL_ACTIONS
    from app.runtime.ports import optional

    action = proposal_message.metadata.get("live_call_action")
    actions = optional(CHAT_CALL_ACTIONS)
    if not isinstance(action, dict) or actions is None:
        return False
    return bool(actions.granted(str(action.get("owner") or ""), capability=str(action.get("capability") or "")))


def decide_governed_proposal(
    store: Any,
    session_id: str,
    proposal_message: ChatMessage,
    request: Any,
    *,
    choice: str,
    user_request: str,
) -> Any:
    """Approve (run) or reject a pending proposal, once. Returns the execution payload on approval, ``True`` on
    rejection, or None when the proposal was no longer pending.

    A live call's proposal is claimed first (``claim_message_metadata``: pending → executing or rejected), so a
    spoken confirm and its button never both run it. A crash after the claim leaves ``executing``, shown as unknown
    and never re-run, since the action may have happened.
    """
    rejected = {"tool_id": request.tool_id, "action_id": request.action_id}
    if _is_live_call_proposal(proposal_message):
        claim = getattr(store, "claim_message_metadata", None)
        status = "executing" if choice == "approve" else "rejected"
        patch: dict[str, Any] = {"governed_tool_execution_status": status,
                                 "governed_tool_execution_updated_at": datetime.now(timezone.utc).isoformat()}
        if choice != "approve":
            patch["governed_tool_execution_result"] = rejected
        if not callable(claim) or not claim(session_id=session_id, message_id=proposal_message.id,
                                            require={"governed_tool_execution_status": "pending"}, patch=patch):
            return None
        if choice != "approve":
            return True
    elif choice != "approve":
        _mark_governed_proposal(store, session_id, proposal_message.id, status="rejected", result=rejected)
        return True
    if _is_live_call_proposal(proposal_message) and not _proposer_granted(proposal_message):
        # Claimed above, so it is never run later either; the person hears why nothing happened.
        payload: Any = _NotRun(_NotRunResult(result_summary="Nothing was changed.",
                                             error="That is no longer allowed for whoever proposed it."))
    else:
        payload = execute_capability(
            _confirmation_grant(session_id),
            request.model_copy(update={"session_id": session_id}),
            user_request=user_request,
        )
    status = "executed" if payload.execution_result.error is None else "failed"
    _mark_governed_proposal(store, session_id, proposal_message.id, status=status,
                            result=payload.model_dump(mode="json"))
    return payload


def _mark_governed_proposal(
    store,
    session_id: str,
    assistant_message_id: str,
    *,
    status: str,
    result: dict[str, Any],
) -> None:
    _patch_message_metadata(
        store,
        session_id,
        assistant_message_id,
        {
            "governed_tool_execution_status": status,
            "governed_tool_execution_result": result,
            "governed_tool_execution_updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )


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


def execution_text(payload: Any) -> str:
    """What a confirmed proposal's run says, built from its result."""
    result = payload.execution_result
    content = result.result_summary or ("Governed action failed." if result.error else "Governed action completed.")
    return f"{content} {result.error}".strip() if result.error else content


def rejection_text(request: Any) -> str:
    return f"Cancelled. I did not execute {request.action_id}."


def _governed_execution_events(user_message: ChatMessage, payload):
    coordinator = default_assistant_turn_coordinator()
    assistant_turn_id = str(user_message.metadata.get("assistant_turn_id") or "").strip()
    if assistant_turn_id:
        coordinator.mark_streaming(assistant_turn_id)
    result = payload.execution_result
    content = execution_text(payload)
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
                "assistant_turn_id": assistant_turn_id or None,
                "agent_mode": False,
                "live_agent": False,
                "review_required": False,
                "executes": result.error is None,
                "direct_execution": payload.model_dump(mode="json"),
            },
        }
    except GeneratorExit:
        if assistant_turn_id:
            coordinator.request_cancel(assistant_turn_id, "client_disconnected")
            coordinator.mark_provider_cancelled(assistant_turn_id)
        raise


def _governed_rejection_events(user_message: ChatMessage, request: Any):
    coordinator = default_assistant_turn_coordinator()
    assistant_turn_id = str(user_message.metadata.get("assistant_turn_id") or "").strip()
    if assistant_turn_id:
        coordinator.mark_streaming(assistant_turn_id)
    content = rejection_text(request)
    if assistant_turn_id and coordinator.is_cancelled(assistant_turn_id):
        yield _interrupted(assistant_turn_id, "")
        return
    yield {"type": "text_chunk", "text": content}
    yield {
        "type": "complete",
        "content": content,
        "metadata": {
            "generation_status": "completed",
            "assistant_turn_id": assistant_turn_id or None,
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
) -> tuple[ChatMessage, Any] | None:
    for message in reversed(session.messages):
        if message.id == current_user_message_id or message.role != "assistant":
            continue
        if message.metadata.get("kasa_execution_status") != "pending":
            continue
        raw = message.metadata.get("pending_tool_request")
        if not isinstance(raw, dict):
            continue
        try:
            request = live_agent_tools().parse_request(raw)
        except ValueError:
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
    _patch_message_metadata(
        store,
        session_id,
        assistant_message_id,
        {
            "kasa_execution_status": status,
            "kasa_execution_result": result,
            "kasa_execution_updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )


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
    request: Any,
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


def _confirmation_prompt(request: Any) -> str:
    action = "turn on" if request.action_id == "kasa.turn_on" else "turn off"
    target = str(request.input.get("target") or "the selected Kasa plug")
    return (
        _PROMPT_1.format(v0=(action), v1=(target))
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
