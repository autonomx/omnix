"""Codex turns run on a pool of app-server processes (WP-7.2)."""
from __future__ import annotations

import threading

import pytest

from app.providers import ChatGPTCodexProvider, ChatMessage, ProviderConfig
from app.providers.base import provider_turn_owner


class FakeProcess:
    def __init__(self) -> None:
        self.terminated = threading.Event()

    def poll(self):
        return 0 if self.terminated.is_set() else None

    def terminate(self) -> None:
        self.terminated.set()

    def wait(self, timeout):
        return 0

    def kill(self) -> None:
        self.terminated.set()


class FakeCodex(ChatGPTCodexProvider):
    """Each member owns a fake process; a turn runs until released or cancelled."""

    started: list[tuple[str | None, "FakeCodex"]]
    release: threading.Event

    def _run_turn(self, messages, *, conversation_id, owner=None, **_turn):
        with self._lock, self._owned_turn(owner):
            if self._process is None:
                self._process = FakeProcess()
            if conversation_id:
                self._threads[conversation_id] = {"thread_id": f"thread-{conversation_id}"}
            FakeCodex.started.append((owner, self))
            while not FakeCodex.release.wait(0.01):
                if self._process.terminated.is_set():
                    raise ConnectionError("Codex app-server exited")
            yield from ()


@pytest.fixture
def codex(monkeypatch):
    monkeypatch.setenv("OMNIX_CODEX_PROCESS_POOL_SIZE", "2")
    FakeCodex.started = []
    FakeCodex.release = threading.Event()
    provider = FakeCodex(ProviderConfig(provider_type="chatgpt_codex", extra_params={"transport": "app_server"}))
    yield provider
    FakeCodex.release.set()
    provider.close()


def _turn(provider, owner, errors, conversation_id=None):
    def run():
        try:
            with provider_turn_owner(owner):
                for _ in provider._chat_stream(
                    [ChatMessage(role="user", content="hi")],
                    model="gpt-5.6-sol",
                    effort="medium",
                    fast_mode=False,
                    conversation_id=conversation_id,
                    tools=[],
                    request_timeout_seconds=10.0,
                    output_schema=None,
                    owner=owner,
                ):
                    pass
        except Exception as exc:
            errors[owner] = exc

    thread = threading.Thread(target=run)
    thread.start()
    return thread


def _wait_started(count: int) -> None:
    for _ in range(500):
        if len(FakeCodex.started) >= count:
            return
        threading.Event().wait(0.01)
    raise AssertionError(f"{len(FakeCodex.started)} of {count} turns started")


def test_two_turns_run_at_once_on_different_processes(codex) -> None:
    errors: dict = {}
    threads = [_turn(codex, "job-a", errors), _turn(codex, "job-b", errors)]

    _wait_started(2)
    members = {id(member) for _owner, member in FakeCodex.started}
    FakeCodex.release.set()
    for thread in threads:
        thread.join(5)

    assert len(members) == 2
    assert errors == {}


def test_a_cancel_ends_only_its_jobs_process(codex) -> None:
    errors: dict = {}
    threads = [_turn(codex, "job-a", errors), _turn(codex, "job-b", errors)]
    _wait_started(2)
    running = dict(FakeCodex.started)

    assert codex.cancel_active_request(owner="job-a") is True
    threads[0].join(5)

    assert running["job-a"]._process.terminated.is_set()
    assert not running["job-b"]._process.terminated.is_set()
    assert isinstance(errors.get("job-a"), ConnectionError)
    assert "job-b" not in errors
    FakeCodex.release.set()
    threads[1].join(5)
    assert errors.keys() == {"job-a"}


def test_a_conversation_stays_on_the_process_that_holds_its_thread(codex) -> None:
    errors: dict = {}
    FakeCodex.release.set()
    _turn(codex, "first", errors, conversation_id="chat-1").join(5)
    FakeCodex.release.clear()

    # Another job takes the first idle process, the one holding the thread;
    # the conversation's next turn waits for it instead of starting a fresh
    # thread on the other, idle process.
    busy = _turn(codex, "other", errors)
    _wait_started(2)
    holder = FakeCodex.started[0][1]
    assert FakeCodex.started[1][1] is holder
    follow_up = _turn(codex, "second", errors, conversation_id="chat-1")
    threading.Event().wait(0.1)
    assert len(FakeCodex.started) == 2  # still waiting for its own process
    FakeCodex.release.set()
    busy.join(5)
    follow_up.join(5)

    assert FakeCodex.started[2] == ("second", holder)
    assert errors == {}


def test_a_waiting_job_cancelled_before_it_starts_never_runs(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_CODEX_PROCESS_POOL_SIZE", "1")
    FakeCodex.started = []
    FakeCodex.release = threading.Event()
    provider = FakeCodex(ProviderConfig(provider_type="chatgpt_codex", extra_params={"transport": "app_server"}))
    errors: dict = {}
    try:
        running = _turn(provider, "job-a", errors)
        _wait_started(1)
        waiting = _turn(provider, "job-b", errors)

        assert provider.cancel_active_request(owner="job-b") is True
        assert not provider._process.terminated.is_set()
        FakeCodex.release.set()
        running.join(5)
        waiting.join(5)

        assert [owner for owner, _member in FakeCodex.started] == ["job-a"]
        assert "cancelled before it started" in str(errors["job-b"])
    finally:
        FakeCodex.release.set()
        provider.close()
