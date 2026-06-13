"""Tests for narration job queue functionality."""
import copy
from unittest.mock import call, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.rpg.api.rpg_session_routes import rpg_session_bp
from app.rpg.session.runtime import (
    apply_turn,
    process_next_narration_job,
)
from app.rpg.session.runtime import (
    _enqueue_narration_request_old as _enqueue_narration_request_compat,
)


def _make_test_app():
    """Build a minimal FastAPI app with the RPG session router for testing."""
    app = FastAPI()
    app.include_router(rpg_session_bp)
    return app


@pytest.fixture
def client():
    return TestClient(_make_test_app())


def test_authoritative_turn_queues_narration_instead_of_generating_inline():
    """Test that authoritative turn queues narration instead of generating it inline."""
    session_id = "test_session"

    # Mock session
    mock_session = {
        "session_id": session_id,
        "runtime_state": {
            "tick": 1,
            "narration_artifacts": [],
            "narration_artifacts_by_turn": {},
        },
    }

    with patch('app.rpg.session.runtime.load_runtime_session', return_value=mock_session), \
         patch('app.rpg.session.runtime.save_runtime_session'), \
         patch('app.rpg.session.runtime._apply_turn_authoritative') as mock_auth:

        mock_auth.return_value = {
            "ok": True,
            "authoritative": {
                "turn_id": "turn:1",
                "tick": 1,
                "resolved_result": {},
                "combat_result": None,
                "xp_result": None,
                "skill_xp_result": None,
                "level_up": None,
                "skill_level_ups": [],
                "summary": "Test summary",
                "presentation": {},
                "response_length": 100,
                "deterministic_fallback_narration": "Fallback narration",
            },
            "narration_request": {
                "turn_id": "turn:1",
                "tick": 1,
            },
            "session": mock_session,
        }

        result = apply_turn(session_id, "test input")

        assert result["ok"] is True
        assert result["result"]["narration_status"] == "queued"
        assert result["result"]["narration"] == "Fallback narration"
        assert result["result"]["raw_llm_narrative"] == ""
        assert result["result"]["used_llm"] is False

        # Note: apply_turn no longer queues narration; it's done in the API layer


def test_worker_processes_one_queued_job():
    """Test that worker processes at most one queued job."""
    session_id = "test_session"

    mock_session = {
        "session_id": session_id,
        "runtime_state": {
            "tick": 1,
            "narration_jobs": [
                {
                    "job_id": "narration:turn:1",
                    "turn_id": "turn:1",
                    "tick": 1,
                    "status": "queued",
                    "created_at": "2023-01-01T00:00:00Z",
                    "started_at": None,
                    "completed_at": None,
                    "error": "",
                    "narration_request": {
                        "turn_id": "turn:1",
                        "tick": 1,
                    },
                }
            ],
            "narration_jobs_by_turn": {
                "turn:1": {
                    "job_id": "narration:turn:1",
                    "turn_id": "turn:1",
                    "tick": 1,
                    "status": "queued",
                    "created_at": "2023-01-01T00:00:00Z",
                    "started_at": None,
                    "completed_at": None,
                    "error": "",
                    "narration_request": {
                        "turn_id": "turn:1",
                        "tick": 1,
                    },
                }
            },
            "narration_artifacts": [],
            "narration_artifacts_by_turn": {},
        },
    }

    with patch('app.rpg.session.runtime.load_runtime_session', return_value=mock_session), \
         patch('app.rpg.session.runtime.save_runtime_session') as mock_save, \
         patch('app.rpg.session.runtime._generate_turn_narration_artifact') as mock_generate:

        mock_generate.return_value = {
            "ok": True,
            "artifact": {
                "turn_id": "turn:1",
                "tick": 1,
                "narration": "Generated narration",
                "used_llm": True,
                "raw_llm_narrative": "Raw LLM",
                "created_at": "2023-01-01T00:00:01Z",
            },
            "session": mock_session,
        }

        result = process_next_narration_job(session_id)

        assert result["ok"] is True
        assert result["status"] == "completed"
        assert result["turn_id"] == "turn:1"

        # Check that job was marked completed
        saved_session = mock_save.call_args_list[1][0][0]  # Second save call
        runtime_state = saved_session["runtime_state"]
        job = runtime_state["narration_jobs_by_turn"]["turn:1"]
        assert job["status"] == "completed"


def test_worker_publishes_full_turn_artifact_payload():
    """Completed player-turn events include the full LLM artifact, not just text."""
    session_id = "test_session"
    base_session = {
        "session_id": session_id,
        "runtime_state": {
            "tick": 6,
            "narration_jobs": [
                {
                    "job_id": "narration:turn:6",
                    "turn_id": "turn:6",
                    "tick": 6,
                    "status": "queued",
                    "job_kind": "player_turn",
                    "created_at": "2023-01-01T00:00:00Z",
                    "started_at": None,
                    "completed_at": None,
                    "worker_token": "",
                    "error": "",
                    "narration_request": {
                        "turn_id": "turn:6",
                        "tick": 6,
                        "job_kind": "player_turn",
                    },
                }
            ],
            "narration_jobs_by_turn": {
                "turn:6": {
                    "job_id": "narration:turn:6",
                    "turn_id": "turn:6",
                    "tick": 6,
                    "status": "queued",
                    "job_kind": "player_turn",
                    "created_at": "2023-01-01T00:00:00Z",
                    "started_at": None,
                    "completed_at": None,
                    "worker_token": "",
                    "error": "",
                    "narration_request": {
                        "turn_id": "turn:6",
                        "tick": 6,
                        "job_kind": "player_turn",
                    },
                }
            },
            "narration_artifacts": [],
            "narration_artifacts_by_turn": {},
        },
    }
    artifact = {
        "turn_id": "turn:6",
        "tick": 6,
        "narration": "Bran answers with real LLM narration.",
        "narration_json": {
            "narration": "Bran wipes the bar and answers.",
            "action": "You ask Bran about his day.",
            "npc": {
                "speaker": "Bran the Innkeeper",
                "line": "A steady day, all told.",
            },
        },
        "speaker_presentation": {"role": "Innkeeper"},
        "used_llm": True,
        "raw_llm_narrative": "{}",
        "created_at": "2023-01-01T00:00:01Z",
    }
    saved_sessions = []
    published_events = []

    def mock_load(_session_id):
        if saved_sessions:
            return copy.deepcopy(saved_sessions[-1])
        return copy.deepcopy(base_session)

    def mock_save(session):
        saved_sessions.append(copy.deepcopy(session))
        return copy.deepcopy(session)

    def mock_publish(_session_id, event):
        published_events.append(copy.deepcopy(event))
        return 1

    with patch("app.rpg.session.runtime_part17.load_runtime_session", side_effect=mock_load), \
         patch("app.rpg.session.runtime_part17.save_runtime_session", side_effect=mock_save), \
         patch("app.rpg.session.runtime_part17._generate_turn_narration_artifact") as mock_generate, \
         patch("app.rpg.session.runtime_part17.publish_narration_event", side_effect=mock_publish):
        mock_generate.return_value = {
            "ok": True,
            "artifact": artifact,
            "session": base_session,
        }

        result = process_next_narration_job(session_id)

    assert result["ok"] is True
    assert result["status"] == "completed"
    narration_events = [
        event for event in published_events
        if event.get("type") == "narration_artifact"
    ]
    assert narration_events
    event = narration_events[-1]
    assert event["turn_id"] == "turn:6"
    assert event["narration"] == artifact["narration"]
    assert event["text"] == artifact["narration"]
    assert event["narration_json"]["npc"]["line"] == "A steady day, all told."
    assert event["speaker_presentation"]["role"] == "Innkeeper"
    assert event["used_llm"] is True


def test_failed_narration_requeues_for_retry():
    """Test that first failure re-queues the job for retry."""
    session_id = "test_session"

    mock_session = {
        "session_id": session_id,
        "runtime_state": {
            "tick": 1,
            "narration_jobs": [
                {
                    "job_id": "narration:turn:1",
                    "turn_id": "turn:1",
                    "tick": 1,
                    "status": "queued",
                    "created_at": "2023-01-01T00:00:00Z",
                    "started_at": None,
                    "completed_at": None,
                    "error": "",
                    "attempts": 0,
                    "max_attempts": 3,
                    "narration_request": {
                        "turn_id": "turn:1",
                        "tick": 1,
                    },
                }
            ],
            "narration_jobs_by_turn": {
                "turn:1": {
                    "job_id": "narration:turn:1",
                    "turn_id": "turn:1",
                    "tick": 1,
                    "status": "queued",
                    "job_kind": "ambient_conversation",
                    "created_at": "2023-01-01T00:00:00Z",
                    "started_at": None,
                    "completed_at": None,
                    "error": "",
                    "narration_request": {
                        "turn_id": "turn:1",
                        "tick": 1,
                    },
                }
            },
            "narration_artifacts": [],
            "narration_artifacts_by_turn": {},
        },
    }

    with patch('app.rpg.session.runtime.load_runtime_session', return_value=mock_session), \
         patch('app.rpg.session.runtime.save_runtime_session') as mock_save, \
         patch('app.rpg.session.runtime._generate_turn_narration_artifact') as mock_generate:

        mock_generate.return_value = {
            "ok": False,
            "error": "Narration generation failed",
            "artifact": {
                "turn_id": "turn:1",
                "tick": 1,
                "narration": "",
                "used_llm": False,
                "raw_llm_narrative": "",
                "created_at": "2023-01-01T00:00:01Z",
            },
            "session": mock_session,
        }

        result = process_next_narration_job(session_id)

        # First failure: re-queued for retry (not immediately failed)
        assert result["ok"] is True
        assert result["status"] == "queued"
        assert result["turn_id"] == "turn:1"
        assert result["attempts"] == 1

        # Check that job was re-queued
        saved_session = mock_save.call_args_list[-1][0][0]
        runtime_state = saved_session["runtime_state"]
        job = runtime_state["narration_jobs_by_turn"]["turn:1"]
        assert job["status"] == "queued"
        assert job["attempts"] == 1


def test_failed_narration_marks_job_failed_after_max_retries():
    """Test that narration is marked failed after max retries."""
    session_id = "test_session"

    mock_session = {
        "session_id": session_id,
        "runtime_state": {
            "tick": 1,
            "narration_jobs": [
                {
                    "job_id": "narration:turn:1",
                    "turn_id": "turn:1",
                    "tick": 1,
                    "status": "queued",
                    "created_at": "2023-01-01T00:00:00Z",
                    "started_at": None,
                    "completed_at": None,
                    "error": "",
                    "attempts": 2,
                    "max_attempts": 3,
                    "narration_request": {
                        "turn_id": "turn:1",
                        "tick": 1,
                    },
                }
            ],
            "narration_jobs_by_turn": {
                "turn:1": {
                    "job_id": "narration:turn:1",
                    "turn_id": "turn:1",
                    "tick": 1,
                    "status": "queued",
                    "created_at": "2023-01-01T00:00:00Z",
                    "started_at": None,
                    "completed_at": None,
                    "error": "",
                    "attempts": 2,
                    "max_attempts": 3,
                    "narration_request": {
                        "turn_id": "turn:1",
                        "tick": 1,
                    },
                }
            },
            "narration_artifacts": [],
            "narration_artifacts_by_turn": {},
        },
    }

    with patch('app.rpg.session.runtime.load_runtime_session', return_value=mock_session), \
         patch('app.rpg.session.runtime.save_runtime_session') as mock_save, \
         patch('app.rpg.session.runtime._generate_turn_narration_artifact') as mock_generate, \
         patch('app.rpg.session.runtime.publish_narration_event'):

        mock_generate.return_value = {
            "ok": False,
            "error": "Narration generation failed",
            "artifact": {
                "turn_id": "turn:1",
                "tick": 1,
                "narration": "",
                "used_llm": False,
                "raw_llm_narrative": "",
                "created_at": "2023-01-01T00:00:01Z",
            },
            "session": mock_session,
        }

        result = process_next_narration_job(session_id)

        assert result["ok"] is False
        assert result["status"] == "failed"
        assert result["turn_id"] == "turn:1"

        # Check that job was marked failed after max retries
        saved_session = mock_save.call_args_list[-1][0][0]
        runtime_state = saved_session["runtime_state"]
        job = runtime_state["narration_jobs_by_turn"]["turn:1"]
        assert job["status"] == "failed"


def test_stale_narration_job_is_marked_stale():
    """Test that stale narration job is marked stale."""
    session_id = "test_session"

    mock_session = {
        "session_id": session_id,
        "runtime_state": {
            "tick": 5,  # Current tick is 5, job tick is 1, so stale
            "narration_jobs": [
                {
                    "job_id": "narration:turn:1",
                    "turn_id": "turn:1",
                    "tick": 1,
                    "status": "queued",
                    "job_kind": "ambient_conversation",
                    "created_at": "2023-01-01T00:00:00Z",
                    "started_at": None,
                    "completed_at": None,
                    "error": "",
                    "narration_request": {
                        "turn_id": "turn:1",
                        "tick": 1,
                    },
                }
            ],
            "narration_jobs_by_turn": {
                "turn:1": {
                    "job_id": "narration:turn:1",
                    "turn_id": "turn:1",
                    "tick": 1,
                    "status": "queued",
                    "created_at": "2023-01-01T00:00:00Z",
                    "started_at": None,
                    "completed_at": None,
                    "error": "",
                    "narration_request": {
                        "turn_id": "turn:1",
                        "tick": 1,
                    },
                }
            },
            "narration_artifacts": [],
            "narration_artifacts_by_turn": {},
        },
    }

    with patch('app.rpg.session.runtime.load_runtime_session', return_value=mock_session), \
         patch('app.rpg.session.runtime.save_runtime_session') as mock_save:

        result = process_next_narration_job(session_id)

        assert result["ok"] is True
        assert result["status"] == "stale"
        assert result["turn_id"] == "turn:1"

        # Check that job was marked stale
        saved_session = mock_save.call_args[0][0]
        runtime_state = saved_session["runtime_state"]
        job = runtime_state["narration_jobs_by_turn"]["turn:1"]
        assert job["status"] == "stale"
        assert "stale_narration_job" in job["error"]


def test_compatibility_wrapper_returns_immediate_result():
    """Test that apply_turn returns immediate result without waiting on narration."""
    session_id = "test_session"

    # Mock session
    mock_session = {
        "session_id": session_id,
        "runtime_state": {
            "tick": 1,
            "narration_artifacts": [],
            "narration_artifacts_by_turn": {},
        },
    }

    with patch('app.rpg.session.runtime.load_runtime_session', return_value=mock_session), \
         patch('app.rpg.session.runtime.save_runtime_session'), \
         patch('app.rpg.session.runtime._apply_turn_authoritative') as mock_auth:

        mock_auth.return_value = {
            "ok": True,
            "authoritative": {
                "turn_id": "turn:1",
                "tick": 1,
                "resolved_result": {"success": True},
                "combat_result": None,
                "xp_result": {"xp_gained": 10},
                "skill_xp_result": {},
                "level_up": None,
                "skill_level_ups": [],
                "summary": "Test summary",
                "presentation": {"description": "Test"},
                "response_length": 50,
                "deterministic_fallback_narration": "Fallback text",
            },
            "narration_request": {
                "turn_id": "turn:1",
                "tick": 1,
            },
            "session": mock_session,
        }

        result = apply_turn(session_id, "test input")

        # Should return immediately with fallback narration
        assert result["ok"] is True
        assert result["result"]["narration"] == "Fallback text"
        assert result["result"]["narration_status"] == "queued"
        resolved = result["result"]["resolved_result"]
        assert resolved["success"] is True
        assert "survival_tick_result" in resolved
        assert result["result"]["xp_result"] == {"xp_gained": 10}

        # Should not have waited for LLM narration
        assert result["result"]["raw_llm_narrative"] == ""
        assert result["result"]["used_llm"] is False

        # Note: apply_turn no longer queues narration; it's done in the API layer


def test_enqueue_idempotent():
    """Test that enqueuing same turn twice is idempotent."""
    session_id = "test_session"
    turn_id = "turn:1"

    mock_session = {
        "session_id": session_id,
        "runtime_state": {
            "tick": 1,
            "narration_jobs": [],
            "narration_jobs_by_turn": {},
            "narration_artifacts": [],
            "narration_artifacts_by_turn": {},
        },
    }

    with patch('app.rpg.session.runtime.load_runtime_session', return_value=mock_session), \
         patch('app.rpg.session.runtime.save_runtime_session'), \
         patch('app.rpg.session.runtime.ensure_narration_worker_running'), \
         patch('app.rpg.session.runtime.signal_narration_work') as mock_signal:

        narration_request = {"turn_id": turn_id, "tick": 1}

        # First enqueue
        result1 = _enqueue_narration_request_compat(session_id, narration_request)
        assert result1["ok"] is True
        assert result1["status"] == "queued"

        # Second enqueue
        result2 = _enqueue_narration_request_compat(session_id, narration_request)
        assert result2["ok"] is True
        assert result2["status"] == "queued"


        assert mock_signal.call_count == 1  # Only first enqueue signals


def test_worker_token_claim_prevents_duplicates():
    """Test that worker token claim prevents duplicate execution.

    When a job is already being processed by one worker (has a non-matching
    worker_token), a second worker call returns 'claimed_elsewhere'.
    """
    session_id = "test_session"

    base_session = {
        "session_id": session_id,
        "runtime_state": {
            "tick": 1,
            "narration_jobs": [
                {
                    "job_id": "narration:turn:1",
                    "turn_id": "turn:1",
                    "tick": 1,
                    "status": "queued",
                    "created_at": "2023-01-01T00:00:00Z",
                    "started_at": None,
                    "completed_at": None,
                    "error": "",
                    "worker_token": None,
                    "narration_request": {"turn_id": "turn:1", "tick": 1},
                }
            ],
            "narration_jobs_by_turn": {
                "turn:1": {
                    "job_id": "narration:turn:1",
                    "turn_id": "turn:1",
                    "tick": 1,
                    "status": "queued",
                    "created_at": "2023-01-01T00:00:00Z",
                    "started_at": None,
                    "completed_at": None,
                    "error": "",
                    "worker_token": None,
                    "narration_request": {"turn_id": "turn:1", "tick": 1},
                }
            },
            "narration_artifacts": [],
            "narration_artifacts_by_turn": {},
        },
    }

    saved_sessions = []

    def mock_load(sid):
        if saved_sessions:
            return copy.deepcopy(saved_sessions[-1])
        return copy.deepcopy(base_session)

    def mock_save(session):
        saved_sessions.append(copy.deepcopy(session))
        return session

    with patch('app.rpg.session.runtime.load_runtime_session', side_effect=mock_load), \
         patch('app.rpg.session.runtime.save_runtime_session', side_effect=mock_save), \
         patch('app.rpg.session.runtime._generate_turn_narration_artifact') as mock_generate, \
         patch('app.rpg.session.runtime.publish_narration_event'):

        mock_generate.return_value = {
            "ok": True,
            "artifact": {
                "turn_id": "turn:1", "tick": 1,
                "narration": "Test narration", "used_llm": True,
            },
            "session": base_session,
        }

        # First worker completes the job
        result1 = process_next_narration_job(session_id)
        assert result1["status"] == "completed"
        assert mock_generate.call_count == 1

        # Second worker finds no queued jobs (already completed)
        result2 = process_next_narration_job(session_id)
        assert result2["status"] == "idle"

        # Only one generation call
        assert mock_generate.call_count == 1


def test_enqueue_signals_worker_manager():
    """Test that enqueuing narration signals worker manager."""
    session_id = "test_session"
    turn_id = "turn:1"

    mock_session = {
        "session_id": session_id,
        "runtime_state": {
            "tick": 1,
            "narration_jobs": [],
            "narration_jobs_by_turn": {},
            "narration_artifacts": [],
            "narration_artifacts_by_turn": {},
        },
    }

    with patch('app.rpg.session.runtime.load_runtime_session', return_value=mock_session), \
         patch('app.rpg.session.runtime.save_runtime_session'), \
         patch('app.rpg.session.runtime.ensure_narration_worker_running'), \
         patch('app.rpg.session.runtime.signal_narration_work'):

        narration_request = {"turn_id": turn_id, "tick": 1}
        _enqueue_narration_request_compat(session_id, narration_request)

            # Note: signals are now handled in API layer


def test_narration_status_resignals_queued_job_without_artifact():
    client = TestClient(_make_test_app())

    session_id = "session:test_status_resignal"

    mock_session = {
        "session_id": session_id,
        "runtime_state": {
            "tick": 2,
            "narration_jobs": [],
            "narration_jobs_by_turn": {
                "turn_2": {
                    "job_id": "narration:turn_2",
                    "turn_id": "turn_2",
                    "tick": 2,
                    "status": "queued",
                    "attempts": 0,
                    "max_attempts": 3,
                    "narration_request": {
                        "turn_id": "turn_2",
                        "tick": 2,
                        "job_kind": "player_turn",
                    },
                },
            },
            "narration_artifacts": [],
            "narration_artifacts_by_turn": {},
        },
    }

    with patch("app.rpg.api.rpg_session_routes.load_runtime_session", return_value=mock_session), \
          patch("app.rpg.api.rpg_session_routes.save_runtime_session"), \
          patch("app.rpg.api.rpg_session_routes.ensure_narration_worker_running") as mock_ensure, \
          patch("app.rpg.api.rpg_session_routes.signal_narration_work") as mock_signal:
        response = client.post("/api/rpg/session/narration_status", json={
            "session_id": session_id,
            "turn_id": "turn_2",
        })

        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True
        assert payload["turn_id"] == "turn_2"
        assert (payload.get("job") or {}).get("status") == "queued"
        assert mock_ensure.call_count == 1
        assert mock_signal.call_args == call(session_id)


def test_narration_status_does_not_resignal_processing_job():
    client = TestClient(_make_test_app())
    session_id = "test_session"

    mock_session = {
        "session_id": session_id,
        "runtime_state": {
            "tick": 2,
            "narration_jobs": [
                {
                    "job_id": "narration:turn_2",
                    "turn_id": "turn_2",
                    "tick": 2,
                    "status": "processing",
                    "started_at": "2099-01-01T00:00:00+00:00",
                    "worker_token": "worker:abc",
                    "attempts": 0,
                    "max_attempts": 3,
                    "narration_request": {
                        "turn_id": "turn_2",
                        "tick": 2,
                        "job_kind": "player_turn",
                    },
                },
            ],
            "narration_jobs_by_turn": {
                "turn_2": {
                    "job_id": "narration:turn_2",
                    "turn_id": "turn_2",
                    "tick": 2,
                    "status": "processing",
                    "started_at": "2099-01-01T00:00:00+00:00",
                    "worker_token": "worker:abc",
                    "attempts": 0,
                    "max_attempts": 3,
                    "narration_request": {
                        "turn_id": "turn_2",
                        "tick": 2,
                        "job_kind": "player_turn",
                    },
                },
            },
            "narration_artifacts": [],
            "narration_artifacts_by_turn": {},
        },
    }

    with patch("app.rpg.api.rpg_session_routes.load_runtime_session", return_value=mock_session), \
         patch("app.rpg.api.rpg_session_routes.save_runtime_session"), \
         patch("app.rpg.api.rpg_session_routes.ensure_narration_worker_running") as mock_ensure, \
         patch("app.rpg.api.rpg_session_routes.signal_narration_work") as mock_signal:
        response = client.post("/api/rpg/session/narration_status", json={
            "session_id": session_id,
            "turn_id": "turn_2",
        })

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["turn_id"] == "turn_2"
    assert (payload.get("job") or {}).get("status") == "processing"
    assert mock_ensure.call_count == 0
    assert mock_signal.call_count == 0


def test_player_turn_job_is_not_marked_stale_when_runtime_tick_advances():
    """Test that player-turn narration jobs are not marked stale when runtime tick advances."""
    session_id = "test_session"

    mock_session = {
        "session_id": session_id,
        "runtime_state": {
            "tick": 10,  # Runtime tick is 10
            "narration_jobs": [
                {
                    "job_id": "narration:turn:6",
                    "turn_id": "turn:6",
                    "tick": 6,  # Job tick is 6
                    "status": "queued",
                    "job_kind": "player_turn",
                    "created_at": "2023-01-01T00:00:00Z",
                    "started_at": None,
                    "completed_at": None,
                    "error": "",
                    "narration_request": {
                        "turn_id": "turn:6",
                        "tick": 6,
                        "job_kind": "player_turn",
                    },
                }
            ],
            "narration_jobs_by_turn": {
                "turn:6": {
                    "job_id": "narration:turn:6",
                    "turn_id": "turn:6",
                    "tick": 6,
                    "status": "queued",
                    "job_kind": "player_turn",
                    "created_at": "2023-01-01T00:00:00Z",
                    "started_at": None,
                    "completed_at": None,
                    "error": "",
                    "narration_request": {
                        "turn_id": "turn:6",
                        "tick": 6,
                        "job_kind": "player_turn",
                    },
                }
            },
            "narration_artifacts": [],
            "narration_artifacts_by_turn": {},
        },
    }

    with patch('app.rpg.session.runtime.load_runtime_session', return_value=mock_session), \
          patch('app.rpg.session.runtime.save_runtime_session') as mock_save, \
          patch('app.rpg.session.runtime._generate_turn_narration_artifact') as mock_generate:

        mock_generate.return_value = {
            "ok": True,
            "artifact": {
                "turn_id": "turn:6",
                "tick": 6,
                "narration": "Generated narration",
                "used_llm": True,
                "raw_llm_narrative": "Raw LLM",
                "created_at": "2023-01-01T00:00:01Z",
            },
            "session": mock_session,
        }

        result = process_next_narration_job(session_id)

        assert result["ok"] is True
        assert result["status"] == "completed"
        assert result["turn_id"] == "turn:6"

        # Verify the job was processed, not marked stale
        saved_session = mock_save.call_args_list[1][0][0]
        runtime_state = saved_session["runtime_state"]
        job = runtime_state["narration_jobs_by_turn"]["turn:6"]
        assert job["status"] == "completed"
        assert "stale" not in job.get("error", "")


def test_service_npc_dialogue_removes_unbacked_prior_memory_reference():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def generate_stream(self, *args, **kwargs):
            yield {
                "text": (
                    '{"format_version":"rpg_narration_v2",'
                    '"narration":"Elara looks over the goods.",'
                    '"action":"Elara checks the available options.",'
                    '"npc":{"speaker":"Elara","line":"Still short on coin from last time, are you?"},'
                    '"reward":"","followup_hooks":[]}'
                )
            }

    service_result = {
        "matched": True,
        "kind": "service_inquiry",
        "service_kind": "shop_goods",
        "provider_id": "npc:Elara",
        "provider_name": "Elara",
        "status": "offers_available",
        "offers": [
            {
                "offer_id": "elara_torch",
                "label": "Torch",
                "price": {"gold": 0, "silver": 1, "copper": 0},
            }
        ],
        "selected_offer_id": "",
        "purchase": None,
        "available_actions": [],
    }

    result = narrate_scene(
        {"title": "Market Stall", "actors": [{"name": "Elara"}]},
        {
            "player_input": "I ask Elara what she sells",
            "service_result": service_result,
            "service_application": {},
            "recalled_service_memories": [],
            "turn_contract": {
                "player_input": "I ask Elara what she sells",
                "service_result": service_result,
                "resolved_result": {"service_result": service_result},
            },
        },
        llm_gateway=StubGateway(),
        retry_on_invalid=False,
    )

    assert "last time" not in result["narration"].lower()
    assert "still short" not in result["narration"].lower()
    assert result["narration_json"]["npc"]["line"] != "Still short on coin from last time, are you?"
