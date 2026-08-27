"""Converge typed Omnix Chat onto the generalized execution lanes.

Live voice keeps the existing latency-optimized Live Agent path. Typed requests
may enter DIRECT or a known WORKFLOW automatically. Open-ended AGENT execution
requires the existing Agent Chat toggle or an explicit /agent-style request.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
import re
from typing import Any

from app.assistant_tools.gate import review_assistant_tool_request
from app.assistant_tools.hermes_bridge import hermes_assistant_tool_execute_payload
from app.assistant_tools.models import AssistantToolRequest

from .contracts import AgentRunCommand, AgentRunSpec, ModelRef, SuccessCriterion, WorkspaceSpec
from .profiles import get_agent_profile, resolve_profile_capabilities
from .router import OmnixRouteDecision, route_omnix_request
from .service import default_agent_run_service
from .workflow_runtime import default_workflow_runtime


@dataclass(frozen=True)
class GeneralizedChatResult:
    content: str
    metadata: dict[str, Any]


_TERMINAL_AGENT = {"completed", "failed", "cancelled"}
_HOME_SET = re.compile(r"\bturn\s+(on|off)\s+(?:the\s+)?(.+?)[.!?]*$", re.I)
_HOME_STATE = re.compile(r"\b(?:status|state)\s*(?:of|for)?\s*(?:the\s+)?(.+?)[.!?]*$", re.I)
_CODE = re.compile(r"\b(?:code|repo|repository|branch|pull request|bug|test|refactor|implement|fix|debug)\b", re.I)
_HOME = re.compile(r"\b(?:kasa|smart\s+plug|plug|outlet|lamp|light|thermostat|home)\b", re.I)
_PERSONAL = re.compile(r"\b(?:gmail|email|calendar|meeting|contact|appointment|schedule)\b", re.I)
_TRADING = re.compile(r"\b(?:stock|trading|trade|ticker|market|shares|equity)\b", re.I)
_CONFIRM = re.compile(r"^(?:yes|confirm|approve|approved|go ahead|proceed|do it)[.!\s]*$", re.I)
_REJECT = re.compile(r"^(?:no|cancel|reject|rejected|do not|don't|never mind|nevermind)[.!\s]*$", re.I)
_PAUSE = re.compile(r"^(?:pause|hold)[.!\s]*$", re.I)
_RESUME = re.compile(r"^(?:resume|continue)[.!\s]*$", re.I)
_CANCEL = re.compile(r"^(?:cancel|stop|abort)[.!\s]*$", re.I)


def route_typed_chat_turn(
    session: Any,
    user_message: Any,
    *,
    provider_id: str | None,
    model_id: str | None,
    context_items: list[dict[str, Any]] | None = None,
) -> GeneralizedChatResult | None:
    del context_items
    if _is_live_voice(user_message):
        return None

    content = str(user_message.content or "").strip()
    explicit_agent = bool(user_message.metadata.get("agent_mode"))
    decision = route_omnix_request(
        content,
        workflow_lookup=_workflow_lookup,
    )
    if explicit_agent and decision.lane != "agent":
        decision = OmnixRouteDecision(
            lane="agent",
            confidence=1.0,
            reason="explicit_agent_mode",
            explicit=True,
        )

    if decision.lane == "chat":
        return None
    # Open-ended execution never escalates from ordinary typed Chat solely from
    # a verb such as "fix". Require explicit Agent mode or explicit /agent text.
    if decision.lane == "agent" and not (explicit_agent or decision.explicit):
        return None

    if decision.lane == "direct":
        return _direct_result(session, user_message, decision)
    if decision.lane == "workflow":
        return _workflow_result(session, user_message, decision)
    return _agent_result(
        session,
        user_message,
        decision,
        provider_id=provider_id,
        model_id=model_id,
    )


def _workflow_lookup(candidate: str) -> str | None:
    try:
        return default_workflow_runtime().lookup(candidate)
    except Exception:
        return None


def _direct_result(session: Any, user_message: Any, decision: OmnixRouteDecision) -> GeneralizedChatResult:
    request = _direct_request(
        str(user_message.content or ""),
        session_id=str(session.id),
        message_id=str(user_message.id),
        capability_id=str(decision.capability_id or ""),
    )
    if request is None:
        return GeneralizedChatResult(
            content="I recognized a direct capability request, but could not resolve its target safely.",
            metadata={
                "generation_status": "completed",
                "omnix_route": decision.model_dump(mode="json"),
                "direct_execution": {"executed": False, "error": "direct_input_not_resolved"},
            },
        )
    review = review_assistant_tool_request(request)
    if not review.allowed:
        return GeneralizedChatResult(
            content=review.result_summary or "That direct action is not allowed.",
            metadata={
                "generation_status": "completed",
                "omnix_route": decision.model_dump(mode="json"),
                "direct_execution": {"executed": False, "error": review.reason},
            },
        )
    if review.approval_required:
        target = str(request.input.get("target") or "the selected resource")
        desired = request.input.get("state")
        verb = f"set {target} {desired}" if desired else f"run {request.action_id} for {target}"
        return GeneralizedChatResult(
            content=f"I can {verb}. Say 'confirm' to run it or 'cancel' to reject it.",
            metadata={
                "generation_status": "completed",
                "omnix_route": decision.model_dump(mode="json"),
                "pending_governed_tool_request": request.model_dump(mode="json"),
                "governed_tool_execution_status": "pending",
                "review_required": True,
                "executes": False,
            },
        )

    payload = hermes_assistant_tool_execute_payload(str(user_message.content or ""), request)
    result = payload.execution_result
    content = result.result_summary or ("Direct capability failed." if result.error else "Direct capability completed.")
    if result.error:
        content = f"{content} {result.error}".strip()
    return GeneralizedChatResult(
        content=content,
        metadata={
            "generation_status": "completed",
            "omnix_route": decision.model_dump(mode="json"),
            "direct_execution": payload.model_dump(mode="json"),
            "review_required": False,
            "executes": result.error is None,
        },
    )


def _direct_request(
    content: str,
    *,
    session_id: str,
    message_id: str,
    capability_id: str,
) -> AssistantToolRequest | None:
    proposal_id = f"direct:{session_id}:{message_id}"
    if capability_id == "home.set_state":
        match = _HOME_SET.search(content)
        if match is None:
            return None
        state = match.group(1).casefold()
        target = _clean_home_target(match.group(2))
        if not target:
            return None
        return AssistantToolRequest(
            tool_id="home",
            action_id="home.set_state",
            session_id=session_id,
            proposal_id=proposal_id,
            input={"target": target, "state": state},
        )
    if capability_id == "home.get_state":
        match = _HOME_STATE.search(content)
        if match is None:
            return None
        target = _clean_home_target(match.group(1))
        if not target:
            return None
        return AssistantToolRequest(
            tool_id="home",
            action_id="home.get_state",
            session_id=session_id,
            proposal_id=proposal_id,
            input={"target": target},
        )
    return None


def _clean_home_target(value: str) -> str:
    target = " ".join(str(value or "").strip().split())
    target = re.sub(r"^(?:kasa|smart)\s+", "", target, flags=re.I)
    target = re.sub(r"\s+(?:please|now)$", "", target, flags=re.I)
    return target.strip(" .!?")


def _workflow_result(session: Any, user_message: Any, decision: OmnixRouteDecision) -> GeneralizedChatResult:
    workflow_id = str(decision.workflow_id or "")
    runtime = default_workflow_runtime()
    try:
        run_id = runtime.start(
            workflow_id,
            {
                "chat_session_id": str(session.id),
                "user_request": str(user_message.content or ""),
                "idempotency_key": f"chat:{session.id}:{user_message.id}",
            },
        )
        state = runtime.get_status(run_id) or {"run_id": run_id, "status": "unknown"}
    except Exception as exc:
        return GeneralizedChatResult(
            content=f"Workflow {workflow_id} failed to start: {type(exc).__name__}: {exc}",
            metadata={
                "generation_status": "completed",
                "omnix_route": decision.model_dump(mode="json"),
                "workflow_run": {"workflow_id": workflow_id, "status": "failed", "error": str(exc)[:500]},
            },
        )
    status = str(state.get("status") or "running")
    if status == "waiting_for_approval":
        content = f"Workflow {workflow_id} is waiting for approval."
    elif status == "completed":
        content = f"Workflow {workflow_id} completed."
    else:
        content = f"Workflow {workflow_id} started with run {run_id}."
    return GeneralizedChatResult(
        content=content,
        metadata={
            "generation_status": "completed",
            "omnix_route": decision.model_dump(mode="json"),
            "workflow_run": state,
        },
    )


def _agent_result(
    session: Any,
    user_message: Any,
    decision: OmnixRouteDecision,
    *,
    provider_id: str | None,
    model_id: str | None,
) -> GeneralizedChatResult | None:
    try:
        service = default_agent_run_service()
    except Exception:
        return None
    active = _latest_active_agent_run(service, session)
    if active is not None:
        return _continue_agent_run(service, active, str(user_message.content or ""), decision)

    profile_id = _select_profile(str(user_message.content or ""))
    repository = os.environ.get("OMNIX_AGENT_DEFAULT_REPOSITORY", "").strip()
    if profile_id in {"coding", "ops"} and not repository:
        # Preserve the existing Hermes proposal-only path when no durable
        # workspace authority is configured.
        return None

    resolved_provider = str(provider_id or getattr(session, "provider_id", None) or os.environ.get("OMNIX_AGENT_DEFAULT_PROVIDER_ID", "")).strip()
    resolved_model = str(model_id or getattr(session, "model_id", None) or os.environ.get("OMNIX_AGENT_DEFAULT_MODEL_ID", "")).strip()
    if not resolved_provider or not resolved_model:
        return None

    profile = get_agent_profile(profile_id)
    local, external = resolve_profile_capabilities(profile)
    task = re.sub(r"^(?:/agent\b|agent[,:]\s*|use (?:the )?agent\b\s*)", "", str(user_message.content or ""), flags=re.I).strip()
    task = task or str(user_message.content or "").strip()
    workspace = (
        WorkspaceSpec(
            root=repository,
            repository=repository,
            base_ref=os.environ.get("OMNIX_AGENT_DEFAULT_BASE_REF", "main").strip() or "main",
        )
        if repository and profile.requires_workspace
        else WorkspaceSpec(root=".", allowed_paths=[])
    )
    spec = AgentRunSpec(
        session_id=str(session.id),
        task=task,
        objective=task,
        profile=profile_id,
        model=ModelRef(provider_id=resolved_provider, model_id=resolved_model),
        capabilities=local,
        external_capabilities=external,
        context_sources=list(profile.context_sources),
        workspace=workspace,
        success_criteria=[
            SuccessCriterion(
                id="user-request",
                description="Complete the user's requested task and report verifiable evidence.",
            )
        ],
        expected_artifacts=["diff"] if profile.requires_workspace else [],
    )
    try:
        snapshot = service.start(spec)
    except Exception:
        return None
    return GeneralizedChatResult(
        content=f"Started {profile_id} Agent run {snapshot.run_id}. I’ll keep the run durable; send another Agent-mode message to steer it.",
        metadata={
            "generation_status": "completed",
            "agent_mode": True,
            "omnix_route": decision.model_dump(mode="json"),
            "agent_run": _agent_metadata(snapshot),
        },
    )


def _latest_active_agent_run(service: Any, session: Any):
    for message in reversed(list(getattr(session, "messages", []) or [])):
        if getattr(message, "role", None) != "assistant":
            continue
        metadata = getattr(message, "metadata", {}) or {}
        raw = metadata.get("agent_run")
        if not isinstance(raw, dict):
            continue
        run_id = str(raw.get("run_id") or "").strip()
        if not run_id:
            continue
        try:
            snapshot = service.get(run_id)
        except Exception:
            continue
        if snapshot is not None and snapshot.status not in _TERMINAL_AGENT:
            return snapshot
    return None


def _continue_agent_run(service: Any, snapshot: Any, content: str, decision: OmnixRouteDecision) -> GeneralizedChatResult:
    command_type = "steer"
    payload: dict[str, Any] = {"message": content}
    normalized = " ".join(content.strip().split())
    if _PAUSE.fullmatch(normalized):
        command_type, payload = "pause", {}
    elif _RESUME.fullmatch(normalized) and snapshot.status == "paused":
        command_type, payload = "resume", {"message": "Resume from the current workspace state."}
    elif _CANCEL.fullmatch(normalized):
        command_type, payload = "cancel", {}
    elif snapshot.status == "waiting_for_approval" and (_CONFIRM.fullmatch(normalized) or _REJECT.fullmatch(normalized)):
        pending = service.approvals(snapshot.run_id, state="pending")
        if len(pending) == 1:
            command_type = "approve" if _CONFIRM.fullmatch(normalized) else "reject"
            payload = {"approval_id": pending[0].approval_id}

    command_digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]
    command = AgentRunCommand(
        run_id=snapshot.run_id,
        command_type=command_type,
        payload=payload,
        idempotency_key=f"chat:{snapshot.run_id}:{command_type}:{command_digest}",
    )
    try:
        updated = service.command(command)
    except Exception as exc:
        return GeneralizedChatResult(
            content=f"Agent run {snapshot.run_id} could not accept that command: {type(exc).__name__}: {exc}",
            metadata={
                "generation_status": "completed",
                "agent_mode": True,
                "omnix_route": decision.model_dump(mode="json"),
                "agent_run": _agent_metadata(snapshot),
            },
        )
    verb = {
        "steer": "Steering sent to",
        "pause": "Pause requested for",
        "resume": "Resume requested for",
        "cancel": "Cancellation requested for",
        "approve": "Approval sent to",
        "reject": "Rejection sent to",
    }[command_type]
    return GeneralizedChatResult(
        content=f"{verb} Agent run {updated.run_id}.",
        metadata={
            "generation_status": "completed",
            "agent_mode": True,
            "omnix_route": decision.model_dump(mode="json"),
            "agent_run": _agent_metadata(updated),
        },
    )


def _agent_metadata(snapshot: Any) -> dict[str, Any]:
    return {
        "run_id": snapshot.run_id,
        "status": snapshot.status,
        "profile": snapshot.spec.profile,
        "task": snapshot.spec.task,
        "revision": snapshot.revision,
        "last_error": snapshot.last_error,
    }


def _select_profile(content: str) -> str:
    if _HOME.search(content):
        return "house"
    if _PERSONAL.search(content):
        return "personal-assistant"
    if _TRADING.search(content):
        return "trading-research"
    if _CODE.search(content):
        return "coding"
    return "research"


def _is_live_voice(user_message: Any) -> bool:
    metadata = getattr(user_message, "metadata", {}) or {}
    return str(metadata.get("user_turn_id") or "").startswith("voice-user-turn:") or str(
        metadata.get("speech_segment_id") or ""
    ).startswith("voice-segment:")
