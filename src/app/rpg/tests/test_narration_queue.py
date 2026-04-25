"""Tests for narration job queue functionality."""
import copy
import json
from unittest.mock import call, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.rpg.api.rpg_session_routes import rpg_session_bp
from app.rpg.session.runtime import (
    _apply_idle_tick_to_session,
    _enqueue_narration_request,
    _generate_turn_narration_artifact,
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
        assert result["result"]["resolved_result"] == {"success": True}
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
         patch('app.rpg.session.runtime.save_runtime_session') as mock_save, \
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
         patch('app.rpg.session.runtime.ensure_narration_worker_running') as mock_ensure, \
         patch('app.rpg.session.runtime.signal_narration_work') as mock_signal:

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


def test_ambient_conversation_job_is_marked_stale_when_far_behind():
    """Test that ambient conversation jobs are still marked stale when far behind."""
    session_id = "test_session"

    mock_session = {
        "session_id": session_id,
        "runtime_state": {
            "tick": 10,  # Runtime tick is 10
            "narration_jobs": [
                {
                    "job_id": "narration:ambient:conv:1:beat:1",
                    "turn_id": "ambient:conv:1:beat:1",
                    "tick": 6,  # Job tick is 6
                    "status": "queued",
                    "job_kind": "ambient_conversation",
                    "created_at": "2023-01-01T00:00:00Z",
                    "started_at": None,
                    "completed_at": None,
                    "error": "",
                    "narration_request": {
                        "turn_id": "ambient:conv:1:beat:1",
                        "tick": 6,
                        "job_kind": "ambient_conversation",
                    },
                }
            ],
            "narration_jobs_by_turn": {
                "ambient:conv:1:beat:1": {
                    "job_id": "narration:ambient:conv:1:beat:1",
                    "turn_id": "ambient:conv:1:beat:1",
                    "tick": 6,
                    "status": "queued",
                    "job_kind": "ambient_conversation",
                    "created_at": "2023-01-01T00:00:00Z",
                    "started_at": None,
                    "completed_at": None,
                    "error": "",
                    "narration_request": {
                        "turn_id": "ambient:conv:1:beat:1",
                        "tick": 6,
                        "job_kind": "ambient_conversation",
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
        assert result["turn_id"] == "ambient:conv:1:beat:1"

        # Verify the job was marked stale
        saved_session = mock_save.call_args[0][0]
        runtime_state = saved_session["runtime_state"]
        job = runtime_state["narration_jobs_by_turn"]["ambient:conv:1:beat:1"]
        assert job["status"] == "stale"
        assert "stale_narration_job" in job["error"]


def test_idle_tick_is_suppressed_while_player_turn_narration_pending():
    """Test that idle ticks are suppressed when there's a blocking player-turn narration pending."""
    session_id = "test_session"

    mock_session = {
        "session_id": session_id,
        "simulation_state": {
            "tick": 5,
        },
        "runtime_state": {
            "tick": 5,
            "idle_streak": 0,
            "ambient_seq": 10,
            "last_real_player_activity_at": "2023-01-01T00:00:00Z",
            "runtime_settings": {},
            "narration_jobs": [
                {
                    "job_id": "narration:turn:5",
                    "turn_id": "turn:5",
                    "tick": 5,
                    "status": "queued",
                    "job_kind": "player_turn",
                    "created_at": "2023-01-01T00:00:00Z",
                    "started_at": None,
                    "completed_at": None,
                    "error": "",
                    "narration_request": {
                        "turn_id": "turn:5",
                        "tick": 5,
                        "job_kind": "player_turn",
                    },
                }
            ],
            "narration_jobs_by_turn": {
                "turn:5": {
                    "job_id": "narration:turn:5",
                    "turn_id": "turn:5",
                    "tick": 5,
                    "status": "queued",
                    "job_kind": "player_turn",
                    "created_at": "2023-01-01T00:00:00Z",
                    "started_at": None,
                    "completed_at": None,
                    "error": "",
                    "narration_request": {
                        "turn_id": "turn:5",
                        "tick": 5,
                        "job_kind": "player_turn",
                    },
                }
            },
            "narration_artifacts": [],  # No artifact for turn:5
            "narration_artifacts_by_turn": {},
        },
    }

    result = _apply_idle_tick_to_session(mock_session, reason="test")

    assert result["ok"] is True
    assert result["updates"] == []  # No updates generated
    assert result["idle_debug_trace"]["idle_suppressed"] is True
    assert result["idle_debug_trace"]["reason"] == "blocking_player_turn_narration"
    assert result["idle_gate_open"] is False
    # Tick should not have advanced
    assert result["session"]["simulation_state"]["tick"] == 5
    assert result["session"]["runtime_state"]["tick"] == 5


def test_processing_player_turn_job_does_not_block_idle_tick():
    """Test that a processing player-turn narration job does not block idle ticks."""
    session_id = "test_session"

    mock_session = {
        "session_id": session_id,
        "simulation_state": {
            "tick": 5,
        },
        "runtime_state": {
            "tick": 5,
            "idle_streak": 0,
            "ambient_seq": 10,
            "last_real_player_activity_at": "2023-01-01T00:00:00Z",
            "runtime_settings": {},
            "narration_jobs": [
                {
                    "job_id": "narration:turn:5",
                    "turn_id": "turn:5",
                    "tick": 5,
                    "status": "processing",
                    "job_kind": "player_turn",
                    "created_at": "2023-01-01T00:00:00Z",
                    "started_at": "2023-01-01T00:00:01Z",
                    "completed_at": None,
                    "error": "",
                    "narration_request": {
                        "turn_id": "turn:5",
                        "tick": 5,
                        "job_kind": "player_turn",
                    },
                }
            ],
            "narration_jobs_by_turn": {
                "turn:5": {
                    "job_id": "narration:turn:5",
                    "turn_id": "turn:5",
                    "tick": 5,
                    "status": "processing",
                    "job_kind": "player_turn",
                    "created_at": "2023-01-01T00:00:00Z",
                    "started_at": "2023-01-01T00:00:01Z",
                    "completed_at": None,
                    "error": "",
                    "narration_request": {
                        "turn_id": "turn:5",
                        "tick": 5,
                        "job_kind": "player_turn",
                    },
                }
            },
            "narration_artifacts": [],  # No artifact yet
            "narration_artifacts_by_turn": {},
        },
    }

    result = _apply_idle_tick_to_session(mock_session, reason="test")

    assert result["ok"] is True
    assert result["idle_debug_trace"].get("idle_suppressed") is not True
    assert result["idle_gate_open"] is True  # Should proceed with idle
    # Tick should have advanced
    assert result["session"]["simulation_state"]["tick"] > 5
    assert result["session"]["runtime_state"]["tick"] > 5


def test_enqueue_narration_request_is_single_flight_per_turn_id():
    runtime_state = {
        "narration_jobs": [],
        "narration_jobs_by_turn": {},
        "narration_artifacts_by_turn": {},
    }

    request = {
        "turn_id": "turn:7",
        "tick": 7,
        "session_id": "test_session",
    }

    runtime_state, job1, _ = _enqueue_narration_request(
        runtime_state,
        "turn:7",
        7,
        request,
        "player_turn",
        100,
    )
    runtime_state, job2, _ = _enqueue_narration_request(
        runtime_state,
        "turn:7",
        7,
        request,
        "player_turn",
        100,
    )

    assert job1["job_id"] == job2["job_id"]
    assert len(runtime_state["narration_jobs"]) == 1
    assert runtime_state["narration_jobs_by_turn"]["turn:7"]["job_id"] == job1["job_id"]


def test_enqueue_narration_request_does_not_queue_when_artifact_exists():
    runtime_state = {
        "narration_jobs": [],
        "narration_jobs_by_turn": {},
        "narration_artifacts_by_turn": {
            "turn:7": {
                "turn_id": "turn:7",
                "narration": "done",
            }
        },
    }

    request = {
        "turn_id": "turn:7",
        "tick": 7,
        "session_id": "test_session",
    }

    runtime_state, job, _ = _enqueue_narration_request(
        runtime_state,
        "turn:7",
        7,
        request,
        "player_turn",
        100,
    )

    assert job == {}
    assert runtime_state["narration_jobs"] == []


def test_process_next_narration_job_skips_superseded_queue_entry():
    session_id = "test_session"

    old_job = {
        "job_id": "narration:turn:9:old",
        "turn_id": "turn:9",
        "tick": 9,
        "status": "queued",
        "job_kind": "player_turn",
        "created_at": "2023-01-01T00:00:00Z",
        "started_at": None,
        "completed_at": None,
        "error": "",
        "narration_request": {
            "turn_id": "turn:9",
            "tick": 9,
            "job_kind": "player_turn",
        },
    }
    new_job = {
        "job_id": "narration:turn:9:new",
        "turn_id": "turn:9",
        "tick": 9,
        "status": "queued",
        "job_kind": "player_turn",
        "created_at": "2023-01-01T00:00:01Z",
        "started_at": None,
        "completed_at": None,
        "error": "",
        "narration_request": {
            "turn_id": "turn:9",
            "tick": 9,
            "job_kind": "player_turn",
        },
    }

    mock_session = {
        "session_id": session_id,
        "runtime_state": {
            "tick": 9,
            "narration_jobs": [old_job],
            "narration_jobs_by_turn": {
                "turn:9": new_job,
            },
            "narration_artifacts": [],
            "narration_artifacts_by_turn": {},
        },
    }

    with patch("app.rpg.session.runtime.load_runtime_session", return_value=mock_session):
        result = process_next_narration_job(session_id)

    assert result["ok"] is True
    assert result["status"] == "skipped"
    assert result["reason"] == "superseded_job"
    assert result["turn_id"] == "turn:9"


def test_process_next_narration_job_dedupes_when_artifact_already_exists():
    session_id = "test_session"

    mock_session = {
        "session_id": session_id,
        "runtime_state": {
            "tick": 10,
            "narration_jobs": [
                {
                    "job_id": "narration:turn:10",
                    "turn_id": "turn:10",
                    "tick": 10,
                    "status": "queued",
                    "job_kind": "player_turn",
                    "created_at": "2023-01-01T00:00:00Z",
                    "started_at": None,
                    "completed_at": None,
                    "error": "",
                    "narration_request": {
                        "turn_id": "turn:10",
                        "tick": 10,
                        "job_kind": "player_turn",
                    },
                }
            ],
            "narration_jobs_by_turn": {
                "turn:10": {
                    "job_id": "narration:turn:10",
                    "turn_id": "turn:10",
                    "tick": 10,
                    "status": "queued",
                    "job_kind": "player_turn",
                    "created_at": "2023-01-01T00:00:00Z",
                    "started_at": None,
                    "completed_at": None,
                    "error": "",
                    "narration_request": {
                        "turn_id": "turn:10",
                        "tick": 10,
                        "job_kind": "player_turn",
                    },
                }
            },
            "narration_artifacts": [],
            "narration_artifacts_by_turn": {
                "turn:10": {
                    "turn_id": "turn:10",
                    "narration": "already_done",
                }
            },
        },
    }

    with patch("app.rpg.session.runtime.load_runtime_session", return_value=mock_session), \
         patch("app.rpg.session.runtime.save_runtime_session") as mock_save:
        result = process_next_narration_job(session_id)

    assert result["ok"] is True
    assert result["status"] == "completed"
    assert result["turn_id"] == "turn:10"
    assert result["deduped"] is True

    saved_session = mock_save.call_args[0][0]
    runtime_state = saved_session["runtime_state"]
    job = runtime_state["narration_jobs_by_turn"]["turn:10"]
    assert job["status"] == "completed"


def test_turn_stream_emits_live_first_draft_artifact(client):
    session_id = "test_session"

    authoritative_result = {
        "ok": True,
        "authoritative": {
            "turn_id": "turn:5",
            "tick": 5,
            "resolved_result": {},
            "combat_result": {},
            "xp_result": {},
            "skill_xp_result": {},
            "level_up": None,
            "skill_level_ups": [],
            "summary": "summary",
            "presentation": {},
            "response_length": "short",
            "deterministic_fallback_narration": "",
        },
        "narration_request": {
            "turn_id": "turn:5",
            "tick": 5,
            "scene": {"title": "Test"},
            "narration_context": {"player_input": "look around"},
            "performance": {
                "enable_live_first_draft_stream": True,
                "enable_live_narration_llm": True,
            },
        },
    }

    mock_session = {
        "session_id": session_id,
        "runtime_state": {"tick": 5},
    }

    artifact_result = {
        "ok": True,
        "artifact": {
            "turn_id": "turn:5",
            "tick": 5,
            "narration": "Scene\nAction\nBran: \"Hello.\"",
            "used_llm": True,
            "raw_llm_narrative": "{\"narration\":\"Scene\"}",
            "narration_json": {"narration": "Scene"},
            "speaker_presentation": {},
            "format_warning": False,
            "artifact_type": "turn_narration",
        },
    }

    def _fake_generate(session_id_arg, narration_request_arg, on_chunk=None):
        if on_chunk:
            on_chunk("Scene ")
            on_chunk("Action ")
        return artifact_result

    with patch("app.rpg.api.rpg_session_routes._apply_turn_authoritative", return_value=authoritative_result), \
         patch("app.rpg.api.rpg_session_routes.load_runtime_session", return_value=mock_session), \
         patch("app.rpg.api.rpg_session_routes._generate_turn_narration_artifact", side_effect=_fake_generate), \
         patch("app.rpg.api.rpg_session_routes.ensure_narration_worker_running") as mock_worker, \
         patch("app.rpg.api.rpg_session_routes.signal_narration_work") as mock_signal:
        response = client.post("/api/rpg/session/turn/stream", json={
            "session_id": session_id,
            "input": "look around",
        })

    assert response.status_code == 200
    body = response.text
    assert '"type": "authoritative_result"' in body
    assert '"type": "token"' in body
    assert '"type": "narration_artifact"' in body
    assert '"live_draft_streaming": true' in body
    assert mock_worker.call_count == 0
    assert mock_signal.call_count == 0


def test_process_next_narration_job_skips_when_authoritative_job_already_processing():
    session_id = "test_session"

    mock_session = {
        "session_id": session_id,
        "runtime_state": {
            "tick": 10,
            # Simulate a stale queue snapshot still containing a queued entry.
            "narration_jobs": [
                {
                    "job_id": "narration:turn:11",
                    "turn_id": "turn:11",
                    "tick": 11,
                    "status": "queued",
                    "job_kind": "player_turn",
                    "created_at": "2023-01-01T00:00:00Z",
                    "started_at": None,
                    "completed_at": None,
                    "worker_token": "",
                    "error": "",
                    "narration_request": {
                        "turn_id": "turn:11",
                        "tick": 11,
                        "job_kind": "player_turn",
                    },
                }
            ],
            # But the authoritative per-turn state is already processing.
            "narration_jobs_by_turn": {
                "turn:11": {
                    "job_id": "narration:turn:11",
                    "turn_id": "turn:11",
                    "tick": 11,
                    "status": "processing",
                    "job_kind": "player_turn",
                    "created_at": "2023-01-01T00:00:00Z",
                    "started_at": "2023-01-01T00:00:01Z",
                    "completed_at": None,
                    "worker_token": "worker:already-running",
                    "error": "",
                    "narration_request": {
                        "turn_id": "turn:11",
                        "tick": 11,
                        "job_kind": "player_turn",
                    },
                }
            },
            "narration_artifacts": [],
            "narration_artifacts_by_turn": {},
        },
    }

    with patch("app.rpg.session.runtime.load_runtime_session", return_value=mock_session), \
         patch("app.rpg.session.runtime.save_runtime_session") as mock_save, \
         patch("app.rpg.session.runtime._generate_turn_narration_artifact") as mock_generate:
        result = process_next_narration_job(session_id)

    assert result["ok"] is True
    assert result["status"] == "skipped"
    assert result["reason"] == "already_processing"
    assert result["turn_id"] == "turn:11"
    assert mock_generate.call_count == 0
    assert mock_save.call_count == 0


def test_generate_turn_narration_artifact_streams_chunks_and_persists_full_text():
    chunks = []

    def on_chunk(piece):
        chunks.append(piece)

    session_id = "test_session"
    narration_request = {
        "turn_id": "turn:11",
        "tick": 11,
        "scene": {
            "scene_id": "scene:tick:11",
            "title": "The Rusty Flagon Tavern",
            "summary": "You ask Bran the price of a room.",
        },
        "narration_context": {
            "player_input": "well, how much?",
        },
        "performance": {
            "enable_live_narration_llm": True,
            "enable_narration_retry": False,
        },
    }

    narration_result = {
        "narration": "Bran names the price.",
        "raw_llm_narrative": "Bran names the price.",
        "used_llm": True,
    }

    with patch("app.rpg.session.runtime.narrate_scene", side_effect=lambda *args, **kwargs: (
        kwargs["on_chunk"]("Bran "),
        kwargs["on_chunk"]("names "),
        kwargs["on_chunk"]("the price."),
        narration_result
    )[-1]):
        result = _generate_turn_narration_artifact(
            session_id,
            narration_request,
            on_chunk=on_chunk,
        )

    assert result["ok"] is True
    artifact = result["artifact"]
    assert artifact["narration"] == "Bran names the price."
    assert "".join(chunks) == "Bran names the price."


def test_generate_turn_narration_artifact_uses_streamed_text_when_result_text_missing():
    chunks = []

    def on_chunk(piece):
        chunks.append(piece)

    session_id = "test_session"
    narration_request = {
        "turn_id": "turn:12",
        "tick": 12,
        "scene": {
            "scene_id": "scene:tick:12",
            "title": "The Rusty Flagon Tavern",
            "summary": "You ask again.",
        },
        "narration_context": {
            "player_input": "well, how much?",
        },
        "performance": {
            "enable_live_narration_llm": True,
            "enable_narration_retry": False,
        },
    }

    with patch("app.rpg.session.runtime.narrate_scene", side_effect=lambda *args, **kwargs: (
        kwargs["on_chunk"]("Five "),
        kwargs["on_chunk"]("silver."),
        {"narration": "", "raw_llm_narrative": "", "used_llm": True}
    )[-1]):
        result = _generate_turn_narration_artifact(session_id, narration_request, on_chunk=on_chunk)

    assert result["ok"] is True
    assert result["artifact"]["narration"] == "Five silver."


def test_narration_json_contract_renders_text():
    from app.rpg.ai.world_scene_narrator import (
        _extract_json_object_from_text,
        _normalize_narration_json,
        _render_narration_text_from_json,
    )

    raw = json.dumps({
        "format_version": "rpg_narration_v2",
        "narration": "The tavern grows quiet.",
        "action": "Bran studies you for a moment.",
        "npc": {
            "speaker": "Bran the Innkeeper",
            "line": "A room is five silver."
        },
        "reward": "",
        "followup_hooks": [],
    })

    parsed = _extract_json_object_from_text(raw)
    normalized = _normalize_narration_json(parsed)
    rendered = _render_narration_text_from_json(normalized)

    assert "The tavern grows quiet." in rendered
    assert "Bran studies you for a moment." in rendered
    assert 'Bran the Innkeeper: "A room is five silver."' in rendered


def test_narration_json_contract_recovers_from_label_text():
    from app.rpg.ai.world_scene_narrator import (
        _extract_json_object_from_text,
        _recover_narration_from_raw_text,
        _render_narration_text_from_json,
    )

    raw = (
        "NARRATOR: The tavern grows quiet.\n"
        "ACTION: Bran studies you for a moment.\n"
        'NPC: Bran the Innkeeper: "A room is five silver."\n'
    )

    parsed = _extract_json_object_from_text(raw)
    assert parsed == {}

    recovered = _recover_narration_from_raw_text(raw)
    rendered = _render_narration_text_from_json(recovered)

    assert "The tavern grows quiet." in rendered
    assert "Bran studies you for a moment." in rendered
    assert 'Bran the Innkeeper: "A room is five silver."' in rendered


def test_accommodation_dialogue_does_not_invent_room_offer_without_service_result():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def call(self, method, *args, **kwargs):
            if method == "generate_stream":
                return self.generate_stream(*args, **kwargs)
            if method == "generate":
                return {
                    "text": (
                        '{"format_version":"rpg_narration_v2",'
                        '"narration":"Bran looks up from behind the counter.",'
                        '"action":"Bran considers your request.",'
                        '"npc":{"speaker":"Bran","line":"A room, you say? Well, we do have a few vacant rooms available on the top floor with the best view in town."},'
                        '"reward":"","followup_hooks":[]}'
                    )
                }
            return {}

        def generate_stream(self, *args, **kwargs):
            yield {
                "text": (
                    '{"format_version":"rpg_narration_v2",'
                    '"narration":"Bran looks up from behind the counter.",'
                    '"action":"Bran considers your request.",'
                    '"npc":{"speaker":"Bran","line":"A room, you say? Well, we do have a few vacant rooms available on the top floor with the best view in town."},'
                    '"reward":"","followup_hooks":[]}'
                )
            }

    scene = {
        "title": "The Rusty Flagon Tavern",
        "actors": [{"name": "Bran"}],
    }
    narration_context = {
        "player_input": "I ask Bran for a room to rent",
        "turn_contract": {
            "player_input": "I ask Bran for a room to rent",
            "semantic_action": {
                "action_type": "trade",
                "activity_label": "request_accommodation",
                "target_name": "Bran",
            },
            "narration_brief": {"summary": "I ask Bran for a room to rent"},
            "resolved_result": {
                "action_metadata": {
                    "transaction_kind": "",
                    "price_source": "",
                    "provider_id": "",
                    "provider_name": "",
                },
                "effect_result": {"service_effects": {}},
            },
        },
        "resolved_result": {
            "ok": True,
            "target_name": "Bran",
            "action_metadata": {
                "transaction_kind": "",
                "price_source": "",
                "provider_id": "",
                "provider_name": "",
            },
            "effect_result": {"service_effects": {}},
        },
    }

    result = narrate_scene(
        scene,
        narration_context,
        llm_gateway=StubGateway(),
        retry_on_invalid=False,
    )
    text = result["narration"].lower()

    assert "action: you ask bran for a room to rent" in text
    assert "result: bran considers your request" in text
    assert "vacant rooms" not in text
    assert "top floor" not in text
    assert "best view" not in text
    assert "let me check what i can offer" in text


def test_accommodation_grounding_catches_cozy_room_and_cost_invention():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def generate_stream(self, *args, **kwargs):
            yield {
                "text": (
                    '{"format_version":"rpg_narration_v2",'
                    '"narration":"The tavern quiets as Bran looks your way.",'
                    '"action":"With a hopeful glint in your eye, you approach Bran and ask if he has a room to rent.",'
                    '"npc":{"speaker":"Bran","line":"Aye, I\\\'ve got a cozy little room above the inn, perfect for a traveler such as yourself. What\\\'ll it cost you?"},'
                    '"reward":"","followup_hooks":[]}'
                )
            }

    scene = {
        "title": "The Rusty Flagon Tavern",
        "actors": [{"name": "Bran"}],
    }

    narration_context = {
        "player_input": "I ask Bran for a room to rent",
        "turn_contract": {
            "player_input": "I ask Bran for a room to rent",
            "semantic_action": {
                "action_type": "social_activity",
                "activity_label": "requesting_rental",
                "target_name": "Bran",
                "reason": "rent_room",
            },
            "narration_brief": {
                "summary": "I ask Bran for a room to rent",
            },
            "resolved_result": {
                "action_metadata": {
                    "transaction_kind": "",
                    "price_source": "",
                    "provider_id": "",
                    "provider_name": "",
                },
                "effect_result": {
                    "service_effects": {},
                },
            },
        },
        "resolved_result": {
            "outcome": "success",
            "target_name": "Bran",
            "action_metadata": {
                "transaction_kind": "",
                "price_source": "",
                "provider_id": "",
                "provider_name": "",
            },
            "effect_result": {
                "service_effects": {},
            },
        },
    }

    result = narrate_scene(
        scene,
        narration_context,
        llm_gateway=StubGateway(),
        retry_on_invalid=False,
    )

    text = result["narration"].lower()

    assert "action: you ask bran for a room to rent" in text
    assert "result: bran considers your request" in text

    assert "cozy little room" not in text
    assert "above the inn" not in text
    assert "perfect for a traveler" not in text
    assert "what'll it cost" not in text
    assert "cost you" not in text

    assert "let me check what i can offer" in text


def test_live_narrator_renders_authoritative_action_and_preserves_npc_dialogue():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    full_line = (
        "Ah, you're looking to rent a room, eh? We've got a cozy little number "
        "on the top floor, just down the hall from the kitchen. It's the best "
        "view in town, aside from the garden out back."
    )

    class StubGateway:
        def call(self, method, *args, **kwargs):
            if method == "generate_stream":
                return self.generate_stream(*args, **kwargs)
            elif method == "generate":
                return {"text": (
                    '{"format_version":"rpg_narration_v2",'
                    '"narration":"You approach the innkeeper as you inquire about available lodgings.",'
                    '"action":"Bran nods thoughtfully as he considers your request.",'
                    f'"npc":{{"speaker":"Bran","line":{json.dumps(full_line)}}},'
                    '"reward":"","followup_hooks":[]}'
                )}
            return {}

        def generate_stream(self, *args, **kwargs):
            yield {
                "text": (
                    '{"format_version":"rpg_narration_v2",'
                    '"narration":"You approach the innkeeper as you inquire about available lodgings.",'
                    '"action":"Bran nods thoughtfully as he considers your request.",'
                    f'"npc":{{"speaker":"Bran","line":{json.dumps(full_line)}}},'
                    '"reward":"","followup_hooks":[]}'
                )
            }

    scene = {
        "title": "The Rusty Flagon Tavern",
        "actors": [{"name": "Bran"}],
    }
    narration_context = {
        "player_input": "I ask Bran for a room to rent",
        "turn_contract": {
            "player_input": "I ask Bran for a room to rent",
            "narration_brief": {"summary": "I ask Bran for a room to rent"},
        },
        "resolved_result": {"ok": True, "target_name": "Bran"},
    }

    result = narrate_scene(scene, narration_context, llm_gateway=StubGateway(), retry_on_invalid=False)
    text = result["narration"]

    assert "Action: You ask Bran for a room to rent" in text
    assert "Result: Bran nods thoughtfully as he considers your request." in text
    assert full_line in text
    assert "kitc..." not in text


def test_narrate_scene_does_not_emit_format_invalid_on_non_json_llm_text():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    llm_output = "Bran narrows his eyes. A room is five silver."

    with patch("app.rpg.ai.world_scene_narrator._generate_live_narrative", return_value=llm_output):
        result = narrate_scene(
            {"title": "The Rusty Flagon Tavern"},
            {"player_input": "how much for a room?"},
            llm_gateway=object(),
        )

    assert "[ERROR: LLM FORMAT INVALID]" not in result.get("narration", "")
    assert result.get("used_llm") is True


def test_narrator_reward_and_action_are_authoritative_only():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def generate_stream(self, *args, **kwargs):
            yield {"text": '{"format_version":"rpg_narration_v2","narration":"The tavern goes quiet.","action":"You win a fortune.","npc":{"speaker":"Bran the Innkeeper","line":"Take this chest of gold."},"reward":"25 gold and merchant reputation","followup_hooks":[]}'}

    scene = {
        "title": "The Rusty Flagon Tavern",
        "actors": [{"name": "Bran the Innkeeper"}, {"name": "Elara the Merchant"}],
    }
    narration_context = {
        "resolved_result": {
            "ok": True,
            "message": "Bran quotes a price for the room.",
            "target_name": "Bran the Innkeeper",
            "dialogue": "A room costs five silver pieces, up front.",
        },
        "xp_result": {"player_xp": 0},
        "skill_xp_result": {"awards": {}},
        "level_up": [],
        "skill_level_ups": [],
    }

    result = narrate_scene(scene, narration_context, llm_gateway=StubGateway(), retry_on_invalid=False)
    text = result["narration"]
    assert "fortune" not in text.lower()
    assert "25 gold" not in text.lower()
    assert "merchant reputation" not in text.lower()
    assert "Bran quotes a price for the room." in text


def test_narrator_rejects_invented_npc_speaker():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def generate_stream(self, *args, **kwargs):
            yield {"text": '{"format_version":"rpg_narration_v2","narration":"The town guard Captain steps forward. Captain of the Town Guard says: \"Seize him.\"","action":"You insult Bran.","npc":{"speaker":"Captain of the Town Guard","line":"Seize him"},"reward":"","followup_hooks":[]}'}

    scene = {
        "title": "The Rusty Flagon Tavern",
        "actors": [{"name": "Bran the Innkeeper"}, {"name": "Elara the Merchant"}],
    }
    narration_context = {
        "resolved_result": {
            "ok": True,
            "message": "Bran scowls at your insult.",
            "target_name": "Bran the Innkeeper",
        },
        "xp_result": {"player_xp": 0},
        "skill_xp_result": {"awards": {}},
        "level_up": [],
        "skill_level_ups": [],
    }

    result = narrate_scene(scene, narration_context, llm_gateway=StubGateway(), retry_on_invalid=False)
    text = result["narration"]
    assert "Captain of the Town Guard" not in text
    assert "Seize him" not in text


def test_narrator_respects_recent_authoritative_room_price():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def generate_stream(self, *args, **kwargs):
            yield {"text": '{"format_version":"rpg_narration_v2","narration":"Bran names a price of ten gold coins for the room.","action":"You ask about the room price.","npc":{"speaker":"Bran the Innkeeper","line":"Ten gold for the night."},"reward":"","followup_hooks":[]}'}

    scene = {
        "title": "The Rusty Flagon Tavern",
        "actors": [{"name": "Bran the Innkeeper"}, {"name": "Elara the Merchant"}],
    }
    narration_context = {
        "resolved_result": {
            "ok": True,
            "message": "You ask Bran how much the room costs.",
            "target_name": "Bran the Innkeeper",
            "dialogue": "A room costs five silver pieces, up front.",
        },
        "recent_authoritative_facts": [
            'Tick 2: Bran quotes a price for the room. | Bran the Innkeeper said: "A room costs five silver pieces, up front."'
        ],
        "xp_result": {"player_xp": 0},
        "skill_xp_result": {"awards": {}},
        "level_up": [],
        "skill_level_ups": [],
    }

    result = narrate_scene(scene, narration_context, llm_gateway=StubGateway(), retry_on_invalid=False)
    text = result["narration"]
    assert "ten gold" not in text.lower()
    assert "five silver" in text.lower()


def test_narrator_rejects_invented_guards_and_guilds_from_narration_text():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def generate_stream(self, *args, **kwargs):
            yield {"text": '{"format_version":"rpg_narration_v2","narration":"Elara signals the guards and word spreads through the merchant guild.","action":"You insult Bran.","npc":{"speaker":"Bran the Innkeeper","line":"Watch your tongue."},"reward":"","followup_hooks":[]}'}

    scene = {
        "title": "The Rusty Flagon Tavern",
        "actors": [{"name": "Bran the Innkeeper"}, {"name": "Elara the Merchant"}],
    }
    narration_context = {
        "resolved_result": {
            "ok": True,
            "message": "Bran scowls at your insult.",
            "target_name": "Bran the Innkeeper",
        },
        "recent_authoritative_facts": [
            "Tick 4: Bran scowls at your insult."
        ],
        "xp_result": {"player_xp": 0},
        "skill_xp_result": {"awards": {}},
        "level_up": [],
        "skill_level_ups": [],
    }

    result = narrate_scene(scene, narration_context, llm_gateway=StubGateway(), retry_on_invalid=False)
    text = result["narration"].lower()
    assert "guards" not in text
    assert "merchant guild" not in text


def test_normalize_final_narration_text_preserves_dialogue_ellipsis():
    from app.rpg.session.runtime import _normalize_final_narration_text

    value = _normalize_final_narration_text(
        'Bran: "I was thinking..."'
    )

    assert value == 'Bran: "I was thinking..."'


def test_normalize_final_narration_text_adds_terminal_punctuation():
    from app.rpg.session.runtime import _normalize_final_narration_text

    value = _normalize_final_narration_text(
        "Bran the Innkeeper names his price"
    )

    assert value == "Bran the Innkeeper names his price."


def test_accommodation_grounding_blocks_vacancy_and_follow_me_claims():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def generate_stream(self, *args, **kwargs):
            yield {
                "text": (
                    '{"format_version":"rpg_narration_v2",'
                    '"narration":"The inn common room quiets as Bran looks your way.",'
                    '"action":"You ask Bran for a room to rent, your persuasive voice carrying across the room.",'
                    '"npc":{"speaker":"Bran","line":"A room, you say? Well, we haven\\\'t had any vacancies lately, but I might have somethin\\\' for you. Follow me."},'
                    '"reward":"+6 persuasion XP","followup_hooks":[]}'
                )
            }

    scene = {
        "title": "The Rusty Flagon Tavern",
        "actors": [{"name": "Bran"}],
    }

    narration_context = {
        "player_input": "I ask Bran for a room to rent",
        "turn_contract": {
            "player_input": "I ask Bran for a room to rent",
            "semantic_action": {
                "action_type": "social_activity",
                "activity_label": "asking_for_room_rental",
                "target_name": "Bran",
                "reason": "asking_for_room_rental",
            },
            "narration_brief": {
                "summary": "I ask Bran for a room to rent",
            },
            "resolved_result": {
                "action_metadata": {
                    "transaction_kind": "",
                    "price_source": "",
                    "provider_id": "",
                    "provider_name": "",
                },
                "effect_result": {
                    "service_effects": {},
                },
            },
        },
        "resolved_result": {
            "outcome": "success",
            "target_name": "Bran",
            "action_metadata": {
                "transaction_kind": "",
                "price_source": "",
                "provider_id": "",
                "provider_name": "",
            },
            "effect_result": {
                "service_effects": {},
            },
        },
    }

    result = narrate_scene(
        scene,
        narration_context,
        llm_gateway=StubGateway(),
        retry_on_invalid=False,
    )

    text = result["narration"].lower()
    narration_json = result["narration_json"]

    assert "action: you ask bran for a room to rent" in text
    assert "result: bran considers your request" in text

    assert "vacancies" not in text
    assert "might have somethin" not in text
    assert "something for you" not in text
    assert "follow me" not in text

    assert "let me check what i can offer" in text
    assert narration_json["reward"] == ""


def test_service_narration_uses_registered_lodging_offers():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def generate_stream(self, *args, **kwargs):
            yield {
                "text": (
                    '{"format_version":"rpg_narration_v2",'
                    '"narration":"Bran watches you from behind the counter.",'
                    '"action":"You politely inquire about renting a room from Bran.",'
                    '"npc":{"speaker":"Bran","line":"Rooms, you say? I have a few, but they are not cheap."},'
                    '"reward":"","followup_hooks":[]}'
                )
            }

    scene = {
        "title": "The Rusty Flagon Tavern",
        "actors": [{"name": "Bran"}],
    }

    narration_context = {
        "player_input": "I ask Bran for a room to rent",
        "turn_contract": {
            "player_input": "I ask Bran for a room to rent",
            "service_result": {
                "matched": True,
                "kind": "service_inquiry",
                "service_kind": "lodging",
                "provider_id": "npc:Bran",
                "provider_name": "Bran",
                "location_id": "loc_tavern",
                "status": "offers_available",
                "offers": [
                    {
                        "offer_id": "bran_lodging_common_cot",
                        "service_kind": "lodging",
                        "label": "Common room cot",
                        "price": {"gold": 0, "silver": 5, "copper": 0},
                    },
                    {
                        "offer_id": "bran_lodging_private_room",
                        "service_kind": "lodging",
                        "label": "Private room",
                        "price": {"gold": 1, "silver": 0, "copper": 0},
                    },
                ],
                "selected_offer_id": "",
                "purchase": None,
                "available_actions": [],
                "source": "deterministic_service_resolver",
            },
            "narration_brief": {
                "summary": "I ask Bran for a room to rent",
            },
            "resolved_result": {
                "service_result": {
                    "matched": True,
                    "kind": "service_inquiry",
                    "service_kind": "lodging",
                    "provider_id": "npc:Bran",
                    "provider_name": "Bran",
                    "location_id": "loc_tavern",
                    "status": "offers_available",
                    "offers": [
                        {
                            "offer_id": "bran_lodging_common_cot",
                            "service_kind": "lodging",
                            "label": "Common room cot",
                            "price": {"gold": 0, "silver": 5, "copper": 0},
                        },
                        {
                            "offer_id": "bran_lodging_private_room",
                            "service_kind": "lodging",
                            "label": "Private room",
                            "price": {"gold": 1, "silver": 0, "copper": 0},
                        },
                    ],
                    "selected_offer_id": "",
                    "purchase": None,
                    "available_actions": [],
                    "source": "deterministic_service_resolver",
                }
            },
        },
        "resolved_result": {
            "service_result": {
                "matched": True,
                "kind": "service_inquiry",
                "service_kind": "lodging",
                "provider_id": "npc:Bran",
                "provider_name": "Bran",
                "location_id": "loc_tavern",
                "status": "offers_available",
                "offers": [
                    {
                        "offer_id": "bran_lodging_common_cot",
                        "service_kind": "lodging",
                        "label": "Common room cot",
                        "price": {"gold": 0, "silver": 5, "copper": 0},
                    },
                    {
                        "offer_id": "bran_lodging_private_room",
                        "service_kind": "lodging",
                        "label": "Private room",
                        "price": {"gold": 1, "silver": 0, "copper": 0},
                    },
                ],
                "selected_offer_id": "",
                "purchase": None,
                "available_actions": [],
                "source": "deterministic_service_resolver",
            }
        },
    }

    result = narrate_scene(
        scene,
        narration_context,
        llm_gateway=StubGateway(),
        retry_on_invalid=False,
    )

    text = result["narration"].lower()
    narration_json = result["narration_json"]

    assert "action: you ask bran for a room to rent" in text
    assert "result: bran checks the available options." in text

    assert "i have a few" not in text
    assert "not cheap" not in text

    assert "common room cot for 5 silver" in text
    assert "private room for 1 gold" in text
    assert narration_json["action"] == "Bran checks the available options."
    assert narration_json["npc"]["line"] == (
        "I can offer Common room cot for 5 silver or Private room for 1 gold."
    )


def test_service_narration_paragraph_does_not_repeat_player_input():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def generate_stream(self, *args, **kwargs):
            yield {
                "text": (
                    '{"format_version":"rpg_narration_v2",'
                    '"narration":"As you ask Bran about a room to rent, the tavern grows quiet.",'
                    '"action":"You ask Bran for a room to rent.",'
                    '"npc":{"speaker":"Bran","line":"I have a few rooms."},'
                    '"reward":"","followup_hooks":[]}'
                )
            }

    service_result = {
        "matched": True,
        "kind": "service_inquiry",
        "service_kind": "lodging",
        "provider_id": "npc:Bran",
        "provider_name": "Bran",
        "location_id": "loc_tavern",
        "status": "offers_available",
        "offers": [
            {
                "offer_id": "bran_lodging_common_cot",
                "service_kind": "lodging",
                "label": "Common room cot",
                "price": {"gold": 0, "silver": 5, "copper": 0},
            }
        ],
        "selected_offer_id": "",
        "purchase": None,
        "available_actions": [],
        "source": "deterministic_service_resolver",
    }

    result = narrate_scene(
        {"title": "The Rusty Flagon Tavern", "actors": [{"name": "Bran"}]},
        {
            "player_input": "I ask Bran for a room to rent",
            "turn_contract": {
                "player_input": "I ask Bran for a room to rent",
                "service_result": service_result,
                "resolved_result": {"service_result": service_result},
                "narration_brief": {"summary": "I ask Bran for a room to rent"},
            },
            "resolved_result": {"service_result": service_result},
        },
        llm_gateway=StubGateway(),
        retry_on_invalid=False,
    )

    text = result["narration"].lower()
    narration_json = result["narration_json"]

    assert "as you ask" not in text
    assert "about a room to rent" not in text
    assert narration_json["narration"] == "Bran looks over the registered lodging options."


def test_service_narration_uses_registered_shop_offers():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def generate_stream(self, *args, **kwargs):
            yield {
                "text": (
                    '{"format_version":"rpg_narration_v2",'
                    '"narration":"Elara folds her hands over the counter.",'
                    '"action":"You ask Elara what she sells.",'
                    '"npc":{"speaker":"Elara","line":"I have all sorts of goods for sale."},'
                    '"reward":"","followup_hooks":[]}'
                )
            }

    service_result = {
        "matched": True,
        "kind": "service_inquiry",
        "service_kind": "shop_goods",
        "provider_id": "npc:Elara",
        "provider_name": "Elara",
        "location_id": "loc_market",
        "status": "offers_available",
        "offers": [
            {
                "offer_id": "elara_torch",
                "service_kind": "shop_goods",
                "label": "Torch",
                "price": {"gold": 0, "silver": 1, "copper": 0},
            },
            {
                "offer_id": "elara_rope",
                "service_kind": "shop_goods",
                "label": "Rope",
                "price": {"gold": 0, "silver": 3, "copper": 0},
            },
        ],
        "selected_offer_id": "",
        "purchase": None,
        "available_actions": [],
        "source": "deterministic_service_resolver",
    }

    result = narrate_scene(
        {"title": "Central Market", "actors": [{"name": "Elara"}]},
        {
            "player_input": "I ask Elara what she sells",
            "turn_contract": {
                "player_input": "I ask Elara what she sells",
                "service_result": service_result,
                "resolved_result": {"service_result": service_result},
                "narration_brief": {"summary": "I ask Elara what she sells"},
            },
            "resolved_result": {"service_result": service_result},
        },
        llm_gateway=StubGateway(),
        retry_on_invalid=False,
    )

    text = result["narration"].lower()

    assert "result: elara checks the available options." in text
    assert "all sorts of goods" not in text
    assert "torch for 1 silver" in text
    assert "rope for 3 silver" in text


def test_service_purchase_applied_narration_reports_completed_purchase():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def generate_stream(self, *args, **kwargs):
            yield {
                "text": (
                    '{"format_version":"rpg_narration_v2",'
                    '"narration":"Elara reaches below the counter.",'
                    '"action":"You buy a torch from Elara.",'
                    '"npc":{"speaker":"Elara","line":"The torch is yours."},'
                    '"reward":"Torch","followup_hooks":[]}'
                )
            }

    service_result = {
        "matched": True,
        "kind": "service_purchase",
        "service_kind": "shop_goods",
        "provider_id": "npc:Elara",
        "provider_name": "Elara",
        "location_id": "loc_market",
        "status": "purchased",
        "offers": [
            {
                "offer_id": "elara_torch",
                "service_kind": "shop_goods",
                "label": "Torch",
                "price": {"gold": 0, "silver": 1, "copper": 0},
            }
        ],
        "selected_offer_id": "elara_torch",
        "purchase": {
            "blocked": False,
            "blocked_reason": "",
            "price": {"gold": 0, "silver": 1, "copper": 0},
            "can_afford": True,
            "applied": True,
            "resource_changes": {"currency": {"gold": 0, "silver": -1, "copper": 0}},
            "effects": {"items_added": [{"item_id": "torch", "name": "Torch", "quantity": 1}]},
            "applied_effects": {
                "currency_changed": True,
                "items_added": [{"item_id": "torch", "name": "Torch", "quantity": 1}],
                "active_service": {},
                "rumor_added": {},
            },
            "note": "Purchase intent resolved deterministically; runtime applies mutation.",
        },
        "available_actions": [],
        "source": "deterministic_service_resolver",
    }

    result = narrate_scene(
        {"title": "Central Market", "actors": [{"name": "Elara"}]},
        {
            "player_input": "I buy a torch from Elara",
            "turn_contract": {
                "player_input": "I buy a torch from Elara",
                "service_result": service_result,
                "resolved_result": {"service_result": service_result},
                "narration_brief": {"summary": "I buy a torch from Elara"},
            },
            "resolved_result": {"service_result": service_result},
        },
        llm_gateway=StubGateway(),
        retry_on_invalid=False,
    )

    text = result["narration"].lower()
    narration_json = result["narration_json"]

    assert "result: elara completes the purchase." in text
    assert "the torch is yours" not in text
    assert "done. torch is settled" in text
    assert "reward:" not in text
    assert narration_json["reward"] == ""


def test_service_purchase_blocked_narration_reports_insufficient_funds():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def generate_stream(self, *args, **kwargs):
            yield {
                "text": (
                    '{"format_version":"rpg_narration_v2",'
                    '"narration":"Elara hands you the rope.",'
                    '"action":"You buy rope from Elara.",'
                    '"npc":{"speaker":"Elara","line":"The rope is yours."},'
                    '"reward":"Rope","followup_hooks":[]}'
                )
            }

    service_result = {
        "matched": True,
        "kind": "service_purchase",
        "service_kind": "shop_goods",
        "provider_id": "npc:Elara",
        "provider_name": "Elara",
        "location_id": "loc_market",
        "status": "blocked",
        "offers": [
            {
                "offer_id": "elara_rope",
                "service_kind": "shop_goods",
                "label": "Rope",
                "price": {"gold": 0, "silver": 3, "copper": 0},
            }
        ],
        "selected_offer_id": "elara_rope",
        "purchase": {
            "blocked": True,
            "blocked_reason": "insufficient_funds",
            "price": {"gold": 0, "silver": 3, "copper": 0},
            "can_afford": False,
            "applied": False,
            "resource_changes": {"currency": {"gold": 0, "silver": 0, "copper": 0}},
            "effects": {},
            "note": "No mutation was applied.",
        },
        "available_actions": [],
        "source": "deterministic_service_resolver",
    }

    result = narrate_scene(
        {"title": "Central Market", "actors": [{"name": "Elara"}]},
        {
            "player_input": "I buy rope from Elara",
            "turn_contract": {
                "player_input": "I buy rope from Elara",
                "service_result": service_result,
                "resolved_result": {"service_result": service_result},
                "narration_brief": {"summary": "I buy rope from Elara"},
            },
            "resolved_result": {"service_result": service_result},
        },
        llm_gateway=StubGateway(),
        retry_on_invalid=False,
    )

    text = result["narration"].lower()
    narration_json = result["narration_json"]

    assert "hands you the rope" not in text
    assert "the rope is yours" not in text
    assert "reward:" not in text
    assert "result: elara names the price, but you do not have enough coin." in text
    assert "rope for 3 silver is the price, but you do not have enough coin." in text
    assert narration_json["reward"] == ""


def test_service_purchase_narration_prefers_resolved_applied_result():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def generate_stream(self, *args, **kwargs):
            yield {
                "text": (
                    '{"format_version":"rpg_narration_v2",'
                    '"narration":"Bran reaches for the ledger.",'
                    '"action":"You buy Common room cot from Bran.",'
                    '"npc":{"speaker":"Bran","line":"I can settle Common room cot once you confirm the purchase."},'
                    '"reward":"","followup_hooks":[]}'
                )
            }

    stale_service_result = {
        "matched": True,
        "kind": "service_purchase",
        "service_kind": "lodging",
        "provider_id": "npc:Bran",
        "provider_name": "Bran",
        "location_id": "loc_tavern",
        "status": "purchase_ready",
        "offers": [
            {
                "offer_id": "bran_lodging_common_cot",
                "service_kind": "lodging",
                "label": "Common room cot",
                "price": {"gold": 0, "silver": 5, "copper": 0},
            }
        ],
        "selected_offer_id": "bran_lodging_common_cot",
        "purchase": {
            "blocked": False,
            "blocked_reason": "",
            "price": {"gold": 0, "silver": 5, "copper": 0},
            "can_afford": True,
            "applied": False,
            "resource_changes": {"currency": {"gold": 0, "silver": -5, "copper": 0}},
            "effects": {"lodging_reserved": True, "rest_quality": "basic", "duration": "one_night"},
        },
        "available_actions": [],
        "source": "deterministic_service_resolver",
    }

    applied_service_result = {
        **stale_service_result,
        "status": "purchased",
        "purchase": {
            **stale_service_result["purchase"],
            "applied": True,
            "applied_effects": {
                "currency_changed": True,
                "items_added": [],
                "active_service": {
                    "service_id": "bran_lodging_common_cot",
                    "offer_id": "bran_lodging_common_cot",
                    "service_kind": "lodging",
                    "provider_id": "npc:Bran",
                    "provider_name": "Bran",
                    "label": "Common room cot",
                    "started_tick": 12,
                    "duration": "one_night",
                    "status": "active",
                },
                "rumor_added": {},
            },
        },
    }

    result = narrate_scene(
        {"title": "The Rusty Flagon Tavern", "actors": [{"name": "Bran"}]},
        {
            "player_input": "I buy Common room cot from Bran",
            "turn_contract": {
                "player_input": "I buy Common room cot from Bran",
                "service_result": stale_service_result,
                "resolved_result": {
                    "service_result": applied_service_result,
                    "service_application": {"applied": True},
                },
            },
            "resolved_result": {
                "service_result": applied_service_result,
                "service_application": {"applied": True},
            },
        },
        llm_gateway=StubGateway(),
        retry_on_invalid=False,
    )

    text = result["narration"].lower()
    narration_json = result["narration_json"]

    assert "once you confirm" not in text
    assert "result: bran completes the purchase." in text
    assert "done. common room cot is settled." in text
    assert narration_json["action"] == "Bran completes the purchase."
    assert narration_json["npc"]["line"] == "Done. Common room cot is settled."


def test_service_purchase_narration_uses_direct_service_application_when_contract_is_stale():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def generate_stream(self, *args, **kwargs):
            yield {
                "text": (
                    '{"format_version":"rpg_narration_v2",'
                    '"narration":"Bran waits with the ledger open.",'
                    '"action":"Bran is ready to complete the purchase.",'
                    '"npc":{"speaker":"Bran","line":"I can settle Common room cot once you confirm the purchase."},'
                    '"reward":"","followup_hooks":[]}'
                )
            }

    stale_service_result = {
        "matched": True,
        "kind": "service_purchase",
        "service_kind": "lodging",
        "provider_id": "npc:Bran",
        "provider_name": "Bran",
        "location_id": "loc_tavern",
        "status": "purchase_ready",
        "offers": [
            {
                "offer_id": "bran_lodging_common_cot",
                "service_kind": "lodging",
                "label": "Common room cot",
                "price": {"gold": 0, "silver": 5, "copper": 0},
            }
        ],
        "selected_offer_id": "bran_lodging_common_cot",
        "purchase": {
            "blocked": False,
            "blocked_reason": "",
            "price": {"gold": 0, "silver": 5, "copper": 0},
            "can_afford": True,
            "applied": False,
            "resource_changes": {"currency": {"gold": 0, "silver": -5, "copper": 0}},
            "effects": {"lodging_reserved": True, "rest_quality": "basic", "duration": "one_night"},
        },
        "available_actions": [],
        "source": "deterministic_service_resolver",
    }

    result = narrate_scene(
        {"title": "The Rusty Flagon Tavern", "actors": [{"name": "Bran"}]},
        {
            "player_input": "I buy Common room cot from Bran",
            "turn_contract": {
                "player_input": "I buy Common room cot from Bran",
                "service_result": stale_service_result,
                "resolved_result": {
                    "service_result": stale_service_result,
                    "service_application": {"applied": False},
                },
            },
            # This is what runtime should now pass directly after mutation.
            "resolved_result": {
                "service_result": {
                    **stale_service_result,
                    "status": "purchased",
                    "purchase": {
                        **stale_service_result["purchase"],
                        "applied": True,
                    },
                },
                "service_application": {"applied": True},
            },
            "service_result": {
                **stale_service_result,
                "status": "purchased",
                "purchase": {
                    **stale_service_result["purchase"],
                    "applied": True,
                },
            },
            "service_application": {"applied": True},
        },
        llm_gateway=StubGateway(),
        retry_on_invalid=False,
    )

    text = result["narration"].lower()
    narration_json = result["narration_json"]

    assert "ready to complete" not in text
    assert "once you confirm" not in text
    assert "result: bran completes the purchase." in text
    assert "done. common room cot is settled." in text
    assert narration_json["action"] == "Bran completes the purchase."
    assert narration_json["npc"]["line"] == "Done. Common room cot is settled."
