"""Browser error reports (WP-9.9): bounded, content-trimmed, rate limited, permission-gated."""
from __future__ import annotations

import logging

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.observability.client_errors import register_client_error_routes
from app.security.permissions import DEFAULT_ROLE_PERMISSIONS, kernel_defaults_for


def _client() -> TestClient:
    app = FastAPI()
    router = APIRouter()
    register_client_error_routes(router)
    app.include_router(router)
    return TestClient(app)


def _report(**overrides):
    return {
        "kind": "error",
        "message": "TypeError: x is undefined",
        "stack": "at render (https://omnix.local/assets/index-abc.js?v=1#frag:10:5)",
        "route": "/chatbot",
        "module": "chatbot",
        "build": "abc123",
        **overrides,
    }


def test_a_report_is_logged_without_query_strings(caplog):
    with caplog.at_level(logging.WARNING, logger="app.observability.client_errors"):
        response = _client().post("/api/client-errors", json=_report())
    assert response.status_code == 202
    assert response.json() == {"accepted": True}
    line = caplog.records[-1].getMessage()
    assert "kind=error" in line and "route=/chatbot" in line
    assert "?v=1" not in line and "#frag" not in line


@pytest.mark.parametrize("change", [
    {"route": "/chatbot?session=secret"},
    {"message": "x" * 501},
    {"kind": "unexpected"},
    {"email": "someone@example.com"},
])
def test_reports_outside_the_contract_are_refused(change):
    assert _client().post("/api/client-errors", json=_report(**change)).status_code == 422


def test_reports_are_rate_limited_per_caller(monkeypatch):
    monkeypatch.setenv("OMNIX_CLIENT_ERROR_RATE_LIMIT_PER_MINUTE", "2")
    client = _client()
    statuses = [client.post("/api/client-errors", json=_report()).status_code for _ in range(3)]
    assert statuses == [202, 202, 429]


def test_signed_in_members_and_viewers_may_report():
    assert kernel_defaults_for("/api/client-errors") == ("client:report", "client:report")
    assert "client:report" in DEFAULT_ROLE_PERMISSIONS["member"]
    assert "client:report" in DEFAULT_ROLE_PERMISSIONS["viewer"]
