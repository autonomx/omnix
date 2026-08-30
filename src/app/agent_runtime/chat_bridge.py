"""Converge typed Omnix Chat onto the generalized execution lanes.

Live voice keeps the existing latency-optimized Live Agent path. Typed requests
are classified in AUTO mode across CHAT, DIRECT, WORKFLOW, and AGENT. The
persistent Agent control forces eligible typed turns through AGENT, while
explicit /agent and per-turn Quick/Deep research commands take precedence.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
import re
from collections.abc import Callable
from typing import Any

from app.assistant_tools.gate import review_assistant_tool_request
from app.assistant_tools.hermes_bridge import hermes_assistant_tool_execute_payload
from app.assistant_tools.models import AssistantToolRequest

from .contracts import AgentRunCommand, AgentRunSpec, ModelRef, RequestModeSelection, SuccessCriterion, WorkspaceSpec
from .evidence import (
    EvidenceCompilationError,
    classify_evidence,
    compile_task_authority,
    evidence_decision_from_semantic,
    resolve_request_mode,
    task_requires_workspace_mutation,
)
from .local_workspace import (
    LocalWorkspaceSelectionError,
    local_workspace_repository_root,
    validate_local_workspace_root,
)
from .profiles import get_agent_profile, select_agent_profile_id
from .router import OmnixRouteDecision, route_omnix_request
from .semantic_classifier import (
    SemanticIntentDecision,
    classify_semantic_intent_safely,
    default_semantic_intent_classifier,
    semantic_confidence_threshold,
    semantic_profile_id,
)
from .service import default_agent_run_service
from .workflow_runtime import default_workflow_runtime


@dataclass(frozen=True)
class GeneralizedChatResult:
    content: str
    metadata: dict[str, Any]


_TERMINAL_AGENT = {"completed", "failed", "cancelled"}
_HOME_SET = re.compile(r"\bturn\s+(on|off|of)\s+(?:the\s+)?(.+?)[.!?]*$", re.I)
_HOME_STATE = re.compile(r"\b(?:status|state)\s*(?:of|for)?\s*(?:the\s+)?(.+?)[.!?]*$", re.I)
_CODE = re.compile(
    r"(?:"
    r"\b(?:code|repo(?:sitory)?|branch|pull request|bug(?:s)?|test(?:s|ing)?|pytest|vitest|"
    r"refactor(?:ing)?|implement(?:ation|ing)?|fix(?:es|ing)?|debugg?(?:ing)?|edit(?:ing)?|"
    r"modify|patch|workspace|file(?:s)?|module|function|class)\b"
    r"|\.(?:py|pyi|js|jsx|ts|tsx|go|rs|java|rb|php|cs|cpp|c|h)\b"
    r"|\b(?:add|write|change|update|comment)\b.{0,120}\b(?:router|file|code|function|class|module|"
    r"repository|repo|workspace|source)\b"
    r")",
    re.I,
)
_HOME = re.compile(r"\b(?:kasa|smart\s+plugs?|plugs?|outlets?|lamps?|lights?|thermostats?|home)\b", re.I)
_PERSONAL = re.compile(r"\b(?:gmail|emails?|calendars?|meetings?|contacts?|appointments?|schedules?)\b", re.I)
_TRADING = re.compile(
    r"\b(?:stocks?|trading|trades?|tickers?|markets?|shares?|equities|gainers?|losers?|"
    r"orders?|positions?|buy|sell|purchase|short|cover)\b",
    re.I,
)
_TICKER_CONTEXT = re.compile(
    r"\b(?:research|reseach|investigate|analy[sz]e|anlyze|buy|sell|purchase|short)\b"
    r".{0,80}(?:\$[A-Z]{1,5}\b|\b(?:NVDA|GME|TSLA)\b)"
)
_CONFIRM = re.compile(r"^(?:yes|confirm|approve|approved|go ahead|proceed|do it)[.!\s]*$", re.I)
_REJECT = re.compile(r"^(?:no|cancel|reject|rejected|do not|don't|never mind|nevermind)[.!\s]*$", re.I)
_PAUSE = re.compile(r"^(?:pause|hold)[.!\s]*$", re.I)
_RESUME = re.compile(r"^(?:resume|continue)[.!\s]*$", re.I)
_CANCEL = re.compile(r"^(?:cancel|stop|abort)[.!\s]*$", re.I)
_CONTROL = re.compile(r"^(?:pause|hold|resume|continue|cancel|stop|abort)[.!\s]*$", re.I)
_WORKSPACE_MUTATION = re.compile(
    r"(?:\b(?:edit|modify|write|change|patch|commit|delete|remove|create)\b.{0,120}\b(?:repo(?:sitory)?|"
    r"file|code|workspace|branch|source|module|script)\b|\.(?:py|pyi|js|jsx|ts|tsx|go|rs|java|rb|php|cs|cpp|c|h)\b|"
    r"\b(?:git\s+push|push\s+to\s+origin|open\s+(?:a\s+)?pull\s+request)\b)",
    re.I,
)
_TRADING_MUTATION = re.compile(
    r"\b(?:buy|sell|purchase|short|cover)\b|\b(?:place|submit|cancel)\b.{0,60}\b(?:order|trade|position)\b",
    re.I,
)
_PUBLICATION_REQUEST = re.compile(
    r"\b(?:git\s+push|push\s+(?:the\s+)?(?:current\s+)?branch|open\s+(?:a\s+)?pull\s+request|create\s+(?:a\s+)?pull\s+request)\b",
    re.I,
)
_CLASSIFIER_STEERING = re.compile(
    r"(?:\b(?:ignore|disregard|override)\b.{0,100}\b(?:classifier|routing|router|rules?)\b|"
    r"\b(?:label|classify|route)\s+(?:this|it)\s+(?:as\s+)?(?:chat|agent)\b)",
    re.I,
)
_CONTEXTUAL_FOLLOW_UP = re.compile(
    r"^(?:(?:let'?s|lets)\s+(?:fix|change|update|implement|apply|do|try)"
    r"(?:\s+(?:it|that|this))?|"
    r"(?:yes|yeah|yep|sure|ok(?:ay)?|go\s+ahead|do\s+it|apply\s+it|"
    r"fix\s+(?:it|that|this)|make\s+that\s+change|implement\s+that))[.!?\s]*$",
    re.I,
)
_CONTEXT_REFERENCE = re.compile(
    r"(?:\b(?:it|that|this|those|them|same|above|previous|earlier|other|former|latter)\b|"
    r"\b(?:the|this|that)\s+(?:issue|problem|bug|defect|fix|change|option|suggestion|idea)\b|"
    r"\b(?:first|second|third|last)\s+(?:one|option|suggestion|idea)\b|"
    r"\b(?:what|thing)\s+(?:you|we|i)\s+(?:suggested|mentioned|described|discussed)\b|"
    r"\b(?:issue|problem|bug|defect)\s+(?:we|i)\s+(?:mentioned|described|discussed)\b)",
    re.I,
)
_SEMANTIC_AUTO = object()
_DEFAULT_AGENT_REASONING_EFFORT = "none"


def _resolve_agent_model_route(
    provider_id: str | None,
    model_id: str | None,
) -> tuple[str, str]:
    """Normalize Chat's provider/model IDs and fill a provider default model.

    Browser Chat persists selectable models as ``llm:<provider>:<model>`` while
    older sessions can retain only a provider. Pi needs a concrete, matched
    provider/model pair, unlike ordinary chat providers that can infer their
    configured default model.
    """

    provider = str(provider_id or "").strip().removeprefix("llm:")
    model = str(model_id or "").strip()
    if model.startswith("llm:"):
        parts = model.split(":", 2)
        if len(parts) == 3 and parts[1] and parts[2]:
            _, model_provider, selected_model = parts
            provider = model_provider
            model = selected_model
    if provider and not model:
        try:
            from app import shared

            configured_provider = shared.get_provider(provider)
            model = str(
                getattr(getattr(configured_provider, "config", None), "model", "")
                or ""
            ).strip()
        except Exception:
            # Preserve the existing clear configuration failure below when the
            # selected provider itself cannot be constructed.
            pass
    return provider, model


def _agent_reasoning_effort() -> str:
    """Return the reasoning level for Chat-created Pi runs.

    ChatGPT Codex calls this disabled level ``none``. Pi receives the same
    intent as ``--thinking off`` when the run command is built. Keep an
    environment override for operators that want to opt back into reasoning
    for a particular worker configuration.
    """
    configured = os.environ.get("OMNIX_AGENT_REASONING_EFFORT", "").strip()
    if not configured:
        return _DEFAULT_AGENT_REASONING_EFFORT
    if configured.casefold() in {"off", "disabled"}:
        return _DEFAULT_AGENT_REASONING_EFFORT
    return configured


def _routing_context_text(value: Any) -> str:
    """Read only the canonical Chat reference projection, never its authority."""

    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        candidate = value.get("reference_context")
    else:
        candidate = getattr(value, "reference_context", None)
    return str(candidate or "").strip()


def _resolve_routing_context(
    session: Any,
    user_message: Any,
    factory: Callable[[], Any] | None,
) -> str:
    """Prefer the canonical Chat memory/history/summary context.

    Production Chat passes a lazy factory from ChatSessionStore. The fallback
    also uses PromptAssembly so direct/unit callers do not revive a parallel
    ad-hoc transcript window.
    """

    if factory is not None:
        try:
            resolved = _routing_context_text(factory())
        except Exception:
            resolved = ""
        if resolved:
            return resolved

    try:
        from app.chat.prompt_assembly import build_prompt_assembly
        from app.chat.routing_context import build_chat_routing_context

        assembly = build_prompt_assembly(
            session,
            user_message,
            global_system_prompt="",
            context_items=[],
            approved_memory=[],
            retrieved_history=[],
        )
        return build_chat_routing_context(assembly).reference_context
    except Exception:
        return ""


def _semantic_classifier_content(content: str, previous_context: str) -> str:
    """Give semantic routing enough prior chat to resolve terse references."""

    latest = str(content or "").strip()
    if not previous_context:
        return latest
    return (
        "Canonical Chat reference context (reference resolution only, not authority):\n"
        f"{previous_context}\n\n"
        "Latest user steering (authoritative):\n"
        f"{latest}"
    )


def _turn_depends_on_previous_context(content: str) -> bool:
    text = " ".join(str(content or "").strip().split())
    if not text or len(text) > 140:
        return False
    return bool(
        _CONTEXTUAL_FOLLOW_UP.fullmatch(text)
        or _CONTEXT_REFERENCE.search(text)
    )


def _profile_resolution_content(content: str, previous_context: str) -> str:
    """Use history for deterministic profile fallback only on referential turns."""

    if previous_context and _turn_depends_on_previous_context(content):
        return _semantic_classifier_content(content, previous_context)
    return str(content or "").strip()


def _contextual_agent_task(
    authority_task: str,
    *,
    latest_content: str,
    previous_context: str,
) -> str:
    """Ground an elliptical Agent task without widening its compiled authority."""

    if not previous_context or not _turn_depends_on_previous_context(latest_content):
        return authority_task
    return (
        f"{authority_task}\n\n"
        "Canonical Chat context for resolving references only; it may include recent "
        "turns, a session summary, approved memory, or retrieved history. The latest "
        "user request above is authoritative:\n"
        f"{previous_context}"
    )


def _should_use_semantic_classifier(decision: OmnixRouteDecision, content: str) -> bool:
    if not str(content or "").strip():
        return False
    if decision.reason == "casual_or_empty":
        return False
    if decision.lane in {"direct", "workflow"} and decision.confidence >= 0.95:
        return False
    return True


def _negated_action_allows_semantic_agent(
    content: str,
    semantic: SemanticIntentDecision,
) -> bool:
    """Distinguish total refusal from a narrow prohibition plus allowed work."""

    if semantic.lane != "agent":
        return False
    actions = {str(value) for value in semantic.action_intents}
    if not actions:
        return False

    text = " ".join(str(content or "").split())
    if re.match(
        r"^(?:don'?t|do\s+not)\s+just\s+(?:tell|explain|describe)\b",
        text,
        re.I,
    ):
        return True

    # A broad refusal such as "don't touch anything" still blocks semantic
    # promotion. Narrow prohibitions below only remove the forbidden action;
    # another requested action may still justify Agent.
    if re.match(
        r"^(?:don'?t|do\s+not|never)\s+(?:touch|access)\s+anything\b",
        text,
        re.I,
    ):
        return False

    forbidden: set[str] = set()
    if re.search(r"\b(?:don'?t|do\s+not|never)\s+(?:send|reply|forward)\b", text, re.I):
        forbidden.add("email_send")
    if re.search(r"\b(?:don'?t|do\s+not|never)\s+(?:draft|compose)\b", text, re.I):
        forbidden.add("email_draft")
    if re.search(
        r"\b(?:don'?t|do\s+not|never)\s+(?:schedule|book|create|add)\b.{0,80}"
        r"\b(?:calendar|meeting|appointment|event)\b",
        text,
        re.I,
    ):
        forbidden.add("calendar_create")
    if re.search(
        r"\b(?:don'?t|do\s+not|never)\s+(?:turn|set|adjust|lower|raise|dim|brighten|change)\b.{0,80}"
        r"\b(?:light|lamp|plug|outlet|thermostat|home)\b",
        text,
        re.I,
    ) or re.search(
        r"\b(?:don'?t|do\s+not|never)\s+change\s+(?:the\s+)?(?:lights?|lamps?)\b",
        text,
        re.I,
    ):
        forbidden.add("home_mutate")
    if re.search(
        r"\b(?:don'?t|do\s+not|never)\s+(?:edit|modify|write|change|patch|update|delete|remove)\b",
        text,
        re.I,
    ):
        forbidden.add("workspace_mutate")

    return bool(actions - forbidden)


def _apply_semantic_route_decision(
    deterministic: OmnixRouteDecision,
    semantic: SemanticIntentDecision | None,
    *,
    content: str | None = None,
) -> OmnixRouteDecision:
    if semantic is None or semantic.confidence < semantic_confidence_threshold():
        return deterministic
    # Hypotheticals remain non-executing. A broad no-action request also stays
    # Chat, but a narrow prohibition (for example "don't send; draft instead")
    # must not suppress a separately requested allowed Agent action. Capability
    # compilation still enforces the explicit prohibition deterministically.
    if deterministic.reason == "hypothetical_or_conditional":
        return deterministic
    if deterministic.reason == "negated_action" and not (
        content is not None
        and _negated_action_allows_semantic_agent(content, semantic)
    ):
        return deterministic
    if (
        content is not None
        and deterministic.lane == "agent"
        and semantic.lane == "chat"
        and _CLASSIFIER_STEERING.search(content)
    ):
        return deterministic.model_copy(
            update={
                "reason": f"{deterministic.reason}+classifier_steering_ignored"[:240],
                "hermes_recommended": deterministic.hermes_recommended or semantic.multi_step,
            }
        )
    if deterministic.explicit:
        return deterministic.model_copy(
            update={
                "reason": f"{deterministic.reason}+semantic:{semantic.primary_intent}"[:240],
                "hermes_recommended": deterministic.hermes_recommended or semantic.multi_step,
            }
        )
    if deterministic.lane in {"direct", "workflow"} and deterministic.confidence >= 0.95:
        return deterministic
    if (
        deterministic.lane == "agent"
        and deterministic.reason in {
            "workspace_mutation_request",
            "workspace_read_request",
        }
        and deterministic.confidence >= 0.95
    ):
        # Concrete workspace reads/mutations are executable requests even when
        # the advisory classifier mistakes a terse repository request for Chat.
        return deterministic
    if (
        deterministic.lane == "chat"
        and semantic.lane == "agent"
        and not semantic.action_intents
    ):
        # A semantic Agent label without any executable semantic action is too
        # weak to promote a conversational request into an autonomous run.
        # This preserves deterministic Chat for planning-only or malformed
        # classifier outputs while still allowing action-bearing semantic
        # upgrades for indirect coding, personal-assistant, home, and research work.
        return deterministic
    return OmnixRouteDecision(
        lane=semantic.lane,
        confidence=semantic.confidence,
        reason=f"semantic:{semantic.primary_intent}"[:240],
        explicit=False,
        hermes_recommended=semantic.multi_step,
    )


def _mark_chat_route(
    user_message: Any,
    decision: OmnixRouteDecision,
    *,
    semantic_intent: SemanticIntentDecision | None = None,
    request_mode: RequestModeSelection | None = None,
) -> None:
    metadata = getattr(user_message, "metadata", None)
    if not isinstance(metadata, dict):
        return
    metadata["omnix_chat_routed"] = True
    metadata["omnix_route"] = decision.model_dump(mode="json")
    if semantic_intent is not None:
        metadata["semantic_intent"] = semantic_intent.model_dump(mode="json")
    if request_mode is not None:
        metadata["request_mode"] = request_mode.model_dump(mode="json")


def route_typed_chat_turn(
    session: Any,
    user_message: Any,
    *,
    provider_id: str | None,
    model_id: str | None,
    context_items: list[dict[str, Any]] | None = None,
    semantic_classifier: Any = _SEMANTIC_AUTO,
    routing_context_factory: Callable[[], Any] | None = None,
) -> GeneralizedChatResult | None:
    # External assistant-context enrichment is intentionally not routing
    # authority. Conversational reference context comes from the canonical Chat
    # prompt pipeline (recent turns, summary, approved memory, retrieved history).
    del context_items
    if _is_live_voice(user_message):
        return None

    content = str(user_message.content or "").strip()
    previous_routing_context = ""
    metadata = getattr(user_message, "metadata", {}) or {}
    explicit_agent = bool(metadata.get("agent_mode"))
    research_mode = _message_research_mode(metadata)
    deterministic_decision = route_omnix_request(
        content,
        workflow_lookup=_workflow_lookup,
        research_mode=research_mode,
    )
    preliminary_mode = resolve_request_mode(
        content,
        turn_research_mode=research_mode,
        persistent_agent=explicit_agent,
        classifier_lane=deterministic_decision.lane,
    )
    # Quick/Deep is a separate bounded research lane and does not need Agent
    # semantic classification. Explicit /agent still outranks a turn setting.
    if preliminary_mode.mode in {"quick_research", "deep_research"}:
        _mark_chat_route(
            user_message,
            deterministic_decision,
            request_mode=preliminary_mode,
        )
        return None

    semantic_intent: SemanticIntentDecision | None = None
    if _should_use_semantic_classifier(deterministic_decision, content):
        classifier = semantic_classifier
        if classifier is _SEMANTIC_AUTO:
            classifier = default_semantic_intent_classifier(
                provider_id=(
                    str(provider_id or getattr(session, "provider_id", None) or "").strip()
                    or None
                ),
                model_id=(
                    str(model_id or getattr(session, "model_id", None) or "").strip()
                    or None
                ),
            )
        if classifier is not None:
            previous_routing_context = _resolve_routing_context(
                session,
                user_message,
                routing_context_factory,
            )
            semantic_content = _semantic_classifier_content(
                content,
                previous_routing_context,
            )
            semantic_intent = classify_semantic_intent_safely(
                classifier,
                semantic_content,
            )

    decision = _apply_semantic_route_decision(
        deterministic_decision,
        semantic_intent,
        content=content,
    )
    mode = resolve_request_mode(
        content,
        turn_research_mode=research_mode,
        persistent_agent=explicit_agent,
        classifier_lane=decision.lane,
    )
    # A narrower per-turn Quick/Deep selection outranks the persistent Agent
    # toggle. An explicit /agent command outranks both.
    if mode.mode in {"quick_research", "deep_research"}:
        _mark_chat_route(
            user_message,
            decision,
            semantic_intent=semantic_intent,
            request_mode=mode,
        )
        return None
    if mode.mode == "agent" and decision.lane != "agent":
        decision = OmnixRouteDecision(
            lane="agent",
            confidence=1.0 if mode.source in {"explicit_command", "persistent_setting"} else decision.confidence,
            reason=f"request_mode:{mode.source}",
            explicit=mode.source == "explicit_command",
            hermes_recommended=semantic_intent.multi_step if semantic_intent else False,
        )

    if decision.lane == "chat":
        _mark_chat_route(
            user_message,
            decision,
            semantic_intent=semantic_intent,
            request_mode=mode,
        )
        return None

    if decision.lane == "direct":
        return _direct_result(session, user_message, decision)
    if decision.lane == "workflow":
        return _workflow_result(session, user_message, decision)
    if (
        not previous_routing_context
        and _turn_depends_on_previous_context(content)
    ):
        previous_routing_context = _resolve_routing_context(
            session,
            user_message,
            routing_context_factory,
        )
    return _agent_result(
        session,
        user_message,
        decision,
        provider_id=provider_id,
        model_id=model_id,
        request_mode=mode,
        semantic_intent=semantic_intent,
        semantic_context=previous_routing_context,
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
        if state == "of":
            state = "off"
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
    request_mode: RequestModeSelection,
    semantic_intent: SemanticIntentDecision | None = None,
    semantic_context: str = "",
) -> GeneralizedChatResult | None:
    content = str(user_message.content or "").strip()
    message_metadata = getattr(user_message, "metadata", {}) or {}
    selected_workspace = str(message_metadata.get("workspace_root") or "").strip()
    profile_id = semantic_profile_id(
        _profile_resolution_content(content, semantic_context),
        semantic_intent,
    )
    profile = get_agent_profile(profile_id)
    try:
        service = default_agent_run_service()
    except Exception as exc:
        return _agent_start_failure(
            decision,
            run_id=None,
            profile=profile_id,
            task=_agent_task(content),
            error=exc,
        )
    latest = _latest_agent_run(service, session)
    active = latest if latest is not None and latest.status not in _TERMINAL_AGENT else None
    if active is not None:
        if selected_workspace:
            try:
                selected_workspace = validate_local_workspace_root(selected_workspace)
            except LocalWorkspaceSelectionError as exc:
                return _agent_request_rejection(
                    decision,
                    profile=profile_id,
                    task=_agent_task(content),
                    reason="local_workspace_unavailable",
                    message=f"I can't use the attached Local folder: {exc}",
                )
            issued_workspace = getattr(active.spec, "workspace", None)
            issued_paths = {
                str(value)
                for value in (
                    getattr(issued_workspace, "root", None),
                    getattr(issued_workspace, "worktree", None),
                    getattr(issued_workspace, "repository", None),
                )
                if value
            }
            normalized_issued = {
                os.path.normcase(os.path.abspath(path))
                for path in issued_paths
            }
            if (
                normalized_issued
                and os.path.normcase(os.path.abspath(selected_workspace))
                not in normalized_issued
            ):
                return _agent_request_rejection(
                    decision,
                    profile=profile_id,
                    task=_agent_task(content),
                    reason="active_run_workspace_mismatch",
                    message=(
                        "The active Agent run is bound to a different Local folder. "
                        "Cancel or finish that run before switching workspaces."
                    ),
                )
        return _continue_agent_run(
            service,
            active,
            content,
            decision,
            reference_context=(
                semantic_context
                if _turn_depends_on_previous_context(content)
                else ""
            ),
        )
    if latest is not None and _CONTROL.fullmatch(content):
        return GeneralizedChatResult(
            content=f"Agent run {latest.run_id} is already {latest.status}.",
            metadata={
                "generation_status": "completed",
                "agent_mode": True,
                "omnix_route": decision.model_dump(mode="json"),
                "agent_run": _agent_metadata(latest),
            },
        )

    repository = os.environ.get("OMNIX_AGENT_DEFAULT_REPOSITORY", "").strip()
    selected_repository: str | None = None
    if profile.requires_workspace and selected_workspace:
        try:
            selected_workspace = validate_local_workspace_root(selected_workspace)
            selected_repository = local_workspace_repository_root(selected_workspace)
        except LocalWorkspaceSelectionError as exc:
            return _agent_start_failure(
                decision,
                run_id=None,
                profile=profile_id,
                task=_agent_task(content),
                error=exc,
            )
        repository = selected_workspace
    if profile.requires_workspace and not repository:
        return _agent_start_failure(
            decision,
            run_id=None,
            profile=profile_id,
            task=_agent_task(content),
            error=RuntimeError(
                f"the {profile_id} profile requires OMNIX_AGENT_DEFAULT_REPOSITORY "
                "or a Local folder"
            ),
        )

    resolved_provider, resolved_model = _resolve_agent_model_route(
        str(
            provider_id
            or getattr(session, "provider_id", None)
            or os.environ.get("OMNIX_AGENT_DEFAULT_PROVIDER_ID", "")
        ).strip(),
        str(
            model_id
            or getattr(session, "model_id", None)
            or os.environ.get("OMNIX_AGENT_DEFAULT_MODEL_ID", "")
        ).strip(),
    )
    if not resolved_provider or not resolved_model:
        return _agent_start_failure(
            decision,
            run_id=None,
            profile=profile_id,
            task=_agent_task(content),
            error=RuntimeError("Agent provider/model is not configured"),
        )

    authority_task = _agent_task(content)
    task = _contextual_agent_task(
        authority_task,
        latest_content=content,
        previous_context=semantic_context,
    )
    if _PUBLICATION_REQUEST.search(content):
        return _agent_request_rejection(
            decision,
            profile=profile_id,
            task=task,
            reason="github_publication_capability_not_issued",
            message=(
                "I can't publish from a Chat-created coding run: GitHub push/PR "
                "capabilities were not issued. Start a separately scoped, "
                "approval-gated publication run."
            ),
        )
    if profile_id in {"research", "trading-research"} and _TRADING_MUTATION.search(content):
        return _agent_request_rejection(
            decision,
            profile=profile_id,
            task=task,
            reason="trading_execution_capability_not_issued",
            message=(
                "I can't place or manage trades from a research run: trading "
                "execution authority was not issued."
            ),
        )
    semantic_evidence = (
        evidence_decision_from_semantic(authority_task, semantic_intent)
        if semantic_intent is not None
        else None
    )
    semantic_actions = (
        list(semantic_intent.action_intents)
        if semantic_intent is not None
        and semantic_intent.confidence >= semantic_confidence_threshold()
        else []
    )
    try:
        evidence_decision = classify_evidence(
            authority_task,
            profile_id=profile_id,
            semantic_adviser=(
                (lambda _task, _profile: semantic_evidence)
                if semantic_evidence is not None
                else None
            ),
        )
        compiled = compile_task_authority(
            profile,
            authority_task,
            evidence_decision,
            semantic_action_intents=semantic_actions,
        )
    except EvidenceCompilationError as exc:
        return _agent_request_rejection(
            decision,
            profile=profile_id,
            task=task,
            reason=exc.code,
            message=f"I can't safely compile this Agent task: {exc}",
        )
    local = list(compiled.required_local)
    external = list(compiled.required_external)
    workspace = None
    if repository and profile.requires_workspace:
        if selected_workspace:
            workspace = WorkspaceSpec(
                root=selected_workspace,
                repository=selected_repository,
                worktree=selected_workspace if selected_repository else None,
                base_ref="HEAD",
            )
        else:
            workspace = WorkspaceSpec(
                root=repository,
                repository=repository,
                base_ref=os.environ.get("OMNIX_AGENT_DEFAULT_BASE_REF", "HEAD").strip() or "HEAD",
            )
    spec = AgentRunSpec(
        session_id=str(session.id),
        task=task,
        objective=authority_task,
        profile=profile_id,
        model=ModelRef(
            provider_id=resolved_provider,
            model_id=resolved_model,
            reasoning_effort=_agent_reasoning_effort(),
        ),
        capabilities=local,
        external_capabilities=external,
        context_sources=list(profile.context_sources),
        request_mode=request_mode,
        evidence_policy=evidence_decision.policy,
        workspace=workspace,
        success_criteria=[
            SuccessCriterion(
                id="user-request",
                description="Complete the user's requested task and report verifiable evidence.",
            )
        ],
        expected_artifacts=(
            ["diff"]
            if profile_id == "coding"
            and task_requires_workspace_mutation(
                authority_task,
                semantic_action_intents=semantic_actions,
            )
            else []
        ),
    )
    try:
        snapshot = service.start(spec)
    except Exception as exc:
        return _agent_start_failure(
            decision,
            run_id=spec.run_id,
            profile=profile_id,
            task=task,
            error=exc,
            service=service,
        )
    return GeneralizedChatResult(
        content=(
            f"Started {profile_id} Agent run {snapshot.run_id}. "
            "I'll keep the run durable; send another Agent-mode message to steer it."
        ),
        metadata={
            "generation_status": "completed",
            "agent_mode": True,
            "omnix_route": decision.model_dump(mode="json"),
            "agent_run": _agent_metadata(snapshot),
            "request_mode": request_mode.model_dump(mode="json"),
            "evidence_decision": evidence_decision.model_dump(mode="json"),
            "semantic_intent": (
                semantic_intent.model_dump(mode="json")
                if semantic_intent is not None
                else None
            ),
        },
    )


def _agent_task(content: str) -> str:
    task = re.sub(
        r"^(?:/agent\b|/agnet\b|agent[,:]\s*|use (?:the )?agent\b\s*)",
        "",
        content,
        flags=re.I,
    ).strip()
    return task or content


def _agent_start_failure(
    decision: OmnixRouteDecision,
    *,
    run_id: str | None,
    profile: str,
    task: str,
    error: Exception,
    service: Any | None = None,
) -> GeneralizedChatResult:
    persisted = None
    if service is not None and run_id:
        try:
            persisted = service.get(run_id)
        except Exception:
            persisted = None
    error_text = f"{type(error).__name__}: {error}"[:2000]
    durable = persisted is not None
    return GeneralizedChatResult(
        content=(
            f"Agent run {run_id} failed to start: {error_text}"
            if run_id
            else f"Agent request could not start: {error_text}"
        ),
        metadata={
            "generation_status": "completed",
            "agent_mode": True,
            "omnix_route": decision.model_dump(mode="json"),
            "agent_start": {
                "status": "failed",
                "durable": durable,
                "error": error_text,
            },
            "agent_run": (
                {
                    "run_id": run_id,
                    "status": str(persisted.status),
                    "profile": str(persisted.spec.profile),
                    "task": str(persisted.spec.task),
                    "revision": persisted.revision,
                    "last_error": persisted.last_error,
                }
                if persisted is not None
                else {
                    "run_id": run_id,
                    "status": "failed",
                    "profile": profile,
                    "task": task,
                    "revision": None,
                    "last_error": error_text,
                }
            ),
        },
    )


def _agent_request_rejection(
    decision: OmnixRouteDecision,
    *,
    profile: str,
    task: str,
    reason: str,
    message: str,
) -> GeneralizedChatResult:
    return GeneralizedChatResult(
        content=message,
        metadata={
            "generation_status": "completed",
            "agent_mode": True,
            "omnix_route": decision.model_dump(mode="json"),
            "agent_start": {
                "status": "rejected",
                "durable": False,
                "reason": reason,
            },
            "agent_run": {
                "run_id": None,
                "status": "rejected",
                "profile": profile,
                "task": task,
                "revision": None,
                "last_error": reason,
            },
        },
    )


def _latest_active_agent_run(service: Any, session: Any):
    snapshot = _latest_agent_run(service, session)
    if snapshot is not None and snapshot.status not in _TERMINAL_AGENT:
        return snapshot
    return None


def _latest_agent_run(service: Any, session: Any):
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
        if snapshot is not None:
            return snapshot
    return None


def _continue_agent_run(
    service: Any,
    snapshot: Any,
    content: str,
    decision: OmnixRouteDecision,
    *,
    reference_context: str = "",
) -> GeneralizedChatResult:
    rejection = _unauthorized_agent_command(snapshot, content)
    if rejection is not None:
        return GeneralizedChatResult(
            content=rejection["message"],
            metadata={
                "generation_status": "completed",
                "agent_mode": True,
                "omnix_route": decision.model_dump(mode="json"),
                "agent_run": _agent_metadata(snapshot),
                "agent_command": {
                    "accepted": False,
                    "command_type": "steer",
                    "reason": rejection["reason"],
                    "required_capabilities": rejection["required_capabilities"],
                },
            },
        )
    command_type = "steer"
    payload: dict[str, Any] = {
        "message": content,
        **(
            {"reference_context": reference_context}
            if reference_context
            else {}
        ),
    }
    normalized = " ".join(content.strip().split())
    if _PAUSE.fullmatch(normalized):
        command_type, payload = "pause", {}
    elif _RESUME.fullmatch(normalized) and snapshot.status == "paused":
        command_type, payload = "resume", {"message": "Resume from the current workspace state."}
    elif snapshot.status == "waiting_for_approval" and (_CONFIRM.fullmatch(normalized) or _REJECT.fullmatch(normalized)):
        pending = service.approvals(snapshot.run_id, state="pending")
        if len(pending) == 1:
            command_type = "approve" if _CONFIRM.fullmatch(normalized) else "reject"
            payload = {"approval_id": pending[0].approval_id}
    elif _CANCEL.fullmatch(normalized):
        command_type, payload = "cancel", {}

    digest_material = normalized
    if command_type == "steer" and reference_context:
        digest_material += "\nreference-context:\n" + reference_context
    command_digest = hashlib.sha256(digest_material.encode("utf-8")).hexdigest()[:24]
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
    if command_type == "steer" and updated.run_id != snapshot.run_id:
        return GeneralizedChatResult(
            content=(
                f"Started superseding Agent run {updated.run_id} because the revised task "
                "requires a different authority/evidence contract."
            ),
            metadata={
                "generation_status": "completed",
                "agent_mode": True,
                "omnix_route": decision.model_dump(mode="json"),
                "agent_run": _agent_metadata(updated),
                "supersedes_run_id": snapshot.run_id,
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


def _unauthorized_agent_command(snapshot: Any, content: str) -> dict[str, Any] | None:
    external_capabilities = {str(value) for value in (snapshot.spec.external_capabilities or [])}
    profile = str(snapshot.spec.profile or "")
    if profile in {"research", "trading-research"} and _TRADING_MUTATION.search(content):
        return {
            "reason": "trading_execution_capability_not_issued",
            "required_capabilities": ["trading.order"],
            "message": (
                "I can't place or manage trades from this read-only research run. "
                "Start a separately scoped, approval-gated trading run if execution is intended."
            ),
        }
    if _PUBLICATION_REQUEST.search(content) and not {
        "github.push",
        "github.create_pr",
    }.issubset(external_capabilities):
        return {
            "reason": "github_publication_capability_not_issued",
            "required_capabilities": ["github.push", "github.create_pr"],
            "message": (
                "I can't publish from this run: GitHub push/PR capabilities were not issued. "
                "The local workspace authority does not grant publication authority."
            ),
        }
    return None


def _agent_metadata(snapshot: Any) -> dict[str, Any]:
    return {
        "run_id": snapshot.run_id,
        "status": snapshot.status,
        "profile": snapshot.spec.profile,
        "task": snapshot.spec.task,
        "revision": snapshot.revision,
        "last_error": snapshot.last_error,
        "superseded_by_run_id": getattr(snapshot, "superseded_by_run_id", None),
        "supersedes_run_id": getattr(snapshot.spec, "supersedes_run_id", None),
        "request_mode": snapshot.spec.request_mode.model_dump(mode="json") if snapshot.spec.request_mode else None,
        "evidence_policy": snapshot.spec.evidence_policy.model_dump(mode="json"),
    }


def _select_profile(content: str) -> str:
    """Compatibility wrapper around the shared deterministic profile classifier."""
    return select_agent_profile_id(content)


def _message_research_mode(metadata: dict[str, Any]) -> str | None:
    direct = metadata.get("research_mode") or metadata.get("web_research_mode")
    if direct is not None:
        return str(direct)
    diagnostics = metadata.get("context_diagnostics")
    if isinstance(diagnostics, dict):
        value = diagnostics.get("research_effective_mode") or diagnostics.get("web_research_mode")
        if value is not None:
            return str(value)
    return None


def _is_live_voice(user_message: Any) -> bool:
    metadata = getattr(user_message, "metadata", {}) or {}
    return str(metadata.get("user_turn_id") or "").startswith("voice-user-turn:") or str(
        metadata.get("speech_segment_id") or ""
    ).startswith("voice-segment:")
