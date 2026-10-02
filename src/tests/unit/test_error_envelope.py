"""Gateway errors are problem details carrying the request id (WP-10.5)."""
from __future__ import annotations

import io
import json
import logging

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.errors import PROBLEM_MEDIA_TYPE, install_error_envelope, problem_code
from app.observability.logging import RequestContextMiddleware, configure_logging


class _Body(BaseModel):
    count: int


def _app() -> FastAPI:
    app = FastAPI()
    install_error_envelope(app)

    @app.get("/boom")
    def boom() -> dict:
        raise RuntimeError("postgresql://user:secret@db/omnix failed in /srv/omnix/private.py")

    @app.get("/missing")
    def missing() -> dict:
        raise HTTPException(status_code=404, detail="session_not_found")

    @app.get("/limited")
    def limited() -> dict:
        raise HTTPException(status_code=429, detail={"error": "rate_limited", "limit": "login"},
                            headers={"Retry-After": "3"})

    @app.post("/count")
    def count(body: _Body) -> dict:
        return {"count": body.count}

    app.add_middleware(RequestContextMiddleware)
    return app


def test_an_unhandled_exception_answers_500_without_internals() -> None:
    stream = io.StringIO()
    handler = configure_logging(log_format="json", level="INFO", stream=stream)
    try:
        response = TestClient(_app(), raise_server_exceptions=False).get(
            "/boom", headers={"X-Request-ID": "req-boom-0001"},
        )
    finally:
        logging.getLogger().removeHandler(handler)

    assert response.status_code == 500
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    assert response.headers["x-request-id"] == "req-boom-0001"
    body = response.json()
    assert body["code"] == "internal_error" and body["request_id"] == "req-boom-0001"
    assert body["instance"] == "/boom" and body["status"] == 500
    assert "secret" not in response.text and "private.py" not in response.text and "RuntimeError" not in response.text
    logged = next(json.loads(line) for line in stream.getvalue().splitlines() if "unhandled_request_error" in line)
    assert logged["request_id"] == "req-boom-0001"
    assert "RuntimeError" in logged["exception"]


def test_route_errors_keep_their_detail_and_gain_a_code() -> None:
    client = TestClient(_app())

    missing = client.get("/missing").json()
    limited = client.get("/limited")

    assert missing["detail"] == "session_not_found" and missing["code"] == "session_not_found"
    assert missing["title"] == "Not Found" and missing["request_id"]
    assert limited.json()["detail"] == {"error": "rate_limited", "limit": "login"}
    assert limited.json()["code"] == "rate_limited"
    assert limited.headers["retry-after"] == "3"


def test_validation_errors_are_invalid_request_problems() -> None:
    response = TestClient(_app()).post("/count", json={"count": "many"})

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"
    assert response.json()["detail"][0]["loc"] == ["body", "count"]


@pytest.mark.parametrize(("status", "detail", "code"), [
    (404, "Chat session not found", "not_found"),
    (403, {"error": "permission_denied", "permission": "admin:metrics"}, "permission_denied"),
    (409, "chat_turn_in_progress", "chat_turn_in_progress"),
    (503, None, "service_unavailable"),
])
def test_problem_codes(status, detail, code) -> None:
    assert problem_code(status, detail) == code


def test_a_failing_market_data_provider_does_not_leak_its_error(caplog) -> None:
    from types import SimpleNamespace

    from app.trading.api import create_trading_router

    def failing_service():
        def bars(*_args):
            raise RuntimeError("GET https://api.example.test/v2/bars?apiKey=sk-live-secret failed")

        return SimpleNamespace(bars=bars)

    app = FastAPI()
    install_error_envelope(app)
    app.include_router(create_trading_router(market_service_factory=failing_service))

    with caplog.at_level(logging.WARNING, logger="app.trading.api"):
        response = TestClient(app).get("/api/trading/bars", params={"instrument_id": "AAPL"})

    assert response.status_code == 502
    assert response.json()["code"] == "market_data_failed"
    assert "sk-live-secret" not in response.text and "api.example.test" not in response.text
    assert "sk-live-secret" in caplog.text  # the operator still has the cause
