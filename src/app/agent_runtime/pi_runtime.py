"""Trusted Omnix prompt layer over the stable Pi RPC runtime core.

Pi's arbitrary skills, templates and context-file loading remain disabled by the
core launcher. Omnix adds only allowlisted methodology and explicitly compiled
repository guidance here, preserving capability and completion authority.
"""
from __future__ import annotations

import json

from .coding_skills import compile_coding_skills
from .contracts import AgentEvent, AgentRunCommand, AgentRunSnapshot, AgentRunSpec
from .debug_logging import log_agent_activity
from . import pi_runtime_core as _pi_runtime_core
from .pi_runtime_core import (
    PiAgentRuntime as _CorePiAgentRuntime,
    PiRpcSession,
    build_agent_environment,
    pi_broker_extension_path,
    pi_guard_extension_path,
    pi_model_provider_extension_path,
    pi_rpc_argv as _imported_core_pi_rpc_argv,
)
from .repository_guidance import compile_repository_guidance


_ENGINEERING_WORKFLOW = """MANDATORY ENGINEERING WORKFLOW FOR MUTATING CODING TASKS
1. INSPECT — inspect the relevant repository structure and existing implementation before editing. Locate tests, callers, interfaces, registrations, schemas and adjacent patterns; do not guess architecture.
2. DEFINE COMPLETION — re-read the user objective and required success criteria. Identify what implementation and evidence will prove each requirement.
3. PLAN — after repository inspection, call `omnix_plan` with action=`inspect` so Omnix can independently capture repository evidence and impact candidates. Then call `omnix_plan` action=`submit` with a structured plan covering every required requirement, high-impact candidate and final validation. The plan is a proposal; only Omnix can approve it. Do not mutate before plan approval when enforcement is active.
4. IMPLEMENT — make only plan-backed changes and add/update regression tests where behavior changes. If new evidence changes the intended implementation, call `omnix_plan` action=`inspect` with focused queries/paths and then action=`amend` before continuing. Repair/review findings are new evidence, not permission to bypass planning.
5. INSPECT THE COMPLETE RESULT — after the final edit, inspect the complete diff. Check accidental changes, duplication, dead/debug code, stale names, missing imports, incomplete call sites, migrations and generated contracts.
6. REREAD REQUIREMENTS — compare every requested requirement against the actual final implementation. Passing tests alone do not prove semantic completeness.
7. IMPACT / REGRESSION REVIEW — search affected callers and consumers; consider edge cases, compatibility and authority boundaries. Fix material issues found.
8. PLAN CONFORMANCE — call `omnix_plan` action=`check` and resolve unplanned paths, missing planned impacts, stale evidence or residual superseded references before requesting completion.
9. FINAL-STATE VALIDATION — run the smallest relevant tests/typecheck/lint/build against the FINAL code state. Validation from before a later mutation is stale and does not count.
10. SELF-REVIEW — critically review the change as if it were another engineer's patch. Repair incomplete requirements or regressions before settling.
11. REQUEST COMPLETION — Pi settling is only a completion request. Omnix will independently validate/review the exact final state and is the only authority that can mark the run completed.
GOVERNED CAPABILITIES — capabilities listed under `Issued governed external capabilities` are already issued by Omnix. When one is needed, invoke it through `omnix_capability`; do not ask the user to issue or enable an already-listed capability.
WORKTREE UI PREVIEW — for governed browser validation of local web/UI changes, never launch `npm run dev`, Vite, `Start-Process`, or another long-lived preview server through shell commands. Invoke `browser.open` through `omnix_capability` with input `{\"workspace_preview\": true, \"path\": \"/<route>\"}`. Omnix resolves the exact run worktree, allocates the loopback port, and owns preview cleanup. Finish with the required deterministic `browser.assert_*` proof; a passing assertion automatically tears down the workspace preview and browser session, so do not call `browser.close` merely for cleanup.
"""


# Keep the internal durable planning tool available whenever coding quality is
# active. Pi's --tools flag filters extension tools as well as built-ins, so the
# broker extension registering omnix_plan is insufficient unless argv includes
# it. This adds no capability authority: every plan decision remains server-side.
_CORE_PI_RPC_ARGV = getattr(
    _pi_runtime_core,
    "_omnix_base_pi_rpc_argv",
    _imported_core_pi_rpc_argv,
)
_pi_runtime_core._omnix_base_pi_rpc_argv = _CORE_PI_RPC_ARGV


def pi_rpc_argv(spec: AgentRunSpec, *, pi_path: str = "pi") -> list[str]:
    argv = list(_CORE_PI_RPC_ARGV(spec, pi_path=pi_path))
    planning_enabled = (
        spec.profile == "coding"
        and "diff" in spec.expected_artifacts
        and spec.quality_policy != "off"
    )
    if not planning_enabled:
        return argv
    if "--tools" in argv:
        index = argv.index("--tools") + 1
        tools = {item for item in str(argv[index]).split(",") if item}
        tools.add("omnix_plan")
        argv[index] = ",".join(sorted(tools))
    elif "--no-builtin-tools" in argv:
        index = argv.index("--no-builtin-tools")
        argv[index:index + 1] = ["--tools", "omnix_plan"]
    else:
        argv.extend(["--tools", "omnix_plan"])
    return argv


_pi_runtime_core.pi_rpc_argv = pi_rpc_argv


# Pi can report provider failures inside message_end/turn_end rather than through
# a top-level error event. The core normalizer historically treated those turns
# as ordinary assistant messages, allowing a usage/quota failure to look like a
# successful settle and later consume stalled-run recovery attempts. Keep the
# core implementation stable, but install a narrow public-runtime normalization
# hook that turns terminal provider failures into explicit run failures.
_CORE_NORMALIZE_PI_EVENT = getattr(
    _pi_runtime_core,
    "_omnix_base_normalize_pi_event",
    _pi_runtime_core.normalize_pi_event,
)
_pi_runtime_core._omnix_base_normalize_pi_event = _CORE_NORMALIZE_PI_EVENT
_LAST_PROVIDER_FAILURE: dict[str, str] = {}


def _provider_failure_event(
    run_id: str,
    payload: dict[str, object],
    *,
    task_revision_id: str | None = None,
) -> AgentEvent | None:
    event_type = str(payload.get("type") or "")
    if event_type not in {"message_end", "turn_end"}:
        return None
    message = payload.get("message")
    if not isinstance(message, dict):
        return None
    stop_reason = str(message.get("stopReason") or "").strip().casefold()
    error_message = str(message.get("errorMessage") or "").strip()
    # Intentional pause/cancel/recovery aborts also carry errorMessage="Request aborted".
    # Only provider terminal stop reasons are failures here; abort remains a normal
    # control-flow boundary handled by the existing resume machinery.
    if stop_reason not in {"error", "failed"}:
        return None
    if not error_message:
        error_message = f"Pi model turn ended with stopReason={stop_reason or 'error'}"

    lowered = error_message.casefold()
    provider_error_code = "model_provider_error"
    retryable: bool | None = None
    error_scope: str | None = None
    # The Omnix model gateway intentionally uses a structured non-429 error for
    # local run budgets. Preserve that identity through Pi instead of collapsing
    # it into a provider transport/rate-limit failure; reviewer orchestration can
    # then retry a local reviewer circuit breaker without lying about the cause.
    if (
        "agent_budget_error" in lowered
        or "budget_output_tokens_" in lowered
        or "budget_max_" in lowered
        or "budget_cost_unmeterable_provider" in lowered
    ):
        provider_error_code = "agent_run_budget_exhausted"
        retryable = False
        error_scope = "run"
    elif "usagelimitexceeded" in lowered or "usage limit" in lowered:
        provider_error_code = "model_usage_limit_exceeded"
    elif "rate limit" in lowered or "ratelimit" in lowered or "too many requests" in lowered:
        provider_error_code = "model_rate_limit_exceeded"
        retryable = True
        error_scope = "provider"
    elif "unauthorized" in lowered or "invalid_api_key" in lowered or "authentication" in lowered:
        provider_error_code = "model_authentication_failed"
        retryable = False
        error_scope = "provider"

    # Pi often repeats the same failed provider result in both message_end and
    # turn_end. Emit one durable run failure per unique provider failure so the
    # service does not process two terminal transitions for the same turn.
    signature = f"{provider_error_code}:{error_message}"
    if _LAST_PROVIDER_FAILURE.get(run_id) == signature:
        return None
    _LAST_PROVIDER_FAILURE[run_id] = signature
    return AgentEvent(
        run_id=run_id,
        event_type="run.failed",
        payload={
            "source": "pi",
            "error": f"{provider_error_code}: {error_message}"[:2000],
            "provider_error_code": provider_error_code,
            "provider_error_message": error_message[:2000],
            "task_revision_id": task_revision_id,
            **({"retryable": retryable} if retryable is not None else {}),
            **({"error_scope": error_scope} if error_scope is not None else {}),
        },
    )


def normalize_pi_event(
    run_id: str,
    payload: dict[str, object],
    *,
    task_revision_id: str | None = None,
) -> AgentEvent | None:
    provider_failure = _provider_failure_event(
        run_id,
        payload,
        task_revision_id=task_revision_id,
    )
    if provider_failure is not None:
        return provider_failure
    if (
        str(payload.get("type") or "") in {"message_end", "turn_end"}
        and run_id in _LAST_PROVIDER_FAILURE
    ):
        return None
    # Once a provider terminal failure has been emitted, Pi may still publish
    # the mechanical agent_settled event for that failed turn. Suppress it so a
    # failed provider request cannot re-enter the quality state machine as an
    # apparent successful settle.
    if str(payload.get("type") or "") == "agent_settled" and run_id in _LAST_PROVIDER_FAILURE:
        return None
    return _CORE_NORMALIZE_PI_EVENT(
        run_id,
        payload,
        task_revision_id=task_revision_id,
    )


# PiRpcSession resolves normalize_pi_event from pi_runtime_core at execution
# time, so bind the public hardened normalizer there as well. This preserves the
# split core/wrapper architecture while making every Pi session observe the same
# provider-failure semantics.
_pi_runtime_core.normalize_pi_event = normalize_pi_event


class PiAgentRuntime(_CorePiAgentRuntime):
    @staticmethod
    def _initial_prompt(
        spec: AgentRunSpec,
        *,
        reference_context: str = "",
    ) -> str:
        base = _CorePiAgentRuntime._initial_prompt(
            spec,
            reference_context=reference_context,
        )
        if spec.profile not in {"coding", "coding-reviewer"}:
            return base

        objective = spec.objective or spec.task
        guidance, guidance_digest = compile_repository_guidance(
            spec.workspace,
            objective=objective,
        )
        skills, skills_digest = compile_coding_skills(profile=spec.profile)
        execution = {
            "provider_id": spec.model.provider_id,
            "model_id": spec.model.model_id,
            "requested_reasoning_effort": spec.model.parameters.get("requested_reasoning_effort"),
            "resolved_reasoning_effort": spec.model.reasoning_effort,
            "reasoning_effort_source": spec.model.parameters.get("reasoning_effort_source"),
            "quality_policy": spec.quality_policy,
            "repository_guidance_digest": guidance_digest,
            "curated_skills_digest": skills_digest,
        }
        sections = [
            base,
            "Resolved Omnix execution profile JSON:\n" + json.dumps(execution, sort_keys=True, default=str),
            "Omnix-compiled repository guidance:\n" + guidance,
            "Omnix allowlisted coding methodology skills:\n" + (skills or "none"),
        ]
        if spec.profile == "coding":
            sections.append(_ENGINEERING_WORKFLOW)
        else:
            sections.append(
                "INDEPENDENT REVIEW MODE: remain read-only, inspect the immutable snapshot critically, "
                "do not propose authority expansion, do not modify files, and return the structured verdict "
                "requested by the review task. Reviewer process success is not approval."
            )
        return "\n\n".join(sections)

    def command_with_context(
        self,
        command: AgentRunCommand,
        *,
        reference_context: str = "",
        reference_images: list[dict[str, str]] | None = None,
    ) -> AgentRunSnapshot:
        """Dispatch restarted recovery without aborting a fresh Pi turn.

        Most stalled-run stages recreate the Pi session and immediately issue a
        durable ``resume`` command. The recreated session has already started
        its initial prompt, so the generic interrupted-turn path would abort
        that fresh request and then race a second prompt, which Pi rejects as
        "Agent is already processing". Recovery is authoritative steering of
        that fresh active turn. Self-review recovery intentionally reuses an
        existing interrupted session and therefore keeps the core abort/prompt
        semantics needed to clear that genuinely stale turn.
        """
        if command.command_type != "resume" or command.payload.get("recovery_attempt") is None:
            return super().command_with_context(
                command,
                reference_context=reference_context,
                reference_images=reference_images,
            )

        raw_message = str(command.payload.get("message") or "")
        if "This is an internal quality/self-review turn that did not finish its protocol." in raw_message:
            return super().command_with_context(
                command,
                reference_context=reference_context,
                reference_images=reference_images,
            )

        with self._lock:
            session = self._sessions.get(command.run_id)
            snapshot = self._snapshots.get(command.run_id)
            if session is None or snapshot is None:
                raise KeyError(command.run_id)

            snapshot = snapshot.model_copy(
                update={
                    "status": "running",
                    "desired_state": "running",
                    "revision": snapshot.revision + 1,
                }
            )
            message = raw_message or "Resume the task from the current state and re-check your work."
            message = self._authoritative_follow_up_prompt(snapshot.spec, message)

            if bool(getattr(session, "_turn_active", False)):
                # Pi explicitly supports steering while a turn is processing.
                # Do not abort the freshly restarted initial turn.
                session.steer(message)
                dispatch = "steer"
            else:
                session.prompt(message)
                dispatch = "prompt"

            self._snapshots[command.run_id] = snapshot
            log_agent_activity(
                "runtime.recovery.dispatched",
                category="runtime",
                run_id=command.run_id,
                fields={
                    "command_id": command.command_id,
                    "recovery_attempt": command.payload.get("recovery_attempt"),
                    "dispatch": dispatch,
                    "status": snapshot.status,
                    "revision": snapshot.revision,
                },
            )
            return snapshot


__all__ = [
    "PiAgentRuntime",
    "PiRpcSession",
    "build_agent_environment",
    "normalize_pi_event",
    "pi_broker_extension_path",
    "pi_guard_extension_path",
    "pi_model_provider_extension_path",
    "pi_rpc_argv",
]
