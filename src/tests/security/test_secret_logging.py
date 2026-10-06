"""Secrets never reach the logs (WP-4.11, canary test)."""
from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

CANARY = "omnix-canary-9f3c2b7e1d"


@pytest.fixture
def captured(caplog):
    caplog.set_level(logging.DEBUG)
    return caplog


def _assert_clean(caplog) -> None:
    text = caplog.text + "".join(str(record.__dict__) for record in caplog.records)
    assert CANARY not in text


def test_request_credentials_are_not_logged(captured) -> None:
    from app.composition.gateway.main import create_gateway_app
    from tests.support.auth import FakeAuthenticator

    app = create_gateway_app(auth_service=FakeAuthenticator())
    client = TestClient(app, base_url="http://127.0.0.1", raise_server_exceptions=False,
                        headers={"X-Omnix-Client": "test", "Authorization": f"Bearer {CANARY}",
                                 "X-Omnix-CSRF": CANARY})
    client.cookies.set("omnix_session", CANARY)
    client.get("/api/jobs")
    client.post("/api/jobs", json={})
    client.get("/api/agent-model/v1/models", headers={"Authorization": f"OmnixRun {CANARY}",
                                                         "X-Omnix-Agent-Run-Id": "run-1"})
    _assert_clean(captured)


def test_url_policy_errors_do_not_echo_credentials(captured) -> None:
    from app.security.url_policy import UrlPolicyError, check_outbound_url

    with pytest.raises(UrlPolicyError) as refused:
        check_outbound_url(f"http://user:{CANARY}@169.254.169.254/")
    assert CANARY not in str(refused.value)
    _assert_clean(captured)


def test_audit_details_drop_secrets(captured) -> None:
    from app.security.audit import audit_details

    details = audit_details({"api_key": CANARY, "nested": {"token": CANARY}, "prompt": CANARY})
    assert CANARY not in repr(details)
    _assert_clean(captured)


def test_invalid_run_tokens_are_not_logged(captured) -> None:
    from app.security.run_tokens import RunTokenError, verify_run_token

    for token in (CANARY, f"{CANARY}.{CANARY}"):
        with pytest.raises(RunTokenError) as refused:
            verify_run_token(token, run_id="run-1")
        assert CANARY not in str(refused.value)
    _assert_clean(captured)
