from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.rpg_debug_routes import register_rpg_debug_routes
from app.rpg import debug_logging
from app.rpg.debug_logging import (
    configure_rpg_debug_logging,
    log_rpg_event,
    rpg_debug_log_status,
    summarize_session,
    summarize_turn_result,
)


@pytest.fixture
def debug_log_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "resources" / "logs" / "rpg"
    monkeypatch.setenv("OMNIX_RPG_LOG_DIR", str(directory))
    monkeypatch.setenv("OMNIX_RPG_DEBUG_LOGS", "1")
    monkeypatch.setenv("OMNIX_RPG_LOG_MAX_FIELD_CHARS", "256")
    debug_logging._reset_rpg_debug_logging_for_tests()
    yield directory
    debug_logging._reset_rpg_debug_logging_for_tests()


def _events(directory: Path, kind: str = "activity") -> list[dict]:
    path = next(directory.glob(f"{kind}-*.jsonl"))
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_structured_rpg_logs_route_performance_errors_and_redact(debug_log_dir: Path) -> None:
    configure_rpg_debug_logging()
    log_rpg_event(
        "turn.completed",
        category="performance",
        session_id="session-1",
        turn_id="turn-2",
        duration_ms=123.4567,
        fields={
            "command": "Ask Bran about the road.",
            "api_token": "do-not-write-this",
            "long_text": "x" * 400,
        },
    )
    log_rpg_event(
        "turn.exception",
        category="performance",
        level="error",
        session_id="session-1",
        error=RuntimeError("runtime exploded"),
        include_traceback=True,
    )

    activity = _events(debug_log_dir)
    performance = _events(debug_log_dir, "performance")
    errors = _events(debug_log_dir, "errors")
    completed = next(event for event in activity if event["event"] == "turn.completed")

    assert completed["session_id"] == "session-1"
    assert completed["duration_ms"] == 123.457
    assert completed["fields"]["api_token"] == "[redacted]"
    assert "<truncated:" in completed["fields"]["long_text"]
    assert any(event["event"] == "turn.completed" for event in performance)
    assert any(event["error"]["type"] == "RuntimeError" for event in errors)


def test_existing_rpg_python_loggers_are_captured(debug_log_dir: Path) -> None:
    configure_rpg_debug_logging()
    logger = logging.getLogger("app.rpg.session.narration_worker")
    logger.debug("worker iteration", extra={"session_id": "session-logger", "queue_depth": 2})

    event = next(item for item in _events(debug_log_dir) if item["event"] == "python.log")
    assert event["session_id"] == "session-logger"
    assert event["fields"]["message"] == "worker iteration"
    assert event["fields"]["extras"]["queue_depth"] == 2


def test_rpg_http_middleware_records_status_and_duration(debug_log_dir: Path) -> None:
    app = FastAPI()
    register_rpg_debug_routes(app)

    @app.get("/api/rpg/sessions/{session_id}/probe")
    async def probe(session_id: str) -> dict[str, str]:
        return {"session_id": session_id}

    response = TestClient(app).get("/api/rpg/sessions/session-http/probe?view=compact")
    assert response.status_code == 200
    assert response.headers["X-Omnix-Rpg-Trace-Id"].startswith("http-")

    completed = [
        event
        for event in _events(debug_log_dir)
        if event["event"] == "http.request.completed"
        and event.get("session_id") == "session-http"
        and event["fields"]["path"].endswith("/probe")
    ]
    assert completed
    assert completed[-1]["fields"]["status_code"] == 200
    assert completed[-1]["duration_ms"] >= 0

    status = TestClient(app).get("/api/rpg/debug/log-status").json()
    assert status["ok"] is True
    assert status["directory"] == str(debug_log_dir)


def test_turn_and_session_summaries_keep_debugging_signals_compact() -> None:
    session = {
        "manifest": {"session_id": "summary-session", "title": "Road Watch", "turn_count": 4},
        "simulation_state": {
            "scene": {"location": "North Road"},
            "player": {"level": 2, "hp": 17, "inventory": ["torch", "rations"]},
        },
        "runtime_state": {
            "tick": 9,
            "combat_state": {"active": True},
            "narration_jobs": [{"turn_id": "turn-9"}],
        },
    }
    result = {
        "ok": True,
        "turn_id": "turn-9",
        "tick": 9,
        "final_narration": "The bandit lowers his blade.",
        "action_type": "negotiate",
        "manual_turn_stage_timing": {"manual_turn_ms": 42.5, "pre_runtime_intent_llm_ms": 20.0},
        "session": session,
    }

    session_summary = summarize_session(session)
    turn_summary = summarize_turn_result(result)

    assert session_summary == {
        "session_id": "summary-session",
        "title": "Road Watch",
        "tick": 9,
        "turn_count": 4,
        "location": "North Road",
        "player_level": 2,
        "player_hp": 17,
        "inventory_count": 2,
        "combat_active": True,
        "narration_jobs": 1,
    }
    assert turn_summary["visible_text_chars"] == len("The bandit lowers his blade.")
    assert turn_summary["stage_timing"]["manual_turn_ms"] == 42.5


def test_rpg_debug_status_lists_created_files(debug_log_dir: Path) -> None:
    log_rpg_event("session.loaded", session_id="session-status")
    status = rpg_debug_log_status()

    assert status["enabled"] is True
    assert status["directory"] == str(debug_log_dir)
    assert any(item["name"].startswith("activity-") for item in status["files"])
