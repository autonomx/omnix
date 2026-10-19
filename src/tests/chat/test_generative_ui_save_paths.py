"""Both save paths compile omnix-ui fences before the commit lock (GUI-1.4)."""
from __future__ import annotations

from contextlib import contextmanager

import pytest

from app.platform.chat import CreateChatSessionRequest, SendChatMessageRequest
from app.platform.chat import admission as admission_module
from app.platform.chat import generation_jobs
from app.platform.chat.admission import admit_chat_turn, stream_chat_turn
from app.platform.chat.generative_ui import finalize as finalize_module
from app.platform.chat.store import ChatSessionStore
from app.jobs.models import JobStatus
from tests.support.in_memory_jobs import InMemoryJobStore

FENCE = "```"
FENCED = f'Revenue held.\n\n{FENCE}omnix-ui\n{{"type": "stats", "items": [{{"label": "Revenue", "value": "$6,930"}}]}}\n{FENCE}'
PLAIN = "Revenue held steady."


class ScriptedStore(ChatSessionStore):
    """A Chat store whose provider answers with a fixed reply on both paths."""

    def __init__(self, path, reply: str) -> None:
        super().__init__(path)
        self.reply = reply

    def stream_provider_reply_chunks(self, session, user_message, **_kwargs):
        yield {"type": "text_chunk", "text": self.reply}
        yield {"type": "complete", "content": self.reply, "metadata": {"generation_status": "completed"}}

    def _generate_reply(self, session, user_message, **_kwargs):
        return {"content": self.reply, "metadata": {"generation_status": "completed"}}


def _admit(tmp_path, reply: str):
    chat_store = ScriptedStore(tmp_path / "chat.json", reply)
    job_store = InMemoryJobStore(tmp_path / "jobs.sqlite")
    session = chat_store.create_session(CreateChatSessionRequest(title="GUI", provider_id="llm:lmstudio", model_id="m"))
    request = SendChatMessageRequest(content="How was the quarter?", user_turn_id="turn-1")
    return chat_store, job_store, admit_chat_turn(chat_store, job_store, session.id, request), request


def _run_stream(tmp_path, reply: str):
    chat_store, job_store, admission, request = _admit(tmp_path, reply)
    events = list(stream_chat_turn(chat_store, job_store, admission, request))
    assert events[-1]["type"] == "session"
    return chat_store, job_store, admission


def _run_job(tmp_path, reply: str):
    chat_store, job_store, admission, request = _admit(tmp_path, reply)
    generation_jobs._run_chat_generation_job(
        chat_store=chat_store, job_store=job_store, job=admission.job, request=request,
        context_builder=None, completion_hook=None,
    )
    return chat_store, job_store, admission


PATHS = {"stream": _run_stream, "job": _run_job}


def _reply(chat_store, admission):
    return chat_store.get_session(admission.session.id).messages[-1]


@pytest.mark.parametrize("path", sorted(PATHS))
def test_a_fenced_reply_is_stored_with_compiled_ui(tmp_path, path):
    chat_store, job_store, admission = PATHS[path](tmp_path, FENCED)
    message = _reply(chat_store, admission)

    assert message.role == "assistant"
    assert message.content == FENCED  # content is never rewritten
    assert message.metadata["ui"]["text"] == "Revenue held.\n\nRevenue: $6,930."
    assert list(message.metadata["ui"]["blocks"]) == ["b1"]
    assert message.metadata["provider_metrics"] == {"ui_blocks": 1, "ui_dropped": 0, "ui_diagnostics": {}}
    assert job_store.get_job(admission.job.id).status == JobStatus.COMPLETED


@pytest.mark.parametrize("path", sorted(PATHS))
def test_a_reply_without_fences_keeps_its_metadata_unchanged(tmp_path, path):
    chat_store, _, admission = PATHS[path](tmp_path, PLAIN)
    message = _reply(chat_store, admission)

    assert message.content == PLAIN
    assert "ui" not in message.metadata and "ui_error" not in message.metadata


@pytest.mark.parametrize("path", sorted(PATHS))
def test_a_compiler_exception_still_commits_the_reply_as_plain_text(tmp_path, monkeypatch, path):
    def explode(*_args, **_kwargs):
        raise RuntimeError("compiler bug")

    monkeypatch.setattr(finalize_module, "compile_chat_ui", explode)
    chat_store, job_store, admission = PATHS[path](tmp_path, FENCED)
    message = _reply(chat_store, admission)

    assert message.content == FENCED
    assert message.metadata["ui"]["blocks"] == {}
    assert "omnix-ui" not in message.metadata["ui"]["text"]
    assert message.metadata["ui_error"] == {"code": "compile_failed", "error_type": "RuntimeError"}
    assert job_store.get_job(admission.job.id).status == JobStatus.COMPLETED


@pytest.mark.parametrize("path", sorted(PATHS))
def test_the_compile_runs_while_the_commit_lock_is_not_held(tmp_path, monkeypatch, path):
    held: list[bool] = [False]
    observed: list[bool] = []
    original_lock = generation_jobs.chat_job_commit_lock
    original_attach = finalize_module.attach_reply_ui

    @contextmanager
    def tracking_lock(job_id):
        with original_lock(job_id):
            held[0] = True
            try:
                yield
            finally:
                held[0] = False

    def spy(*args, **kwargs):
        observed.append(held[0])
        return original_attach(*args, **kwargs)

    monkeypatch.setattr(generation_jobs, "chat_job_commit_lock", tracking_lock)
    monkeypatch.setattr(generation_jobs, "attach_reply_ui", spy)
    monkeypatch.setattr(admission_module, "attach_reply_ui", spy)
    chat_store, _, admission = PATHS[path](tmp_path, FENCED)

    assert observed == [False]
    assert "ui" in _reply(chat_store, admission).metadata
