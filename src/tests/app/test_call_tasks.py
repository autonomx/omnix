"""Background work a call asks for (companion roadmap 1.1): research starts after the reply is committed."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.platform.chat import live_call_tasks
from app.platform.live_voice.llm import call_tools
from app.platform.live_voice.llm.call_tools import RequestGate, parse_request
from app.platform.live_voice.llm.stream import stream_low_latency_reply
from app.providers import ChatResponse


def test_a_research_request_is_a_background_task_and_a_lookup_is_not() -> None:
    research = parse_request("[[research: best e-bikes under $2000 in 2026 || Sure, I'll dig into that.]]")
    lookup = parse_request("[[look up: weather || one sec]]")

    assert research == call_tools.AbilityRequest("deep_research", "best e-bikes under $2000 in 2026",
                                                 "Sure, I'll dig into that.")
    assert research.background and lookup is not None and not lookup.background
    assert parse_request("[[research: ]]") is None


def test_the_prompt_offers_research_only_with_its_grant() -> None:
    both = call_tools.abilities_prompt({"web_search": True, "deep_research": True}) or ""
    research_only = call_tools.abilities_prompt({"web_search": False, "deep_research": True}) or ""

    assert "[[look up:" in both and "[[research:" in both
    assert "[[research:" in research_only and "[[look up:" not in research_only
    assert call_tools.abilities_prompt({"web_search": False, "deep_research": False}) is None


# --- A spoken turn --------------------------------------------------------------------------


def _store() -> SimpleNamespace:
    rendered = SimpleNamespace(messages=[
        SimpleNamespace(role="system", content="You are the assistant.", per_turn=False),
        SimpleNamespace(role="user", content="Can you research e-bikes for me?", per_turn=False),
    ])
    return SimpleNamespace(
        build_provider_prompt=lambda session, user_message, context_items: (SimpleNamespace(diagnostics={}), rendered),
        _active_memory_metadata=lambda assembly, current_rendered: {},
        _active_history_metadata=lambda assembly: {},
    )


class _Provider:
    provider_name = "claude_cli"

    def __init__(self, *replies: list[str]) -> None:
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    def chat_completion(self, **kwargs: Any):
        self.calls.append(kwargs)
        parts = self.replies.pop(0)
        return iter([ChatResponse(content=part, model="haiku") for part in parts]
                    + [ChatResponse(content="", model="haiku", finish_reason="stop")])


def _turn(monkeypatch, provider: _Provider, *, granted: bool, available: bool = True) -> list[dict[str, Any]]:
    monkeypatch.setattr(call_tools, "deep_research_available", lambda _identity: available)
    monkeypatch.setattr(call_tools, "granted_abilities",
                        lambda _session: {"web_search": True, "deep_research": granted})
    monkeypatch.setattr(call_tools, "run_web_search", lambda *a, **k: (_ for _ in ()).throw(AssertionError("searched")))
    return list(stream_low_latency_reply(
        _store(), SimpleNamespace(id="chat:system", interaction_mode="system", character_id=None),
        SimpleNamespace(id="msg:user", content="Can you research e-bikes for me?", metadata={"speech_segment_id": "s-1"}),
        provider_id="llm:claude_cli", model_id=None, context_items=[], provider=provider,
    ))


def _spoken(events: list[dict[str, Any]]) -> str:
    return "".join(event["text"] for event in events if event["type"] == "text_chunk")


def test_a_granted_research_request_says_its_line_and_ends_the_turn_without_running_anything(monkeypatch) -> None:
    provider = _Provider(["[[research: e-bikes under $2000 || Sure, I'll dig", " into that.]]"])

    events = _turn(monkeypatch, provider, granted=True)

    assert _spoken(events) == "Sure, I'll dig into that."
    assert len(provider.calls) == 1  # no second model call, no search: the task starts after the commit
    assert events[-1]["metadata"]["call_tasks"] == [{
        "index": 0, "ability": "deep_research", "query": "e-bikes under $2000", "allowed": True, "reason": "granted",
        "owner": "system-assistant"}]
    assert "call_lookups" not in events[-1]["metadata"]


def test_words_before_a_research_request_are_its_spoken_line(monkeypatch) -> None:
    provider = _Provider(["On it. [[research: e-bikes || ignored]]"])

    events = _turn(monkeypatch, provider, granted=True)

    assert _spoken(events) == "On it. "
    assert len(provider.calls) == 1 and events[-1]["metadata"]["call_tasks"][0]["allowed"] is True


def test_a_research_request_with_nothing_to_say_lets_the_model_say_it_started(monkeypatch) -> None:
    provider = _Provider(["[[research: e-bikes]]"], ["I'm on it."])

    events = _turn(monkeypatch, provider, granted=True)

    assert _spoken(events) == "I'm on it."
    note = provider.calls[1]["messages"][-1]
    assert note.per_turn and "has started and runs in the background" in note.content


def test_research_without_the_grant_starts_nothing_and_the_model_answers_instead(monkeypatch) -> None:
    provider = _Provider(["[[research: e-bikes || Sure.]]"], ["I can't dig into that right now."])
    monkeypatch.setattr("app.platform.live_voice.llm.stream._ability_gate", lambda _session: RequestGate())

    events = _turn(monkeypatch, provider, granted=False)

    assert _spoken(events) == "I can't dig into that right now."
    assert events[-1]["metadata"]["call_tasks"] == [{
        "index": 0, "ability": "deep_research", "query": "e-bikes", "allowed": False, "reason": "not_granted",
        "owner": "system-assistant"}]
    assert "cannot start research right now" in provider.calls[1]["messages"][-1].content


# --- Starting a committed request --------------------------------------------------------------


_STARTED_JOB = SimpleNamespace(id="job:research")


class _Research:
    """Both ports the start reads: research, and the grants (``CHAT_CALL_ACTIONS``) it checks first."""

    def __init__(self, *, result: Any = _STARTED_JOB, error: Exception | None = None, granted: bool = True) -> None:
        self.calls: list[dict[str, Any]] = []
        self.result, self.error, self.allowed = result, error, granted
        self.checked: list[tuple[str, str]] = []

    def call_owner(self, session: Any) -> str:
        return "system-assistant"

    def granted(self, owner_id: str, *, ability: str = "", capability: str = "") -> bool:
        self.checked.append((owner_id, ability))
        return self.allowed

    def begin_call_research(self, session: Any, question: str, **kwargs: Any) -> Any:
        self.calls.append({"question": question, **kwargs})
        if self.error is not None:
            raise self.error
        return self.result


def _bind(monkeypatch, research: Any) -> None:
    monkeypatch.setattr("app.runtime.ports.optional", lambda _port: research)


def test_only_granted_research_starts_once_per_task_id(monkeypatch) -> None:
    research = _Research()
    _bind(monkeypatch, research)
    tasks = [
        {"index": 0, "ability": "deep_research", "query": "e-bikes", "allowed": True},
        {"index": 1, "ability": "deep_research", "query": "scooters", "allowed": False},
        {"index": 2, "ability": "unlock_door", "query": "front", "allowed": True},
    ]

    recorded = live_call_tasks.start_call_tasks("jobs", SimpleNamespace(id="chat:1"), "msg:user", tasks)

    assert [task.get("start") for task in recorded] == ["started", None, "refused"]
    assert recorded[0]["job_id"] == "job:research"
    assert research.calls == [{"question": "e-bikes", "task_id": "call-task:msg:user:0",
                               "user_message_id": "msg:user", "job_store": "jobs"}]

    again = live_call_tasks.start_call_tasks("jobs", SimpleNamespace(id="chat:1"), "msg:user", recorded)
    assert again == recorded and len(research.calls) == 1  # a recorded start is never repeated


def test_a_task_that_cannot_start_never_breaks_the_committed_reply(monkeypatch) -> None:
    task = [{"index": 0, "ability": "deep_research", "query": "e-bikes", "allowed": True}]
    outcomes = []
    for research in (None, _Research(result=None), _Research(error=RuntimeError("down"))):
        _bind(monkeypatch, research)
        outcomes += [t["start"] for t in live_call_tasks.start_call_tasks("jobs", SimpleNamespace(id="chat:1"),
                                                                           "msg:user", task)]
    assert outcomes == ["refused", "refused", "failed"]

    # A grant revoked between the reply and the start: the speaker who asked no longer holds it.
    revoked = _Research(granted=False)
    _bind(monkeypatch, revoked)
    asked_by_guest = [{**task[0], "owner": "bea"}]
    recorded = live_call_tasks.start_call_tasks("jobs", SimpleNamespace(id="chat:1"), "msg:user", asked_by_guest)
    assert (recorded[0]["start"], recorded[0]["reason"]) == ("refused", "not_granted")
    assert revoked.calls == [] and revoked.checked == [("bea", "deep_research")]
    assert live_call_tasks.start_call_tasks("jobs", SimpleNamespace(id="chat:1"), "msg:user", "junk") == []


def test_the_start_outcome_is_written_back_on_the_asking_reply(monkeypatch) -> None:
    _bind(monkeypatch, _Research())
    tasks = [{"index": 0, "ability": "deep_research", "query": "e-bikes", "allowed": True}]
    reply = SimpleNamespace(id="msg:reply", role="assistant", metadata={"reply_to_message_id": "msg:user",
                                                                        "call_tasks": tasks})
    session = SimpleNamespace(id="chat:1", messages=[reply])
    patches: list[dict[str, Any]] = []
    chat_store = SimpleNamespace(update_message_metadata=lambda **kwargs: patches.append(kwargs))

    live_call_tasks.start_and_record_call_tasks(chat_store, "jobs", session, "msg:user", tasks)

    assert patches == [{"session_id": "chat:1", "message_id": "msg:reply", "metadata": {"call_tasks": [
        {**tasks[0], "start": "started", "job_id": "job:research"}]}}]

    failing = SimpleNamespace(update_message_metadata=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("db")))
    recorded = live_call_tasks.start_and_record_call_tasks(failing, "jobs", session, "msg:user", tasks)
    assert recorded[0]["start"] == "started"  # a lost record never raises into the committed turn


def test_the_commit_starts_what_the_reply_recorded_and_only_then(monkeypatch) -> None:
    from contextlib import nullcontext

    from app.platform.chat import generation_jobs

    started: list[tuple[str, Any]] = []
    monkeypatch.setattr(live_call_tasks, "start_and_record_call_tasks",
                        lambda chat_store, job_store, session, message_id, tasks: started.append((message_id, tasks)))
    monkeypatch.setattr(generation_jobs, "chat_job_commit_lock", lambda _job_id: nullcontext())
    monkeypatch.setattr(generation_jobs, "_cancel_requested", lambda _store, _job_id: False)
    committed: list[dict[str, Any]] = []
    chat_store = SimpleNamespace(complete_streamed_reply=lambda *a: committed.append(a[3]) or SimpleNamespace(id="chat:1"))
    job_store = SimpleNamespace(complete_job=lambda *a: "done")
    job = SimpleNamespace(id="job:1")
    tasks = [{"index": 0, "ability": "deep_research", "query": "e-bikes", "allowed": True}]

    generation_jobs._commit_chat_reply(chat_store, job_store, job, session_id="chat:1", message_id="msg:user",
                                       content="Sure.", metadata={"call_tasks": tasks})
    generation_jobs._commit_chat_reply(chat_store, job_store, job, session_id="chat:1", message_id="msg:other",
                                       content="Hi.", metadata={})
    assert started == [("msg:user", tasks)]
    # Every reply names its turn: the durable store does not add the link itself.
    assert [meta["reply_to_message_id"] for meta in committed] == ["msg:user", "msg:other"]

    monkeypatch.setattr(generation_jobs, "_cancel_requested", lambda _store, _job_id: True)
    monkeypatch.setattr(generation_jobs, "_cancel_chat_turn", lambda *a: None)
    generation_jobs._commit_chat_reply(chat_store, job_store, job, session_id="chat:1", message_id="msg:late",
                                       content="Sure.", metadata={"call_tasks": tasks})
    assert started == [("msg:user", tasks)]  # a cancelled turn starts nothing


# --- The research result -----------------------------------------------------------------------


def test_a_calls_research_is_appended_as_its_own_message_and_a_typed_one_completes_its_turn() -> None:
    from app.platform.research.jobs import DeepResearchJobInput, _save_result

    calls: list[tuple[str, tuple[Any, ...]]] = []
    chat_store = SimpleNamespace(
        complete_streamed_reply=lambda *a: calls.append(("reply", a)) or "session",
        append_assistant_message=lambda *a: calls.append(("append", a)) or ("session", "message", False),
    )
    typed = DeepResearchJobInput(session_id="chat:1", user_message_id="msg:user", question="e-bikes")
    called = typed.model_copy(update={"call_task_id": "call-task:msg:user:0"})

    assert _save_result(chat_store, typed, "Report.", {"research_job_id": "job:1"}) == "session"
    assert _save_result(chat_store, called, "Report.", {"research_job_id": "job:1"}) == "session"

    assert calls[0] == ("reply", ("chat:1", "msg:user", "Report.", {"research_job_id": "job:1"}))
    assert calls[1] == ("append", ("chat:1", "Report.", {
        "research_job_id": "job:1", "turn_id": "call-task:msg:user:0", "call_task_id": "call-task:msg:user:0",
        "call_task_asked_in": "msg:user"}))


def test_call_research_runs_without_a_plan_to_approve_and_once_per_task(monkeypatch) -> None:
    from app.platform.research import api
    from app.platform.research.release_policy import ResearchReleasePolicy
    from app.platform.research.policy import ResearchPolicy
    from app.platform.research.settings import ResearchRuntimeSettings

    class _Adapter(api.ChatResearchAdapter):
        def __init__(self, release: ResearchReleasePolicy) -> None:
            self.release = release

        def resolve_turn(self, request: Any, session_id: str, **_kwargs: Any):
            return super().resolve_turn(request, session_id, settings=ResearchRuntimeSettings(
                policy=ResearchPolicy(), deep_enabled=True),
                                        release_policy=self.release)

    created: list[tuple[Any, str]] = []

    def create_job_once(request: Any, *, idempotency_key: str) -> Any:
        created.append((request, idempotency_key))
        return SimpleNamespace(id="job:research", input_payload=request.input_payload)

    monkeypatch.setattr(api, "_start_research_execution", lambda _store, job: job)
    monkeypatch.setattr(ResearchRuntimeSettings, "provider_available", property(lambda _self: True))
    jobs = SimpleNamespace(create_job_once=create_job_once)
    session = SimpleNamespace(id="chat:1", provider_id="llm:claude_cli", model_id="haiku")

    job = _Adapter(ResearchReleasePolicy()).begin_call_research(
        session, "e-bikes under $2000", task_id="call-task:msg:user:0", user_message_id="msg:user", job_store=jobs)

    assert job is not None and created[0][1] == "call-task:msg:user:0"
    payload = created[0][0].input_payload
    assert payload["question"] == "e-bikes under $2000" and payload["user_message_id"] == "msg:user"
    assert payload["awaiting_plan_approval"] is False and payload["call_task_id"] == "call-task:msg:user:0"
    assert payload["provider_id"] == "llm:claude_cli" and payload["research_plan"] is not None

    blocked = _Adapter(ResearchReleasePolicy(deep_local_enabled=False)).begin_call_research(
        session, "e-bikes", task_id="call-task:msg:user:1", user_message_id="msg:user", job_store=jobs)
    assert blocked is None and len(created) == 1  # the release policy still decides whether deep research runs


def test_research_is_offered_only_when_it_can_start(monkeypatch) -> None:
    from app.platform.live_voice.llm import call_tools

    available = {"value": False}
    asked: list[str] = []

    class _Research:
        def resolve_turn(self, request: Any, session_id: str, **_kwargs: Any):
            asked.append(session_id)
            return SimpleNamespace(effective_mode="deep" if available["value"] else "off")

    monkeypatch.setattr(call_tools, "_research_availability", {})
    monkeypatch.setattr("app.runtime.ports.optional", lambda _port: _Research())
    monkeypatch.setattr(call_tools, "granted_abilities", lambda _s: {"web_search": True, "deep_research": True})
    session = SimpleNamespace(id="chat:avail")

    assert call_tools.offered_abilities(session) == {"web_search": True, "deep_research": False}
    assert "research" not in (call_tools.abilities_prompt(call_tools.offered_abilities(session)) or "")
    assert asked == ["chat:avail"]  # read once, then kept

    monkeypatch.setattr(call_tools, "_research_availability", {})
    available["value"] = True
    assert call_tools.offered_abilities(session)["deep_research"] is True


def test_granted_research_that_cannot_start_is_recorded_unavailable(monkeypatch) -> None:
    provider = _Provider(["[[research: e-bikes || Sure.]]"], ["I can't dig into that right now."])
    monkeypatch.setattr("app.platform.live_voice.llm.stream._ability_gate", lambda _session: RequestGate())

    events = _turn(monkeypatch, provider, granted=True, available=False)

    assert _spoken(events) == "I can't dig into that right now."  # no promise of research that never starts
    assert events[-1]["metadata"]["call_tasks"][0]["allowed"] is False
    assert events[-1]["metadata"]["call_tasks"][0]["reason"] == "unavailable"
    assert "cannot start research right now" in provider.calls[1]["messages"][-1].content


# --- The call's task list (companion 1.2) ------------------------------------------------------


def _message(message_id: str, role: str, created_at: str, **metadata: Any) -> SimpleNamespace:
    return SimpleNamespace(id=message_id, role=role, created_at=created_at, metadata=metadata)


class _Jobs:
    def __init__(self, **statuses: str) -> None:
        self.statuses = statuses
        self.cancelled: list[str] = []

    def get_job(self, job_id: str) -> Any:
        status = self.statuses.get(job_id)
        if status is None:
            return None
        return SimpleNamespace(status=status, completed_at="2026-11-15T10:05:00+00:00" if status == "completed" else None,
                               updated_at="2026-11-15T10:04:00+00:00")

    def cancel_job(self, job_id: str, request: Any) -> Any:
        self.cancelled.append(job_id)
        self.statuses[job_id] = "canceled"


def _at(value: str) -> Any:
    from datetime import datetime

    return datetime.fromisoformat(value)


def _task(index: int, **fields: Any) -> dict[str, Any]:
    return {"index": index, "ability": "deep_research", "query": f"q{index}", "allowed": True, **fields}


def _states(session: Any, jobs: Any, now: str = "2026-11-15T10:10:00+00:00") -> dict[str, tuple[str, bool]]:
    from datetime import datetime

    listed = live_call_tasks.list_call_tasks(session, jobs, now=datetime.fromisoformat(now))
    return {task.task_id.rsplit(":", 1)[1]: (task.state, task.reported) for task in listed.tasks}


def test_a_tasks_state_is_its_jobs_state() -> None:
    tasks = [
        _task(0, start="started", job_id="job:open"),
        _task(1, start="started", job_id="job:done"),
        _task(2, start="started", job_id="job:failed"),
        _task(3, start="started", job_id="job:stale"),
        _task(4, start="started", job_id="job:cancelled"),
        _task(5, start="started", job_id="job:gone"),
        _task(6, start="refused"),
        _task(7, start="failed"),
        {**_task(8), "allowed": False},
        _task(9),  # no start recorded, long after the reply: the process stopped before it
    ]
    session = SimpleNamespace(messages=[
        _message("msg:user", "user", "2026-11-15T10:00:00+00:00"),
        _message("msg:reply", "assistant", "2026-11-15T10:00:01+00:00", reply_to_message_id="msg:user",
                 call_tasks=tasks),
    ])
    jobs = _Jobs(**{"job:open": "running", "job:done": "completed", "job:failed": "failed", "job:stale": "stale",
                    "job:cancelled": "canceled"})

    assert _states(session, jobs) == {
        "0": ("open", False), "1": ("completed", False), "2": ("failed", False), "3": ("failed", False),
        "4": ("cancelled", True), "5": ("failed", False), "6": ("not_started", False), "7": ("not_started", False),
        "8": ("not_started", False), "9": ("not_started", False),
    }


def test_a_start_still_on_its_way_reads_open_and_old_tasks_are_left_out() -> None:
    session = SimpleNamespace(messages=[
        _message("msg:old-reply", "assistant", "2026-11-15T09:00:00+00:00", reply_to_message_id="msg:old",
                 call_tasks=[_task(0, start="started", job_id="job:x")]),
        _message("msg:reply", "assistant", "2026-11-15T10:09:30+00:00", reply_to_message_id="msg:user",
                 call_tasks=[_task(0)]),
    ])

    listed = live_call_tasks.list_call_tasks(session, _Jobs(), now=_at(
        "2026-11-15T10:10:00+00:00"))

    assert [(task.task_id, task.state) for task in listed.tasks] == [("call-task:msg:user:0", "open")]


def test_a_saved_result_completes_the_task_and_a_report_marks_it_reported() -> None:
    task_id = "call-task:msg:user:0"
    session = SimpleNamespace(messages=[
        _message("msg:reply", "assistant", "2026-11-15T10:00:01+00:00", reply_to_message_id="msg:user",
                 call_tasks=[_task(0, start="started", job_id="job:run")]),
        _message("msg:result", "assistant", "2026-11-15T10:06:00+00:00", call_task_id=task_id),
    ])
    jobs = _Jobs(**{"job:run": "running"})

    from datetime import datetime

    listed = live_call_tasks.list_call_tasks(session, jobs, now=datetime.fromisoformat("2026-11-15T10:10:00+00:00"))
    assert listed.tasks[0].state == "completed" and listed.tasks[0].result_message_id == "msg:result"
    assert listed.tasks[0].settled_at == "2026-11-15T10:06:00+00:00" and not listed.tasks[0].reported

    session.messages.append(_message("msg:report", "assistant", "2026-11-15T10:07:00+00:00",
                                     task_report_for=task_id))
    assert _states(session, jobs)["0"] == ("completed", True)


def test_cancel_stops_only_this_chats_task() -> None:
    from datetime import datetime

    now = datetime.fromisoformat("2026-11-15T10:10:00+00:00")
    session = SimpleNamespace(messages=[
        _message("msg:reply", "assistant", "2026-11-15T10:00:01+00:00", reply_to_message_id="msg:user",
                 call_tasks=[_task(0, start="started", job_id="job:run"), _task(1, start="refused")]),
    ])
    jobs = _Jobs(**{"job:run": "running"})

    assert live_call_tasks.cancel_call_task(session, jobs, "call-task:msg:other:0", now=now) is None
    assert jobs.cancelled == []

    cancelled = live_call_tasks.cancel_call_task(session, jobs, "call-task:msg:user:0", now=now)
    assert cancelled is not None and cancelled.state == "cancelled" and cancelled.reported
    assert jobs.cancelled == ["job:run"]

    not_started = live_call_tasks.cancel_call_task(session, jobs, "call-task:msg:user:1", now=now)
    assert not_started is not None and not_started.state == "not_started" and jobs.cancelled == ["job:run"]


def test_the_task_routes_find_a_task_only_through_its_own_chat() -> None:
    from datetime import datetime, timezone

    from fastapi import APIRouter, FastAPI
    from fastapi.testclient import TestClient

    from app.platform.chat.live_call_task_routes import register_live_call_task_routes

    asked = datetime.now(timezone.utc).isoformat()
    session = SimpleNamespace(id="chat:1", messages=[
        _message("msg:reply", "assistant", asked, reply_to_message_id="msg:user",
                 call_tasks=[_task(0, start="started", job_id="job:run")]),
    ])
    jobs = _Jobs(**{"job:run": "running"})
    chats = SimpleNamespace(get_session=lambda session_id: session if session_id == "chat:1" else None)
    router = APIRouter()
    register_live_call_task_routes(router, chat_store_factory=lambda: chats, job_store_factory=lambda: jobs)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    listed = client.get("/api/chat/sessions/chat:1/live-call/tasks").json()
    assert [(task["task_id"], task["state"]) for task in listed["tasks"]] == [("call-task:msg:user:0", "open")]
    assert client.get("/api/chat/sessions/chat:2/live-call/tasks").status_code == 404
    assert client.post("/api/chat/sessions/chat:2/live-call/tasks/call-task:msg:user:0/cancel").status_code == 404
    assert client.post("/api/chat/sessions/chat:1/live-call/tasks/call-task:msg:x:0/cancel").status_code == 404
    assert jobs.cancelled == []

    cancelled = client.post("/api/chat/sessions/chat:1/live-call/tasks/call-task:msg:user:0/cancel")
    assert cancelled.status_code == 200 and cancelled.json()["state"] == "cancelled"
    assert jobs.cancelled == ["job:run"]
