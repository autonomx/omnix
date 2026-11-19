"""An action a live call asked for (``[[do: …]]``): one job per task, which reads or proposes and never writes.

The call's stream validated the request against the speaker's grants and the action's typed input before it was
recorded (``assistant_tools.voice_actions``). After the reply's commit, ``live_call_tasks`` starts this job once per
task id. The job branches on the action's effect:

- A read runs through ``execute_capability`` under the chat's unapproved grant, so the tool's own policy decides;
  its result is appended as the task's result message and the call reports it.
- A write is never run here, whatever the per-action settings say (``policy_floor="always_ask"``). A device is
  resolved to exactly one device first, the request is reviewed, and the task's result message is the pending
  proposal, with a question built here. The person confirms it in the call (``live_agent_store``) or with a button.

No approval is recorded by the job: no one has approved anything yet.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

JOB_MODULE = "chat"
JOB_TYPE = "chat.live_call_action"
# Where a proposal came from; ``live_agent_store`` applies the call's confirmation rule to these.
LIVE_CALL_ORIGIN = "live_call"
_RESULT_CHARS = 1200
_LISTED = 12

_THREADS_LOCK = threading.Lock()
_THREAD_JOB_IDS: set[str] = set()


class LiveCallActionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    user_message_id: str = Field(min_length=1)
    capability: str = Field(min_length=1, max_length=64)
    input: dict[str, Any] = Field(default_factory=dict)
    effect: Literal["read", "write"]
    # The speaker who asked; a write's proposal runs only while they still hold its ability (companion 5.2).
    owner: str = Field(default="", max_length=200)


class _ActionFailed(Exception):
    """The task fails with this code-built line, which the report may tell."""


def begin_call_action(job_store: Any, session: Any, task: dict[str, Any], *, task_id: str, user_message_id: str,
                      chat_store: Any = None) -> Any:
    """Create the task's job once (keyed by its task id) and start it; None when the recorded task is not valid."""
    from app.jobs.models import CreateJobRequest, ResourceClass
    from app.persistence.runtime import uses_postgresql_runtime

    actions = _call_actions()
    if actions is None:
        return None
    check = actions.check(str(task.get("capability") or ""), task.get("input"))
    if not check.ok or check.effect is None:
        return None
    payload = LiveCallActionInput(
        session_id=session.id, task_id=task_id, user_message_id=user_message_id,
        capability=check.capability, input=check.input or {}, effect=check.effect,
        owner=str(task.get("owner") or ""),
    )
    job = job_store.create_job_once(CreateJobRequest(
        owner_id=session.id, module=JOB_MODULE, type=JOB_TYPE, resource_class=ResourceClass.NETWORK,
        input_payload=payload.model_dump(mode="json"),
    ), idempotency_key=task_id)
    if uses_postgresql_runtime():
        return job  # the durable worker runs it (``chat.feature``)
    return _start_inline(job_store, job, chat_store)


def _start_inline(job_store: Any, job: Any, chat_store: Any) -> Any:
    from app.jobs.models import JobStatus

    current = job_store.get_job(job.id) or job
    if current.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELED}:
        return current
    with _THREADS_LOCK:
        if job.id in _THREAD_JOB_IDS:
            return current
        _THREAD_JOB_IDS.add(job.id)

    def run() -> None:
        try:
            execute_call_action(job_store, running, chat_store=chat_store)
        except Exception:  # noqa: BLE001 - the task reads as failed
            logger.warning("call action %s: failed to run", job.id, exc_info=True)
            try:
                _fail(job_store, job.id, "call_action_crashed", "That could not be finished.", retryable=False)
            except Exception:  # noqa: BLE001
                logger.warning("call action %s: failure not recorded", job.id, exc_info=True)
        finally:
            with _THREADS_LOCK:
                _THREAD_JOB_IDS.discard(job.id)

    thread = threading.Thread(target=run, name=f"omnix-call-action-{job.id.removeprefix('job:')[:8]}", daemon=True)
    try:
        running = job_store.mark_running(job.id) or current
        thread.start()
    except BaseException:
        with _THREADS_LOCK:
            _THREAD_JOB_IDS.discard(job.id)
        raise
    return running


def execute_call_action(job_store: Any, job: Any, *, chat_store: Any) -> Any:
    """Run one call action's job: a read's result, or a write's proposal, saved as the task's result message."""
    from app.jobs.models import CompleteJobRequest, JobStatus
    from pydantic import ValidationError

    try:
        request = LiveCallActionInput.model_validate(job.input_payload or {})
    except ValidationError as exc:
        return _fail(job_store, job.id, "call_action_invalid", str(exc)[:500], retryable=False)
    if chat_store is None:
        return _fail(job_store, job.id, "call_action_chat_unavailable", "The chat service is not composed.",
                     retryable=True)
    current = job_store.get_job(job.id)
    if current is None:
        return job
    if current.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELED}:
        return current
    if current.cancel.requested or current.status == JobStatus.CANCEL_REQUESTED:
        return job_store.finalize_cancel(job.id, "cancelled from the live call") if callable(
            getattr(job_store, "finalize_cancel", None)) else current
    if current.status != JobStatus.RUNNING:
        current = job_store.mark_running(job.id) or current
    try:
        content, metadata = _read(request) if request.effect == "read" else _propose(request)
    except _ActionFailed as exc:
        return _fail(job_store, job.id, "call_action_failed", str(exc), retryable=False)
    from app.jobs.inline_execution import require_execution_authority

    require_execution_authority(job_store, job.id)
    appended = chat_store.append_assistant_message(request.session_id, content, {
        **metadata, "generation_status": "completed", "turn_id": request.task_id,
        "call_task_id": request.task_id, "call_task_asked_in": request.user_message_id,
    })
    if appended is None:
        return _fail(job_store, job.id, "call_action_session_missing", "The chat is gone.", retryable=False)
    _session, message, _duplicate = appended
    completed = job_store.complete_job(job.id, CompleteJobRequest(output_refs=[{
        "type": "live_call_action", "session_id": request.session_id, "message_id": message.id,
        "capability": request.capability, "effect": request.effect,
    }]))
    return completed or current


def _call_actions() -> Any:
    """The assistant tools' side of a call action (``CHAT_CALL_ACTIONS``), or None when they are not composed."""
    from app.platform.chat.contracts import CHAT_CALL_ACTIONS
    from app.runtime.ports import optional

    return optional(CHAT_CALL_ACTIONS)


def _required_actions() -> Any:
    actions = _call_actions()
    if actions is None:
        raise _ActionFailed("The assistant tools are not available.")
    return actions


def _run_read(request: LiveCallActionInput, capability: str, data: dict[str, Any]) -> Any:
    from app.capabilities.executor import CapabilityGrant, execute_capability

    actions = _required_actions()
    # Unapproved, no floor: the tool's configured policy decides whether this read may run on its own.
    payload = execute_capability(
        CapabilityGrant("chat", request.session_id),
        actions.tool_request(session_id=request.session_id, task_id=request.task_id, capability=capability,
                             data=data).model_copy(update={"proposal_id": None}),
        user_request=actions.describe(capability, data),
    )
    return payload.execution_result


def _read(request: LiveCallActionInput) -> tuple[str, dict[str, Any]]:
    result = _run_read(request, request.capability, request.input)
    if result.error:
        raise _ActionFailed(_bounded(result.result_summary or "That could not be read.", 200))
    return _read_text(request.capability, result), {"live_call_action": {
        "capability": request.capability, "effect": "read", "tool_result": _bounded(result.result_summary, 200),
    }}


def _read_text(capability: str, result: Any) -> str:
    output = result.output if isinstance(result.output, dict) else {}
    summary = str(result.result_summary or "").strip()
    if capability == "home.list_devices":
        devices = [row for row in output.get("devices") or [] if isinstance(row, dict)]
        names = [f"{_bounded(str(row.get('name') or ''), 60)} ({'on' if row.get('on') else 'off'})"
                 for row in devices[:_LISTED]]
        more = f", and {len(devices) - _LISTED} more" if len(devices) > _LISTED else ""
        summary = f"{len(devices)} home device{'s' if len(devices) != 1 else ''}" + (
            f": {', '.join(names)}{more}." if names else ".")
    elif capability == "calendar.read_availability":
        events = [row for row in output.get("events") or [] if isinstance(row, dict)]
        rows = [f"{_bounded(str(row.get('title') or 'Untitled'), 80)}, {row.get('start_time', '')} to "
                f"{row.get('end_time', '')}" for row in events[:_LISTED]]
        summary = ("Nothing on the calendar then." if not events else
                   f"{len(events)} event{'s' if len(events) != 1 else ''} then: {'; '.join(rows)}.")
    return _bounded(summary, _RESULT_CHARS)


def _propose(request: LiveCallActionInput) -> tuple[str, dict[str, Any]]:
    actions = _required_actions()
    data = dict(request.input)
    name = ""
    if request.capability == "home.set_state":
        device_id, name = _resolve_device(request, str(data.get("target") or ""))
        data["target"] = device_id
    tool_request = actions.tool_request(session_id=request.session_id, task_id=request.task_id,
                                        capability=request.capability, data=data)
    # Reviewed as asking, whatever the per-action settings: a call's write always waits for the person.
    decision = actions.review(tool_request, approved=False, policy_floor="always_ask")
    if not decision.allowed:
        raise _ActionFailed(_bounded(decision.result_summary or "That is not allowed now.", 200))
    return proposal_question(request.capability, data, device_name=name), {
        "pending_governed_tool_request": tool_request.model_dump(mode="json"),
        "governed_tool_execution_status": "pending",
        "governed_proposal_origin": LIVE_CALL_ORIGIN,
        "live_call_action": {"capability": request.capability, "effect": "write", "owner": request.owner},
    }


def _normalised(text: str) -> str:
    return " ".join("".join(ch if ch.isalnum() else " " for ch in text.casefold()).split())


def _resolve_device(request: LiveCallActionInput, target: str) -> tuple[str, str]:
    """The one device a spoken target names: an equal name, else a unique name containing it."""
    result = _run_read(request, "home.list_devices", {})
    if result.error:
        raise _ActionFailed("I couldn't reach the home devices.")
    devices = [row for row in (result.output or {}).get("devices") or []
               if isinstance(row, dict) and str(row.get("id") or "").strip()]
    wanted = _normalised(target)
    spoken = _bounded(target, 80)
    if not wanted:
        raise _ActionFailed(f"I couldn't find {spoken}.")
    equal = [row for row in devices if _normalised(str(row.get("name") or "")) == wanted]
    matches = equal or [row for row in devices if wanted in _normalised(str(row.get("name") or ""))]
    if len(matches) != 1:
        raise _ActionFailed(f"I couldn't find {spoken}." if not matches
                            else f"More than one device matches {spoken}.")
    device = matches[0]
    return str(device["id"]), _bounded(str(device.get("name") or device["id"]), 80)


def _when(data: dict[str, Any]) -> str:
    zone_name = str(data.get("timezone") or "")
    zone = ZoneInfo(zone_name)
    start = datetime.fromisoformat(str(data.get("start_time")).replace("Z", "+00:00"))
    end = datetime.fromisoformat(str(data.get("end_time")).replace("Z", "+00:00"))
    start = start.astimezone(zone) if start.tzinfo else start.replace(tzinfo=zone)
    end = end.astimezone(zone) if end.tzinfo else end.replace(tzinfo=zone)
    day = f"{start:%a} {start.day} {start:%b}"
    if end.date() == start.date():
        return f"{day}, {start:%H:%M}–{end:%H:%M} {zone_name}"
    return f"{day} {start:%H:%M} to {end:%a} {end.day} {end:%b} {end:%H:%M} {zone_name}"


def proposal_question(capability: str, data: dict[str, Any], *, device_name: str = "") -> str:
    """The question a proposal asks, question first, built from the validated input only."""
    if capability == "home.set_state":
        return f"Turn {'on' if data.get('on') else 'off'} {device_name or data.get('target')}? Say confirm or cancel."
    if capability == "calendar.create_event":
        title = _bounded(str(data.get("title") or ""), 120)
        return f"Add ‘{title}’ on {_when(data)}? Say confirm or cancel."
    return f"Run {capability}? Say confirm or cancel."


def _bounded(text: str, limit: int) -> str:
    compact = " ".join(str(text or "").split())
    return compact if len(compact) <= limit else compact[:limit].rsplit(" ", 1)[0] + " …"


def _fail(job_store: Any, job_id: str, code: str, message: str, *, retryable: bool) -> Any:
    from app.jobs.models import FailJobRequest

    logger.info("call action %s failed: %s", job_id, code)
    return job_store.fail_job(job_id, FailJobRequest(code=code, message=message, retryable=retryable,
                                                     details={"job_type": JOB_TYPE}))


def execute_call_action_job(context: Any, job: Any) -> Any:
    """The durable worker's handler (``chat.feature``)."""
    chat_store = getattr(context.services, "chat", None) if context.services is not None else None
    return execute_call_action(context.job_store, job, chat_store=chat_store)


__all__ = [
    "JOB_TYPE", "LIVE_CALL_ORIGIN", "LiveCallActionInput", "begin_call_action", "execute_call_action",
    "execute_call_action_job", "proposal_question",
]
