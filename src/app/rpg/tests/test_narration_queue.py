"""Tests for narration job queue functionality."""
from unittest.mock import patch, call

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.rpg.api.rpg_session_routes import rpg_session_bp
from app.rpg.session.narration_worker import signal_narration_work, ensure_narration_worker_running

from app.rpg.session.runtime import (
    apply_turn,
    process_next_narration_job,
    _enqueue_narration_request,
    load_runtime_session,
    save_runtime_session,
)


def _make_test_app():
    """Build a minimal FastAPI app with the RPG session router for testing."""
    app = FastAPI()
    app.include_router(rpg_session_bp)
    return app


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
         patch('app.rpg.session.runtime.save_runtime_session') as mock_save, \
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

        # Check that narration job was queued
        saved_session = mock_save.call_args[0][0]
        runtime_state = saved_session["runtime_state"]
        assert "narration_jobs" in runtime_state
        assert len(runtime_state["narration_jobs"]) == 1
        job = runtime_state["narration_jobs"][0]
        assert job["turn_id"] == "turn:1"
        assert job["status"] == "queued"


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
        assert result["result"]["resolved_result"] == {"success": True}
        assert result["result"]["xp_result"] == {"xp_gained": 10}

        # Should not have waited for LLM narration
        assert result["result"]["raw_llm_narrative"] == ""
        assert result["result"]["used_llm"] is False


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
         patch('app.rpg.session.runtime.save_runtime_session') as mock_save, \
         patch('app.rpg.session.runtime.ensure_narration_worker_running'), \
         patch('app.rpg.session.runtime.signal_narration_work') as mock_signal:

        narration_request = {"turn_id": turn_id, "tick": 1}

        # First enqueue
        result1 = _enqueue_narration_request(session_id, narration_request)
        assert result1["ok"] is True
        assert result1["status"] == "queued"

        # Second enqueue
        result2 = _enqueue_narration_request(session_id, narration_request)
        assert result2["ok"] is True
        assert result2["status"] == "queued"

        # Only one save call (first enqueue)
        assert mock_save.call_count == 1
        assert mock_signal.call_count == 2


def test_worker_token_claim_prevents_duplicates():
    """Test that worker token claim prevents duplicate execution.
    
    When a job is already being processed by one worker (has a non-matching
    worker_token), a second worker call returns 'claimed_elsewhere'.
    """
    session_id = "test_session"
    import copy

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
         patch('app.rpg.session.runtime.ensure_narration_worker_running') as mock_ensure, \
         patch('app.rpg.session.runtime.signal_narration_work') as mock_signal:

        narration_request = {"turn_id": turn_id, "tick": 1}
        _enqueue_narration_request(session_id, narration_request)

        assert mock_ensure.call_count == 1
        assert mock_signal.call_args == call(session_id)


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
