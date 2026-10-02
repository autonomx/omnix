"""Log lines carry request and job ids (WP-10.1, WP-10.2)."""
from __future__ import annotations

import io
import json
import logging
import threading
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.chat import generation_jobs as jobs
from app.observability.logging import (
    RequestContextMiddleware,
    configure_logging,
    log_context,
)

logger = logging.getLogger("omnix.tests.structured_logging")


@pytest.fixture
def captured():
    stream = io.StringIO()
    handler = configure_logging(log_format="json", level="INFO", stream=stream)
    try:
        yield lambda: [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]
    finally:
        logging.getLogger().removeHandler(handler)


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/work")
    def work() -> dict:
        logger.info("handling work")
        return {"ok": True}

    app.add_middleware(RequestContextMiddleware)
    return app


def test_a_request_log_line_carries_the_request_id_returned_to_the_caller(captured) -> None:
    response = TestClient(_app()).get("/work")

    request_id = response.headers["x-request-id"]
    line = next(item for item in captured() if item["message"] == "handling work")
    assert line["request_id"] == request_id
    assert line["logger"] == "omnix.tests.structured_logging"


def test_a_valid_inbound_request_id_is_kept_and_an_invalid_one_replaced(captured) -> None:
    client = TestClient(_app())

    assert client.get("/work", headers={"X-Request-ID": "client-req-12345"}).headers["x-request-id"] == "client-req-12345"
    replaced = client.get("/work", headers={"X-Request-ID": "bad id\nwith newline"}).headers["x-request-id"]
    assert replaced != "bad id\nwith newline" and len(replaced) >= 20


def test_a_dispatched_chat_job_and_its_provider_call_log_the_job_id(monkeypatch, captured) -> None:
    done = threading.Event()

    def run(**kwargs):
        logger.info("running chat job")
        pool_call = jobs._dispatcher.submit_provider_call(lambda: logger.info("provider call"))
        pool_call.result(timeout=2)
        done.set()

    dispatcher = jobs._ChatGenerationDispatcher(worker_count=1, outstanding_limit=2)
    monkeypatch.setattr(jobs, "_dispatcher", dispatcher)
    monkeypatch.setattr(jobs, "_run_chat_generation_job", run)
    store = SimpleNamespace(
        get_job=lambda job_id: SimpleNamespace(id=job_id, status=jobs.JobStatus.QUEUED),
        mark_running=lambda job_id: SimpleNamespace(id=job_id, status=jobs.JobStatus.RUNNING),
    )
    try:
        dispatcher.submit(jobs._ChatGenerationWork(
            chat_store=None, job_store=store,
            job=SimpleNamespace(id="job-77", input_payload={"session_id": "session-1"}),
            request=object(), context_builder=None, completion_hook=None,
        ))
        assert done.wait(2)
    finally:
        dispatcher.close(timeout=1)

    lines = {item["message"]: item for item in captured()}
    assert lines["running chat job"]["job_id"] == "job-77"
    assert lines["running chat job"]["feature"] == "chat"
    assert lines["provider call"]["job_id"] == "job-77"


def test_context_nests_and_user_ids_are_hashed(captured) -> None:
    with log_context(request_id="req-00000001"), log_context(job_id="job-1", user_id="user:alice@example.com"):
        logger.info("nested")
    logger.info("outside")

    lines = {item["message"]: item for item in captured()}
    assert lines["nested"]["request_id"] == "req-00000001"
    assert lines["nested"]["job_id"] == "job-1"
    assert lines["nested"]["user_id"].startswith("user:") and "alice" not in lines["nested"]["user_id"]
    assert "request_id" not in lines["outside"]
    with pytest.raises(ValueError):
        with log_context(password="x"):
            pass


def test_the_gateway_installs_the_request_context_outermost() -> None:
    from app.gateway.app_factory import _install_request_middleware

    gateway = FastAPI()
    _install_request_middleware(gateway, auth_service=object())

    assert gateway.user_middleware[0].cls is RequestContextMiddleware
