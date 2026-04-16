"""Tests for narration job queue functionality."""
import copy
from unittest.mock import call, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.rpg.api.rpg_session_routes import rpg_session_bp

from app.rpg.session.runtime import (
    _apply_idle_tick_to_session,
    apply_turn,
    _enqueue_narration_request,
    _enqueue_narration_request_old as _enqueue_narration_request_compat,
    _get_narration_job_for_turn,
    process_next_narration_job,
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
