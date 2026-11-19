"""Tasks a live call started, such as research it asked for: started once, after the reply that asked is committed.

A call's model asks for background work with a request line (``live_voice.llm.call_tools``). The reply's stream
checks the speaker's grant in code and records the request on the reply (``call_tasks``); nothing runs yet. Once the
reply is committed, each granted request starts here through its owner's port, keyed by its task id, so a retried
commit, a poll or recovery never starts the same work twice, and an early start or a discarded reply starts nothing.

The start's outcome is written back on the reply (``start``, ``job_id``). A task that did not start is never started
later: research that begins long after the person was told it had is worse than an honest "I couldn't start that".
A task's state afterwards is its job's (``list_call_tasks``).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# The background abilities a task can be (assistant_tools.owner_grants): deep research starts through its port;
# an action (a task with a ``capability``) through ``live_call_actions``.
_DEEP_RESEARCH = "deep_research"

# How a start went, recorded on the reply.
STARTED = "started"
REFUSED = "refused"  # the owner said no now (e.g. the release policy, or nothing configured)
FAILED = "failed"  # the start raised

# The call asks about recent tasks only; an older one is history in the chat.
TASK_WINDOW = timedelta(minutes=30)
# A granted task with no recorded start this long after its reply was committed never started (the process stopped
# between the commit and the start).
START_GRACE = timedelta(seconds=60)

CallTaskState = Literal["open", "completed", "failed", "cancelled", "not_started"]

# A write a call asked for is proposed, not run (``live_call_actions``): its result message is the proposal. The
# report speaks the proposal's own question, stamped when it starts so the person's next turn can confirm it
# (``live_agent_store``), and marks the proposal reported when delivered; no second message is made.
REPORT_STARTED_AT = "report_started_at"
PROPOSAL_REPORTED = "call_task_reported"
# A report stream that failed after its stamp may be offered again after this long.
PROPOSAL_RESTAMP = timedelta(seconds=10)
# The person's answer to a proposal's question counts this long after the question began.
PROPOSAL_CONFIRM_WINDOW = timedelta(minutes=2)
# A voice turn's marker that the person began speaking after a report's audio started (the report's turn id).
HEARD_TURN_ID = "heard_turn_id"

_OPEN_JOBS = frozenset({"queued", "leased", "running", "waiting", "retrying", "paused", "cancel_requested"})
_FAILED_JOBS = frozenset({"failed", "stale"})


class CallTask(BaseModel):
    """One task a call asked for, as the call shows it."""

    task_id: str
    ability: str
    query: str = ""
    state: CallTaskState
    asked_at: str
    settled_at: str | None = None
    result_message_id: str | None = None
    reported: bool = False


class CallTaskList(BaseModel):
    tasks: list[CallTask] = Field(default_factory=list)


def call_task_id(user_message_id: str, index: int) -> str:
    """The task's identity: the turn that asked and the request's place in its reply."""
    return f"call-task:{user_message_id}:{index}"


def _start_action(job_store: Any, session: Any, user_message_id: str, task: dict[str, Any], task_id: str,
                  chat_store: Any) -> dict[str, Any]:
    from app.platform.chat.live_call_actions import begin_call_action

    try:
        job = begin_call_action(job_store, session, task, task_id=task_id, user_message_id=user_message_id,
                                chat_store=chat_store)
    except Exception:  # noqa: BLE001 - the reply stands; the task did not start
        logger.warning("call task %s: action could not start", task_id, exc_info=True)
        return {"start": FAILED}
    if job is None:
        logger.warning("call task %s: the recorded action is not valid", task_id)
        return {"start": REFUSED}
    return {"start": STARTED, "job_id": str(getattr(job, "id", "") or "") or None}


def _granted_owner(session: Any, task: dict[str, Any]) -> str | None:
    """Who asked for the task (a guest's turn records the guest), if they still hold its ability; read now."""
    from app.platform.chat.contracts import CHAT_CALL_ACTIONS
    from app.runtime.ports import optional

    actions = optional(CHAT_CALL_ACTIONS)
    if actions is None:
        return None
    owner = str(task.get("owner") or "") or actions.call_owner(session)
    granted = actions.granted(owner, ability=str(task.get("ability") or ""),
                              capability=str(task.get("capability") or ""))
    return owner if granted else None


def _start_one(job_store: Any, session: Any, user_message_id: str, task: dict[str, Any],
               chat_store: Any = None) -> dict[str, Any]:
    """Start one granted task; returns what to record about the start."""
    from app.platform.chat.contracts import CHAT_RESEARCH
    from app.runtime.ports import optional

    task_id = call_task_id(user_message_id, int(task.get("index") or 0))
    owner = _granted_owner(session, task)
    if owner is None:
        logger.info("call task %s: its speaker does not hold %r now", task_id, task.get("ability"))
        return {"start": REFUSED, "reason": "not_granted"}
    task = {**task, "owner": owner}
    if task.get("capability"):
        return _start_action(job_store, session, user_message_id, task, task_id, chat_store)
    if task.get("ability") != _DEEP_RESEARCH:
        logger.warning("call task %s: no starter for ability %r", task_id, task.get("ability"))
        return {"start": REFUSED}
    research = optional(CHAT_RESEARCH)
    if research is None:
        logger.warning("call task %s: research is not available", task_id)
        return {"start": REFUSED}
    try:
        job = research.begin_call_research(
            session, str(task.get("query") or ""), task_id=task_id, user_message_id=user_message_id,
            job_store=job_store,
        )
    except Exception:  # noqa: BLE001 - the reply stands; the task did not start
        logger.warning("call task %s: research could not start", task_id, exc_info=True)
        return {"start": FAILED}
    if job is None:
        logger.warning("call task %s: deep research is not available now", task_id)
        return {"start": REFUSED}
    return {"start": STARTED, "job_id": str(getattr(job, "id", "") or "") or None}


def start_call_tasks(job_store: Any, session: Any, user_message_id: str, tasks: Any, *,
                     chat_store: Any = None) -> list[dict[str, Any]]:
    """Start the granted requests a committed reply recorded; returns the tasks with their start outcomes.

    The reply is already saved, so a task that cannot start is logged and recorded, never raised: the call goes on.
    A task that is not granted, or was already started, is returned as it was.
    """
    recorded: list[dict[str, Any]] = []
    for task in tasks if isinstance(tasks, list) else []:
        if not isinstance(task, dict):
            continue
        if task.get("allowed") is not True or task.get("start"):
            recorded.append(dict(task))
            continue
        recorded.append({**task, **_start_one(job_store, session, user_message_id, task, chat_store)})
    return recorded


def _reply_to(session: Any, user_message_id: str) -> Any:
    return next(
        (message for message in reversed(getattr(session, "messages", None) or [])
         if message.role == "assistant" and message.metadata.get("reply_to_message_id") == user_message_id),
        None,
    )


def start_and_record_call_tasks(chat_store: Any, job_store: Any, session: Any, user_message_id: str,
                                tasks: Any) -> list[dict[str, Any]]:
    """Start a committed reply's tasks and write each start's outcome back on the reply."""
    recorded = start_call_tasks(job_store, session, user_message_id, tasks, chat_store=chat_store)
    reply = _reply_to(session, user_message_id) if session is not None else None
    if reply is None or not recorded or recorded == tasks:
        return recorded
    try:
        chat_store.update_message_metadata(session_id=session.id, message_id=reply.id,
                                           metadata={"call_tasks": recorded})
    except Exception:  # noqa: BLE001 - the work started; only its record is missing, which reads as not started
        logger.warning("call tasks of %s: start outcome not recorded", reply.id, exc_info=True)
    return recorded


def _parse_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _job_state(job_store: Any, job_id: str) -> tuple[CallTaskState, str | None]:
    try:
        job = job_store.get_job(job_id)
    except Exception:  # noqa: BLE001 - an unreadable job reads as still open; the next poll tries again
        logger.warning("call task job %s: unreadable", job_id, exc_info=True)
        return "open", None
    if job is None:
        return "failed", None
    status = str(getattr(job.status, "value", job.status))
    settled_at = getattr(job, "completed_at", None) or getattr(job, "updated_at", None)
    if status in _OPEN_JOBS:
        return "open", None
    if status == "completed":
        return "completed", settled_at
    if status == "canceled":
        return "cancelled", settled_at
    if status in _FAILED_JOBS:
        return "failed", settled_at
    return "open", None


def _task_state(job_store: Any, task: dict[str, Any], asked: datetime | None,
                now: datetime) -> tuple[CallTaskState, str | None]:
    if task.get("allowed") is not True or task.get("start") in {REFUSED, FAILED}:
        return "not_started", None
    job_id = task.get("job_id")
    if task.get("start") == STARTED and job_id:
        return _job_state(job_store, str(job_id))
    if task.get("start") == STARTED:
        return "failed", None
    if asked is not None and now - asked < START_GRACE:
        return "open", None  # the start is still on its way
    return "not_started", None


def _iter_call_tasks(session: Any, now: datetime):
    """(reply, user message id, task, asked time) for each task asked for in the window, oldest first."""
    for message in getattr(session, "messages", None) or []:
        tasks = message.metadata.get("call_tasks") if message.role == "assistant" else None
        user_message_id = message.metadata.get("reply_to_message_id") if tasks else None
        if not isinstance(tasks, list) or not user_message_id:
            continue
        asked = _parse_time(message.created_at)
        if asked is not None and now - asked > TASK_WINDOW:
            continue
        for task in tasks:
            if isinstance(task, dict):
                yield message, str(user_message_id), task, asked


def is_call_proposal(message: Any) -> bool:
    """Whether a message is a write proposal a live call made."""
    from app.platform.chat.live_call_actions import LIVE_CALL_ORIGIN

    metadata = getattr(message, "metadata", None) or {}
    return metadata.get("governed_proposal_origin") == LIVE_CALL_ORIGIN and bool(metadata.get("call_task_id"))


def _proposal_settled(message: Any) -> bool:
    """A proposal needs no report once delivered, or once decided some other way (e.g. its button)."""
    metadata = message.metadata
    return metadata.get(PROPOSAL_REPORTED) is True or metadata.get("governed_tool_execution_status") != "pending"


def _report_in_progress(message: Any, now: datetime) -> bool:
    started = _parse_time(message.metadata.get(REPORT_STARTED_AT))
    return started is not None and now - started < PROPOSAL_RESTAMP


def list_call_tasks(session: Any, job_store: Any, *, now: datetime | None = None) -> CallTaskList:
    """The tasks the call asked for in the last half hour, with their state read from their jobs."""
    now = now or datetime.now(timezone.utc)
    results: dict[str, Any] = {}
    reported: set[str] = set()
    for message in getattr(session, "messages", None) or []:
        if message.role != "assistant":
            continue
        if message.metadata.get("call_task_id"):
            results.setdefault(str(message.metadata["call_task_id"]), message)
        if message.metadata.get("task_report_for"):
            reported.add(str(message.metadata["task_report_for"]))
    views: list[CallTask] = []
    for reply, user_message_id, task, asked in _iter_call_tasks(session, now):
        task_id = call_task_id(user_message_id, int(task.get("index") or 0))
        state, settled_at = _task_state(job_store, task, asked, now)
        result = results.get(task_id)
        if result is not None and state in {"open", "completed"}:
            # The result is saved before its job completes; the call can tell it as soon as it is there.
            state, settled_at = "completed", settled_at or result.created_at
        views.append(CallTask(
            task_id=task_id, ability=str(task.get("ability") or ""), query=str(task.get("query") or ""),
            state=state, asked_at=str(reply.created_at), settled_at=settled_at,
            result_message_id=result.id if result is not None else None,
            # A cancelled task gets no report: the person stopped it.
            reported=task_id in reported or state == "cancelled" or (
                result is not None and is_call_proposal(result) and _proposal_settled(result)),
        ))
    return CallTaskList(tasks=views)


def find_call_task(session: Any, task_id: str, *, now: datetime | None = None) -> dict[str, Any] | None:
    """The recorded task with this id in this session's window, or None (a task of another chat is never found)."""
    now = now or datetime.now(timezone.utc)
    for _reply, user_message_id, task, _asked in _iter_call_tasks(session, now):
        if call_task_id(user_message_id, int(task.get("index") or 0)) == task_id:
            return task
    return None


def cancel_call_task(session: Any, job_store: Any, task_id: str, *, now: datetime | None = None) -> CallTask | None:
    """Cancel an open task's job; returns the task's state afterwards, or None when this chat has no such task."""
    from app.jobs.models import CancelJobRequest

    now = now or datetime.now(timezone.utc)
    task = find_call_task(session, task_id, now=now)
    if task is None:
        return None
    if task.get("start") == STARTED and task.get("job_id"):
        job_store.cancel_job(str(task["job_id"]), CancelJobRequest(reason="cancelled from the live call"))
    return next((view for view in list_call_tasks(session, job_store, now=now).tasks if view.task_id == task_id),
                None)


# The call reports a settled task on its own, through the initiative authority. The server names the report
# (``initiative_candidate``) and checks it again when the report starts (``task_report_material``); the reason the
# call sends back only names the task, and never reaches the prompt.
TASK_REPORT_REASON = "task_report:"
TASK_REPORT_TURN = "task-report:"
# A completed result goes into the report's prompt bounded; the full write-up stays in the chat.
REPORT_RESULT_CHARS = 1500
_REPORTABLE = frozenset({"completed", "failed", "not_started"})
# How a call task's result appears in later live prompts: the report and the task state carry what the call needs,
# and an untrusted write-up never sits in the history as the assistant's own words.
_HISTORY_QUERY_CHARS = 120


class InitiativeCandidate(BaseModel):
    """The one initiative the server would have the call take now, or none."""

    reason: str | None = None


class TaskReportMaterial(BaseModel):
    """What a report turn may say about one settled task of this chat, read from the server's own records."""

    task: CallTask
    turn_id: str
    # The completed result's text, bounded, as untrusted tool output; empty when the task did not complete.
    result_text: str = ""
    # A write proposal's own question, built by code, spoken as it is (no model); with the message that holds it.
    proposal_text: str = ""
    proposal_message_id: str | None = None


def task_report_reason(task_id: str) -> str:
    return f"{TASK_REPORT_REASON}{task_id}"


def task_report_turn_id(task_id: str) -> str:
    return f"{TASK_REPORT_TURN}{task_id}"


def reported_task_id(*, reason: str | None = None, turn_id: str | None = None) -> str | None:
    """The task a report reason or a report turn id names, or None when it names none."""
    for value, prefix in ((reason, TASK_REPORT_REASON), (turn_id, TASK_REPORT_TURN)):
        if isinstance(value, str) and value.startswith(prefix) and value[len(prefix):].strip():
            return value[len(prefix):].strip()
    return None


def _message(session: Any, message_id: str | None) -> Any:
    return next((message for message in getattr(session, "messages", None) or [] if message.id == message_id), None)


def initiative_candidate(session: Any, job_store: Any, *, now: datetime | None = None) -> InitiativeCandidate:
    """The oldest settled task of this call with no report yet, as its report reason; otherwise no initiative.

    A proposal whose report has just started is skipped: that report is playing.
    """
    now = now or datetime.now(timezone.utc)
    for task in list_call_tasks(session, job_store, now=now).tasks:
        if task.state not in _REPORTABLE or task.reported:
            continue
        result = _message(session, task.result_message_id)
        if result is not None and is_call_proposal(result) and _report_in_progress(result, now):
            continue
        return InitiativeCandidate(reason=task_report_reason(task.task_id))
    return InitiativeCandidate()


def _bounded(text: str, limit: int) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[:limit].rsplit(" ", 1)[0] + " …"


def task_report_material(session: Any, job_store: Any, reason: str, *,
                         now: datetime | None = None) -> TaskReportMaterial | None:
    """The report a ``task_report:`` reason names, or None unless that task is this chat's, settled and unreported."""
    now = now or datetime.now(timezone.utc)
    task_id = reported_task_id(reason=reason)
    if task_id is None:
        return None
    task = next((view for view in list_call_tasks(session, job_store, now=now).tasks if view.task_id == task_id),
                None)
    if task is None or task.state not in _REPORTABLE or task.reported:
        return None
    result_text = ""
    if task.state == "completed":
        result = _message(session, task.result_message_id)
        if result is not None and is_call_proposal(result):
            if _report_in_progress(result, now) or not str(result.content or "").strip():
                return None
            return TaskReportMaterial(task=task, turn_id=task_report_turn_id(task_id),
                                      proposal_text=str(result.content).strip(), proposal_message_id=result.id)
        result_text = _bounded(getattr(result, "content", ""), REPORT_RESULT_CHARS)
        if not result_text:
            # Finished with nothing saved to tell: say it could not be finished rather than invent findings.
            task = task.model_copy(update={"state": "failed"})
    return TaskReportMaterial(task=task, turn_id=task_report_turn_id(task_id), result_text=result_text)


def claim_proposal_report(chat_store: Any, session: Any, report: TaskReportMaterial, *,
                          now: datetime | None = None) -> bool:
    """Stamp the start of a proposal's report, once: only while it is pending and unreported, with no stamp or one
    a failed report left more than ``PROPOSAL_RESTAMP`` ago. Whether this report won the stamp."""
    from app.platform.chat.message_claims import ABSENT

    now = now or datetime.now(timezone.utc)
    message = _message(session, report.proposal_message_id)
    if message is None or not is_call_proposal(message) or _report_in_progress(message, now):
        return False
    previous = message.metadata.get(REPORT_STARTED_AT)
    return bool(chat_store.claim_message_metadata(
        session_id=session.id, message_id=message.id,
        require={"governed_tool_execution_status": "pending", PROPOSAL_REPORTED: ABSENT,
                 REPORT_STARTED_AT: previous if previous is not None else ABSENT},
        patch={REPORT_STARTED_AT: now.isoformat()},
    ))


def call_proposal_message(session: Any, task_id: str) -> Any:
    """The proposal a call's task made, found only in its own chat; None when the task's result is not one."""
    return next((item for item in getattr(session, "messages", None) or []
                 if item.role == "assistant" and item.metadata.get("call_task_id") == task_id
                 and is_call_proposal(item)), None)


def mark_proposal_reported(chat_store: Any, session: Any, task_id: str) -> Any:
    """The delivered report of a proposal marks the proposal itself; returns the proposal message, or None when
    the task's result is not a proposal (its report is then saved as a message of its own)."""
    message = call_proposal_message(session, task_id)
    if message is None:
        return None
    if message.metadata.get(PROPOSAL_REPORTED) is not True:
        chat_store.update_message_metadata(session_id=session.id, message_id=message.id,
                                           metadata={PROPOSAL_REPORTED: True})
    return message


def _is_voice_turn(message: Any) -> bool:
    metadata = getattr(message, "metadata", None) or {}
    return bool(str(metadata.get("speech_segment_id") or "").strip()) or str(
        metadata.get("user_turn_id") or "").startswith("voice-user-turn:")


def proposal_confirmable(session: Any, proposal: Any, user_message: Any) -> bool:
    """Whether ``user_message`` may confirm or cancel a call's proposal: its question has begun, this is the first
    user turn after that, within ``PROPOSAL_CONFIRM_WINDOW``, and a voice turn began after the question did (the web
    sends ``heard_turn_id``). Anything else has expired; worked out on reading, so there is no status write to race."""
    started = _parse_time(proposal.metadata.get(REPORT_STARTED_AT))
    said = _parse_time(getattr(user_message, "created_at", None))
    if started is None or said is None or said < started or said - started > PROPOSAL_CONFIRM_WINDOW:
        return False
    first = next((message for message in getattr(session, "messages", None) or []
                  if message.role == "user" and (_parse_time(message.created_at) or started) >= started), None)
    if first is not None and first.id != user_message.id:
        return False
    if _is_voice_turn(user_message):
        task_id = str(proposal.metadata.get("call_task_id") or "")
        return user_message.metadata.get(HEARD_TURN_ID) == task_report_turn_id(task_id)
    return True


def proposal_button_allowed(proposal: Any, *, now: datetime | None = None) -> bool:
    """The call's Confirm/Cancel buttons act on a proposal whose question began within the window."""
    now = now or datetime.now(timezone.utc)
    started = _parse_time(proposal.metadata.get(REPORT_STARTED_AT))
    return started is not None and timedelta(0) <= now - started <= PROPOSAL_CONFIRM_WINDOW


def proposal_question_open(session: Any, *, now: datetime | None = None) -> bool:
    """Whether the chat's latest pending proposal is a call's whose question began within the window: a confirm or
    cancel said over the question is then an answer, never a remark to talk through."""
    latest = next((item for item in reversed(getattr(session, "messages", None) or [])
                   if item.role == "assistant"
                   and item.metadata.get("governed_tool_execution_status") == "pending"), None)
    return latest is not None and is_call_proposal(latest) and proposal_button_allowed(latest, now=now)


def live_history_session(session: Any) -> Any:
    """The session as later live prompts see it: each call task's result is a short stub pointing to the chat."""
    messages = list(getattr(session, "messages", None) or [])
    if not any(message.metadata.get("call_task_id") for message in messages):
        return session
    queries: dict[str, tuple[str, str]] = {}
    for message in messages:
        tasks = message.metadata.get("call_tasks") if message.role == "assistant" else None
        user_message_id = message.metadata.get("reply_to_message_id") if tasks else None
        for task in tasks if isinstance(tasks, list) and user_message_id else []:
            if isinstance(task, dict):
                queries[call_task_id(str(user_message_id), int(task.get("index") or 0))] = (
                    str(task.get("ability") or ""), str(task.get("query") or ""))
    stubbed = []
    for message in messages:
        task_id = message.metadata.get("call_task_id")
        if not task_id:
            stubbed.append(message)
            continue
        ability, query = queries.get(str(task_id), ("", ""))
        label = "research" if ability in {"", _DEEP_RESEARCH} else ability.replace("_", " ")
        about = f": {_bounded(query, _HISTORY_QUERY_CHARS)}" if query.strip() else ""
        if is_call_proposal(message):
            status = str(message.metadata.get("governed_tool_execution_status") or "pending")
            content = f"[{label} proposal{about}, {status}]"
        else:
            content = f"[{label} result{about}, see chat]"
        stubbed.append(message.model_copy(update={"content": content}))
    return session.model_copy(update={"messages": stubbed})


CALL_TASKS_HEADING = "Work you started in this call, from Omnix's own records (trust these over the conversation):"
CALL_TASKS_RULE = ("If they ask how one is going, answer from this list. Never say one is done, found or changed "
                   "unless it says so here.")
_PROPOSAL_OUTCOMES = {
    "executed": "done",
    "rejected": "not done: they cancelled it",
    "failed": "not done: it failed",
    "executing": "its outcome is not known yet",
}


def _ago(then: Any, now: datetime) -> str:
    moment = _parse_time(then)
    if moment is None:
        return ""
    minutes = int((now - moment).total_seconds() // 60)
    return "under a minute ago" if minutes < 1 else f"{minutes} min ago"


def _proposal_line(message: Any, now: datetime) -> str:
    status = str(message.metadata.get("governed_tool_execution_status") or "pending")
    if status != "pending":
        return _PROPOSAL_OUTCOMES.get(status, "not done")
    if message.metadata.get(REPORT_STARTED_AT) is None:
        return "not done yet: you will ask them to confirm it"
    if proposal_button_allowed(message, now=now):
        return "not done yet: waiting for them to say confirm or cancel"
    return "not done: the question went unanswered"


def _task_line(task: CallTask, session: Any, now: datetime) -> str:
    label = f'research "{_bounded(task.query, _HISTORY_QUERY_CHARS)}"' if task.ability == _DEEP_RESEARCH else (
        _bounded(task.query, _HISTORY_QUERY_CHARS) or task.ability.replace("_", " "))
    if task.state == "open":
        return f"- {label}: started {_ago(task.asked_at, now)}, still running."
    if task.state == "not_started":
        return f"- {label}: it could not start."
    if task.state == "cancelled":
        return f"- {label}: stopped; they cancelled it."
    if task.state == "failed":
        return f"- {label}: it could not be finished."
    result = _message(session, task.result_message_id)
    if result is not None and is_call_proposal(result):
        return f"- {label}: {_proposal_line(result, now)}."
    told = "you have told them" if task.reported else "not told yet; you will tell them when the call is quiet"
    return f"- {label}: finished {_ago(task.settled_at, now)}, the result is in the chat; {told}."


def call_tasks_prompt(session: Any, job_store: Any = None, *, now: datetime | None = None) -> str | None:
    """What the call's tasks are doing now, built from their records, for a live turn's per-turn prompt; None when
    the call started none in the window. Without it "how's that going?" could only be answered from memory."""
    now = now or datetime.now(timezone.utc)
    if next(_iter_call_tasks(session, now), None) is None:
        return None  # nothing to read: no job store call on a turn that has no tasks
    if job_store is None:
        from app.jobs import default_job_store

        job_store = default_job_store()
    tasks = list_call_tasks(session, job_store, now=now).tasks
    if not tasks:
        return None
    return "\n".join([CALL_TASKS_HEADING, *(_task_line(task, session, now) for task in tasks), CALL_TASKS_RULE])


__all__ = [
    "CALL_TASKS_HEADING",
    "call_tasks_prompt",
    "CallTask",
    "CallTaskList",
    "InitiativeCandidate",
    "TASK_REPORT_REASON",
    "TaskReportMaterial",
    "HEARD_TURN_ID",
    "PROPOSAL_CONFIRM_WINDOW",
    "PROPOSAL_REPORTED",
    "REPORT_STARTED_AT",
    "call_proposal_message",
    "call_task_id",
    "cancel_call_task",
    "claim_proposal_report",
    "is_call_proposal",
    "mark_proposal_reported",
    "proposal_button_allowed",
    "proposal_confirmable",
    "proposal_question_open",
    "find_call_task",
    "initiative_candidate",
    "list_call_tasks",
    "live_history_session",
    "reported_task_id",
    "task_report_material",
    "task_report_reason",
    "task_report_turn_id",
    "start_and_record_call_tasks",
    "start_call_tasks",
]
