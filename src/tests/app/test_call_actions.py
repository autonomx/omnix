"""A call's actions: reads run, writes only propose, and a proposal is decided once, by its answer (roadmap 1.5)."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from app.platform.assistant_tools.voice_actions import check_voice_action
from app.platform.chat import live_agent_store, live_call_tasks
from app.platform.chat.live_call_actions import JOB_TYPE, LIVE_CALL_ORIGIN, LiveCallActionInput, execute_call_action

TASK = "call-task:msg:asked:0"
GRANTS = {"smart_home": True, "calendar": True}
SYSTEM = "system-assistant"
_STAMP = datetime.fromisoformat("2026-11-15T10:00:00+00:00")


# Validation -----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("capability", "data", "grants"), [
    ("home.explode", {}, GRANTS),  # unknown
    ("calendar.delete_event", {"event_id": "e1"}, GRANTS),  # not offered by voice
    ("home.apply_scene", {"scene": "night"}, GRANTS),  # not offered by voice
    ("home.set_state", {"target": "lamp", "on": "yes"}, GRANTS),  # not a boolean
    ("home.set_state", {"target": "lamp", "on": True, "brightness": 4}, GRANTS),  # extra field
    ("calendar.read_availability", {"start_time": "2026-11-15T10:00:00", "end_time": "2026-11-15T09:00:00",
                                    "timezone": "Europe/London"}, GRANTS),  # ends before it starts
    ("calendar.read_availability", {"start_time": "2026-11-15T10:00:00", "end_time": "2026-11-15T11:00:00",
                                    "timezone": "Mars/Olympus"}, GRANTS),  # no such zone
])
def test_an_action_the_call_cannot_offer_or_with_a_bad_input_is_invalid(capability, data, grants) -> None:
    check = check_voice_action(capability, data, grants)
    assert not check.ok and check.reason == "invalid"


def test_an_action_needs_its_group_granted_and_its_input_is_cleaned() -> None:
    assert check_voice_action("home.set_state", {"target": "lamp", "on": True}, {"calendar": True}).reason == (
        "not_granted")
    check = check_voice_action("home.set_state", {"target": "  Desk lamp ", "on": False}, GRANTS)
    assert check.ok and check.effect == "write" and check.input == {"target": "Desk lamp", "on": False}
    assert check_voice_action("home.list_devices", {}, GRANTS).effect == "read"


# The job --------------------------------------------------------------------------------------------------------


@pytest.fixture
def stores(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.composition.gateway.main import create_gateway_app
    from app.persistence.runtime import reset_persistence_mode_cache
    from app.platform.chat.character_store import InMemoryChatSessionStore
    from app.platform.chat.live_chat_speculation import clear_live_speculation_cache
    from tests.support.in_memory_jobs import InMemoryJobStore

    monkeypatch.setenv("OMNIX_PERSISTENCE_MODE", "legacy_test")
    monkeypatch.setenv("OMNIX_ALLOW_LEGACY_TEST_PERSISTENCE", "1")
    monkeypatch.setenv("OMNIX_CHARACTER_DB_PATH", str(tmp_path / "characters.sqlite3"))
    monkeypatch.setenv("OMNIX_CHAT_STORE_PATH", str(tmp_path / "chat.json"))
    monkeypatch.setenv("OMNIX_LIVE_CONVERSATION_PROFILE_PATH", str(tmp_path / "profiles.json"))
    reset_persistence_mode_cache()
    clear_live_speculation_cache()
    # Each speaker's grants, read again when a task starts and when its proposal is confirmed.
    grants: dict[str, dict[str, bool]] = {SYSTEM: dict(GRANTS)}
    monkeypatch.setattr("app.platform.assistant_tools.owner_grants.owner_grants",
                        lambda owner_id: dict(grants.get(owner_id, {})))
    chat_store = InMemoryChatSessionStore()
    job_store = InMemoryJobStore(tmp_path / "jobs")  # its own state: task ids repeat across tests
    client = TestClient(
        create_gateway_app(chat_store_factory=lambda: chat_store, job_store_factory=lambda: job_store),
        base_url="http://localhost", headers={"X-Omnix-Client": "web"},
    )
    session_id = client.post("/api/chat/sessions", json={"title": "Call"}).json()["id"]
    yield SimpleNamespace(chat=chat_store, jobs=job_store, client=client, session_id=session_id, grants=grants)
    clear_live_speculation_cache()


class _Calls:
    """Stands in for ``execute_capability``: records each call and answers from ``answers`` by action id."""

    def __init__(self, **answers: Any) -> None:
        self.answers = answers
        self.calls: list[tuple[Any, Any]] = []
        self.lock = threading.Lock()

    def __call__(self, grant: Any, request: Any, *, user_request: str = "") -> Any:
        with self.lock:
            self.calls.append((grant, request))
        answer = self.answers.get(request.action_id) or {"summary": "Done.", "output": {}}
        return _Payload(answer.get("summary", ""), answer.get("output") or {}, answer.get("error"))

    @property
    def actions(self) -> list[str]:
        return [request.action_id for _grant, request in self.calls]


class _Payload:
    def __init__(self, summary: str, output: dict[str, Any], error: str | None = None) -> None:
        self.execution_result = SimpleNamespace(result_summary=summary, output=output, error=error)

    def model_dump(self, mode: str = "python") -> dict[str, Any]:
        result = self.execution_result
        return {"execution_result": {"result_summary": result.result_summary, "error": result.error}}


def _devices(*names: str) -> dict[str, Any]:
    return {"summary": f"{len(names)} devices", "output": {"devices": [
        {"id": f"dev-{index}", "name": name, "on": index == 0} for index, name in enumerate(names)]}}


def _run_job(stores: Any, capability: str, data: dict[str, Any], effect: str) -> Any:
    from app.jobs.models import CreateJobRequest, ResourceClass

    payload = LiveCallActionInput(session_id=stores.session_id, task_id=TASK, user_message_id="msg:asked",
                                  capability=capability, input=data, effect=effect, owner=SYSTEM)
    job = stores.jobs.create_job_once(CreateJobRequest(
        owner_id=stores.session_id, module="chat", type=JOB_TYPE, resource_class=ResourceClass.NETWORK,
        input_payload=payload.model_dump(mode="json")), idempotency_key=TASK)
    return execute_call_action(stores.jobs, job, chat_store=stores.chat)


def _result_message(stores: Any) -> Any:
    session = stores.chat.get_session(stores.session_id)
    return next(message for message in session.messages if message.metadata.get("call_task_id") == TASK)


def _audits(monkeypatch) -> list[str]:
    actions: list[str] = []
    monkeypatch.setattr("app.security.audit.record", lambda action, **_kwargs: actions.append(action))
    return actions


def _automatic_home(monkeypatch) -> Any:
    """Per-action settings that would let every home action run on its own."""
    from app.platform.assistant_tools.config_store import (
        AssistantActionConfigRecord, AssistantToolConfigRecord, AssistantToolsConfigPayload,
    )

    config = AssistantToolsConfigPayload(tools=[AssistantToolConfigRecord(
        tool_id="home", enabled=True, connection_status="connected", approval_policy="allow_automatic",
        actions=[AssistantActionConfigRecord(action_id=action, enabled=True, approval_policy="allow_automatic")
                 for action in ("home.list_devices", "home.get_state", "home.set_state")])])
    monkeypatch.setattr("app.platform.assistant_tools.gate.load_assistant_tools_config", lambda *a, **k: config)
    return config


def test_a_read_runs_under_the_chats_unapproved_grant_and_records_no_approval(stores, monkeypatch) -> None:
    calls = _Calls(**{"home.list_devices": _devices("Desk lamp", "Fan")})
    monkeypatch.setattr("app.capabilities.executor.execute_capability", calls)
    audits = _audits(monkeypatch)

    job = _run_job(stores, "home.list_devices", {}, "read")

    assert job.status.value == "completed"
    grant, request = calls.calls[0]
    assert (grant.source, grant.subject_id, grant.approved_by, grant.policy_floor) == (
        "chat", stores.session_id, None, None)
    assert request.action_id == "home.list_devices" and request.proposal_id is None
    message = _result_message(stores)
    assert message.content == "2 home devices: Desk lamp (on), Fan (off)."
    assert "pending_governed_tool_request" not in message.metadata
    assert "approval.decide" not in audits


def test_a_write_only_proposes_even_when_its_settings_say_automatic(stores, monkeypatch) -> None:
    from app.platform.assistant_tools.contracts import AssistantToolRequest, review_assistant_tool_request

    config = _automatic_home(monkeypatch)
    calls = _Calls(**{"home.list_devices": _devices("Desk lamp", "Fan")})
    monkeypatch.setattr("app.capabilities.executor.execute_capability", calls)
    audits = _audits(monkeypatch)

    job = _run_job(stores, "home.set_state", {"target": "desk lamp", "on": False}, "write")

    assert job.status.value == "completed"
    assert calls.actions == ["home.list_devices"]  # the device was looked up; nothing was switched
    message = _result_message(stores)
    assert message.content == "Turn off Desk lamp? Say confirm or cancel."
    assert message.metadata["governed_tool_execution_status"] == "pending"
    assert message.metadata["governed_proposal_origin"] == LIVE_CALL_ORIGIN
    assert message.metadata["pending_governed_tool_request"]["input"] == {"target": "dev-0", "on": False}
    assert message.metadata["live_call_action"]["owner"] == SYSTEM  # its confirm re-checks this speaker's grant
    assert "approval.decide" not in audits

    # The floor is what holds it: the same settings alone would let it run.
    request = AssistantToolRequest(tool_id="home", action_id="home.set_state", session_id=stores.session_id,
                                   input={"target": "dev-0", "on": False})
    assert review_assistant_tool_request(request, config=config).executable
    held = review_assistant_tool_request(request, config=config, policy_floor="always_ask")
    assert held.allowed and held.approval_required and not held.executable


@pytest.mark.parametrize(("names", "target", "outcome"), [
    (("Desk lamp", "Fan"), "heater", "I couldn't find heater."),
    (("Desk lamp", "Floor lamp"), "lamp", "More than one device matches lamp."),
    (("Desk lamp", "Floor lamp"), "floor-lamp", "dev-1"),
    (("Lamp", "Desk lamp"), "lamp", "dev-0"),  # an equal name beats a longer one containing it
])
def test_a_spoken_device_resolves_to_exactly_one(stores, monkeypatch, names, target, outcome) -> None:
    _automatic_home(monkeypatch)
    calls = _Calls(**{"home.list_devices": _devices(*names)})
    monkeypatch.setattr("app.capabilities.executor.execute_capability", calls)

    job = _run_job(stores, "home.set_state", {"target": target, "on": True}, "write")

    if outcome.startswith("dev-"):
        assert job.status.value == "completed"
        assert _result_message(stores).metadata["pending_governed_tool_request"]["input"]["target"] == outcome
    else:
        assert job.status.value == "failed" and job.error.message == outcome
    assert calls.actions == ["home.list_devices"]


# When a proposal may be answered --------------------------------------------------------------------------------


def _message(message_id: str, role: str, at: datetime, content: str = "", **metadata: Any) -> SimpleNamespace:
    return SimpleNamespace(id=message_id, role=role, content=content, created_at=at.isoformat(), metadata=metadata)


def _tool_request(session_id: str = "chat:1") -> dict[str, Any]:
    from app.platform.assistant_tools.contracts import AssistantToolRequest

    return AssistantToolRequest(tool_id="home", action_id="home.set_state", session_id=session_id,
                                proposal_id=TASK, input={"target": "dev-0", "on": False}).model_dump(mode="json")


def _proposal_metadata(stamp: datetime | None, session_id: str = "chat:1") -> dict[str, Any]:
    metadata = {"pending_governed_tool_request": _tool_request(session_id), "governed_tool_execution_status": "pending",
                "governed_proposal_origin": LIVE_CALL_ORIGIN, "call_task_id": TASK, "turn_id": TASK,
                "live_call_action": {"capability": "home.set_state", "effect": "write", "owner": SYSTEM}}
    if stamp is not None:
        metadata[live_call_tasks.REPORT_STARTED_AT] = stamp.isoformat()
    return metadata


def _proposal(stamp: datetime | None = _STAMP) -> SimpleNamespace:
    return _message("msg:proposal", "assistant", _STAMP - timedelta(seconds=10), "Turn off Desk lamp?",
                    **_proposal_metadata(stamp))


def _confirmable(*users: SimpleNamespace, proposal: SimpleNamespace | None = None) -> bool:
    proposal = proposal or _proposal()
    session = SimpleNamespace(messages=[proposal, *users])
    return live_call_tasks.proposal_confirmable(session, proposal, users[-1])


def _after(seconds: float) -> datetime:
    return _STAMP + timedelta(seconds=seconds)


HEARD = {"heard_turn_id": live_call_tasks.task_report_turn_id(TASK)}


def test_a_typed_answer_counts_only_as_the_first_turn_after_the_question_within_the_window() -> None:
    assert _confirmable(_message("u1", "user", _after(5), "confirm"))
    assert not _confirmable(_message("u1", "user", _after(-2), "confirm"))  # before the question began
    assert not _confirmable(_message("u1", "user", _after(121), "confirm"))  # the window has passed
    assert not _confirmable(_message("u1", "user", _after(5), "confirm"), proposal=_proposal(stamp=None))
    # Another turn came first, such as something typed in the composer: the proposal has expired.
    assert not _confirmable(_message("u1", "user", _after(5), "what's the weather"),
                            _message("u2", "user", _after(20), "confirm", user_turn_id="voice-user-turn:2", **HEARD))


def test_a_spoken_answer_must_have_begun_after_the_question_did() -> None:
    voice = {"user_turn_id": "voice-user-turn:1"}
    assert not _confirmable(_message("u1", "user", _after(5), "confirm", **voice))  # nothing says it was heard
    assert not _confirmable(_message("u1", "user", _after(5), "confirm", **voice,
                                     heard_turn_id="task-report:call-task:msg:other:0"))
    assert _confirmable(_message("u1", "user", _after(5), "confirm", **voice, **HEARD))
    assert not _confirmable(_message("u1", "user", _after(5), "confirm", speech_segment_id="seg-1"))
    assert _confirmable(_message("u1", "user", _after(5), "confirm", speech_segment_id="seg-1", **HEARD))


def test_an_expired_call_proposal_hides_older_ones() -> None:
    older = _message("msg:older", "assistant", _STAMP - timedelta(minutes=5), "Turn off the fan?",
                     pending_governed_tool_request=_tool_request(), governed_tool_execution_status="pending")
    answer = _message("u1", "user", _after(200), "confirm")
    with_call = SimpleNamespace(messages=[older, _proposal(), answer])
    assert live_agent_store._pending_governed_proposal(with_call, answer) is None
    # Without the call's proposal, the older one is what a confirm answers, as before.
    alone = SimpleNamespace(messages=[older, answer])
    found = live_agent_store._pending_governed_proposal(alone, answer)
    assert found is not None and found[0].id == "msg:older"


def test_the_buttons_act_only_within_the_window() -> None:
    assert live_call_tasks.proposal_button_allowed(_proposal(), now=_after(60))
    assert not live_call_tasks.proposal_button_allowed(_proposal(), now=_after(121))
    assert not live_call_tasks.proposal_button_allowed(_proposal(), now=_after(-1))
    assert not live_call_tasks.proposal_button_allowed(_proposal(stamp=None), now=_after(1))


# Stamping and deciding, through a store -------------------------------------------------------------------------


def _store_proposal(stores: Any, stamp: datetime | None) -> Any:
    appended = stores.chat.append_assistant_message(stores.session_id, "Turn off Desk lamp? Say confirm or cancel.",
                                                    _proposal_metadata(stamp, stores.session_id))
    return appended[1]


def _metadata(stores: Any, message_id: str) -> dict[str, Any]:
    session = stores.chat.get_session(stores.session_id)
    return next(message for message in session.messages if message.id == message_id).metadata


def test_a_proposal_report_is_stamped_once_and_again_only_after_a_failed_one(stores) -> None:
    message = _store_proposal(stores, stamp=None)
    report = SimpleNamespace(proposal_message_id=message.id)

    def claim(at: datetime) -> bool:
        session = stores.chat.get_session(stores.session_id)
        return live_call_tasks.claim_proposal_report(stores.chat, session, report, now=at)

    assert claim(_STAMP)
    assert not claim(_after(5))  # a report is still under way
    assert claim(_after(11))  # that one failed; a new report may start
    assert _metadata(stores, message.id)[live_call_tasks.REPORT_STARTED_AT] == _after(11).isoformat()

    stores.chat.update_message_metadata(session_id=stores.session_id, message_id=message.id,
                                        metadata={live_call_tasks.PROPOSAL_REPORTED: True})
    assert not claim(_after(30))  # delivered
    stores.chat.update_message_metadata(session_id=stores.session_id, message_id=message.id,
                                        metadata={live_call_tasks.PROPOSAL_REPORTED: False,
                                                  "governed_tool_execution_status": "executing"})
    assert not claim(_after(60))  # decided


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _spoken_confirm(stores: Any, **request: Any) -> list[dict[str, Any]]:
    from app.platform.chat.models import SendChatMessageRequest

    session, user_message = stores.chat.begin_user_message(
        stores.session_id, SendChatMessageRequest(content="confirm", **request), start_streaming=True)
    return list(live_agent_store.stream_live_agent_turn(
        stores.chat, session, user_message, provider_id=None, model_id=None, planner=object(),
        original_stream=lambda *_args, **_kwargs: iter(())))


def test_a_spoken_confirm_and_the_button_run_it_once(stores, monkeypatch) -> None:
    calls = _Calls(**{"home.set_state": {"summary": "Desk lamp is off."}})
    monkeypatch.setattr(live_agent_store, "execute_capability", calls)
    message = _store_proposal(stores, stamp=_now() - timedelta(seconds=1))

    events = _spoken_confirm(stores, user_turn_id="voice-user-turn:1", heard_turn_id=HEARD["heard_turn_id"])

    assert next(event for event in events if event["type"] == "complete")["content"] == "Desk lamp is off."
    pressed = stores.client.post(f"/api/chat/sessions/{stores.session_id}/live-call/tasks/{TASK}/decision",
                                 json={"decision": "confirm"})
    assert pressed.status_code == 409 and pressed.json()["detail"] == "proposal_decided"
    assert calls.actions == ["home.set_state"]
    assert _metadata(stores, message.id)["governed_tool_execution_status"] == "executed"


def test_a_proposal_whose_speaker_lost_the_grant_is_not_run(stores, monkeypatch) -> None:
    calls = _Calls(**{"home.set_state": {"summary": "Desk lamp is off."}})
    monkeypatch.setattr(live_agent_store, "execute_capability", calls)
    message = _store_proposal(stores, stamp=_now() - timedelta(seconds=1))
    stores.grants[SYSTEM] = {"smart_home": False}  # revoked after the proposal was made

    events = _spoken_confirm(stores, user_turn_id="voice-user-turn:1", heard_turn_id=HEARD["heard_turn_id"])

    said = next(event for event in events if event["type"] == "complete")["content"]
    assert said == "Nothing was changed. That is no longer allowed for whoever proposed it."
    assert calls.actions == []
    assert _metadata(stores, message.id)["governed_tool_execution_status"] == "failed"


def test_a_proposal_with_no_recorded_speaker_is_not_run(stores, monkeypatch) -> None:
    calls = _Calls()
    monkeypatch.setattr(live_agent_store, "execute_capability", calls)
    metadata = _proposal_metadata(_now() - timedelta(seconds=1), stores.session_id)
    metadata["live_call_action"] = {"capability": "home.set_state", "effect": "write"}
    stores.chat.append_assistant_message(stores.session_id, "Turn off Desk lamp? Say confirm or cancel.", metadata)

    pressed = stores.client.post(f"/api/chat/sessions/{stores.session_id}/live-call/tasks/{TASK}/decision",
                                 json={"decision": "confirm"})

    assert pressed.status_code == 200 and pressed.json()["status"] == "failed"
    assert calls.actions == []


def test_a_task_starts_only_while_the_speaker_who_asked_holds_the_grant(stores, monkeypatch) -> None:
    calls = _Calls(**{"home.list_devices": _devices("Desk lamp")})
    monkeypatch.setattr("app.capabilities.executor.execute_capability", calls)
    session = stores.chat.get_session(stores.session_id)
    # A guest asked (their turn records them); the host's grants do not stand in for theirs.
    task = {"index": 0, "ability": "smart_home", "query": "list devices", "allowed": True, "reason": "granted",
            "owner": "bea", "capability": "home.list_devices", "input": {}, "effect": "read"}

    refused = live_call_tasks.start_call_tasks(stores.jobs, session, "msg:asked", [task], chat_store=stores.chat)
    assert refused[0]["start"] == live_call_tasks.REFUSED and refused[0]["reason"] == "not_granted"

    stores.grants["bea"] = {"smart_home": True}
    started = live_call_tasks.start_call_tasks(stores.jobs, session, "msg:asked", [task], chat_store=stores.chat)
    assert started[0]["start"] == live_call_tasks.STARTED
    assert stores.jobs.get_job(started[0]["job_id"]).input_payload["owner"] == "bea"


def test_two_confirms_at_once_run_it_once(stores, monkeypatch) -> None:
    from app.capabilities.executor import live_agent_tools

    calls = _Calls()
    monkeypatch.setattr(live_agent_store, "execute_capability", calls)
    message = _store_proposal(stores, stamp=_now())
    request = live_agent_tools().parse_request(message.metadata["pending_governed_tool_request"])
    barrier = threading.Barrier(4)
    results: list[Any] = []

    def confirm() -> None:
        barrier.wait()
        results.append(live_agent_store.decide_governed_proposal(
            stores.chat, stores.session_id, message, request, choice="approve", user_request="confirm"))

    threads = [threading.Thread(target=confirm) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len([result for result in results if result is not None]) == 1
    assert calls.actions == ["home.set_state"]


def test_the_button_confirms_cancels_and_refuses_what_it_may_not_decide(stores, monkeypatch) -> None:
    calls = _Calls(**{"home.set_state": {"summary": "Desk lamp is off."}})
    monkeypatch.setattr(live_agent_store, "execute_capability", calls)
    base = f"/api/chat/sessions/{stores.session_id}/live-call/tasks"

    def press(task_id: str, decision: str) -> Any:
        return stores.client.post(f"{base}/{task_id}/decision", json={"decision": decision})

    message = _store_proposal(stores, stamp=_now() - timedelta(seconds=121))
    assert press(TASK, "confirm").json()["detail"] == "proposal_expired"
    assert press("call-task:msg:other:0", "confirm").status_code == 404  # not this chat's
    assert press(TASK, "approve").status_code == 422

    stores.chat.update_message_metadata(session_id=stores.session_id, message_id=message.id, metadata={
        live_call_tasks.REPORT_STARTED_AT: _now().isoformat()})
    cancelled = press(TASK, "cancel")
    assert cancelled.status_code == 200
    assert cancelled.json() == {"task_id": TASK, "status": "rejected",
                                "text": "Cancelled. I did not execute home.set_state."}
    assert _metadata(stores, message.id)["governed_tool_execution_status"] == "rejected"
    assert press(TASK, "confirm").json()["detail"] == "proposal_decided"
    assert calls.calls == []


def test_a_proposal_left_executing_is_never_run_again(stores, monkeypatch) -> None:
    from app.capabilities.executor import live_agent_tools

    calls = _Calls()
    monkeypatch.setattr(live_agent_store, "execute_capability", calls)
    message = _store_proposal(stores, stamp=_now())
    # A crash after the claim: the action may have happened, so nothing runs it again.
    stores.chat.update_message_metadata(session_id=stores.session_id, message_id=message.id,
                                        metadata={"governed_tool_execution_status": "executing"})

    pressed = stores.client.post(f"/api/chat/sessions/{stores.session_id}/live-call/tasks/{TASK}/decision",
                                 json={"decision": "confirm"})
    assert pressed.json()["detail"] == "proposal_decided"
    request = live_agent_tools().parse_request(message.metadata["pending_governed_tool_request"])
    assert live_agent_store.decide_governed_proposal(stores.chat, stores.session_id, message, request,
                                                     choice="approve", user_request="confirm") is None
    session = stores.chat.get_session(stores.session_id)
    assert live_agent_store._pending_governed_proposal(session, SimpleNamespace(id="u", role="user")) is None
    assert calls.calls == []


def test_a_confirm_said_over_the_question_stops_it_without_asking_the_model(stores, monkeypatch) -> None:
    from app.platform.chat import live_overlap_judge

    asked: list[str] = []

    async def judge(**kwargs: Any) -> dict[str, Any]:
        asked.append(kwargs["transcript"])
        return {"decision": "continue", "source": "model", "reason": None, "elapsed_ms": 1.0}

    monkeypatch.setattr(live_overlap_judge, "judge_overlap", judge)

    def overlap(transcript: str, **extra: Any) -> dict[str, Any]:
        response = stores.client.post(f"/api/live-call/sessions/{stores.session_id}/overlap-judgement",
                                      json={"transcript": transcript, "assistant_text": "Turn off Desk lamp?", **extra})
        assert response.status_code == 200
        return response.json()

    assert overlap("confirm")["source"] == "model"  # no proposal: the model judges, as before
    message = _store_proposal(stores, stamp=_now())
    assert overlap("yes") == {"decision": "stop", "source": "proposal_answer", "reason": "proposal_answer",
                              "elapsed_ms": 0.0}
    assert overlap("cancel")["source"] == "proposal_answer"
    assert overlap("what's the weather")["source"] == "model"  # not an answer
    # A remark the call would drop is only checked for an answer; the model is not asked about it.
    assert overlap("cancel", proposal_answer_only=True)["source"] == "proposal_answer"
    assert overlap("mm-hm", proposal_answer_only=True) == {"decision": "continue", "source": "fallback",
                                                            "reason": "not_proposal_answer", "elapsed_ms": 0.0}
    stores.chat.update_message_metadata(session_id=stores.session_id, message_id=message.id, metadata={
        live_call_tasks.REPORT_STARTED_AT: (_now() - timedelta(seconds=121)).isoformat()})
    assert overlap("yes")["source"] == "model"  # the question's window has passed
    assert asked == ["confirm", "what's the weather", "yes"]


# Speculation ----------------------------------------------------------------------------------------------------


def test_a_speculated_answer_to_a_pending_proposal_is_refused(stores) -> None:
    from app.platform.chat import live_chat_speculation

    _store_proposal(stores, stamp=_now())
    started = stores.client.post(f"/api/live/speculation/sessions/{stores.session_id}/stream",
                                 json={"content": "confirm", "segment_id": "seg-1", "source_sequence": 0})
    assert started.status_code == 409 and started.json()["detail"] == "speculation_answers_proposal"

    # One speculated before the proposal existed is refused when it would be accepted.
    live_chat_speculation._SPECULATIONS["gen-1"] = live_chat_speculation._Speculation(
        generation_id="gen-1", session_id=stores.session_id, candidate_text="confirm", provider_id=None,
        model_id=None, segment_id="seg-1", source_sequence=0, created_at=time.time(), content="Sure.",
        completed=True)
    accepted = stores.client.post(f"/api/live/speculation/sessions/{stores.session_id}/gen-1/accept",
                                  json={"final_text": "confirm"})
    assert accepted.status_code == 409 and accepted.json()["detail"] == "speculation_answers_proposal"
    session = stores.chat.get_session(stores.session_id)
    assert not any(message.role == "user" for message in session.messages)


def test_a_call_with_guests_is_not_speculated(stores, monkeypatch) -> None:
    from app.platform.chat import live_chat_speculation

    # With guests the server chooses who answers (companion 5.2); a speculated reply is always the host's.
    monkeypatch.setattr(live_chat_speculation, "has_scene_guests", lambda session: True)
    started = stores.client.post(f"/api/live/speculation/sessions/{stores.session_id}/stream",
                                 json={"content": "hello", "segment_id": "seg-1", "source_sequence": 0})
    assert started.status_code == 409 and started.json()["detail"] == "speculation_in_scene"

    # A guest who joined after the speculation started blocks its accept; a chat that cannot have guests is not read.
    seat_reads: list[str] = []
    monkeypatch.setattr(live_chat_speculation, "seats_taken", lambda session_id: seat_reads.append(session_id) or True)
    for generation_id, scene_possible in (("gen-scene", True), ("gen-plain", False)):
        live_chat_speculation._SPECULATIONS[generation_id] = live_chat_speculation._Speculation(
            generation_id=generation_id, session_id=stores.session_id, candidate_text="hello", provider_id=None,
            model_id=None, segment_id="seg-1", source_sequence=0, created_at=time.time(), content="Hi.",
            completed=True, scene_possible=scene_possible)
    accepted = stores.client.post(f"/api/live/speculation/sessions/{stores.session_id}/gen-scene/accept",
                                  json={"final_text": "hello"})
    assert accepted.status_code == 409 and accepted.json()["detail"] == "speculation_in_scene"
    assert seat_reads == [stores.session_id]
    plain = stores.client.post(f"/api/live/speculation/sessions/{stores.session_id}/gen-plain/accept",
                               json={"final_text": "hello"})
    assert plain.status_code == 200 and seat_reads == [stores.session_id]


def test_without_the_assistant_tools_port_an_action_task_does_not_start(monkeypatch) -> None:
    from app.platform.chat import live_call_actions

    class _NoJobs:
        def create_job_once(self, *_args, **_kwargs):
            raise AssertionError("no job is created without the assistant tools")

    monkeypatch.setattr(live_call_actions, "_call_actions", lambda: None)
    task = {"capability": "home.list_devices", "input": {}}
    assert live_call_actions.begin_call_action(_NoJobs(), SimpleNamespace(id="s1"), task, task_id="call-task:m1:0",
                                               user_message_id="m1") is None
