"""Tests for narration job queue functionality."""
import json
import queue
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.rpg.api.rpg_session_routes import rpg_session_bp
from app.rpg.session.runtime import (
    _apply_idle_tick_to_session,
    _enqueue_narration_request,
    _generate_turn_narration_artifact,
    process_next_narration_job,
)


def _make_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(rpg_session_bp)
    return app


@pytest.fixture
def client():
    return TestClient(_make_test_app())


def test_service_npc_dialogue_allows_backed_prior_memory_reference():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def generate_stream(self, *args, **kwargs):
            yield {
                "text": (
                    '{"format_version":"rpg_narration_v2",'
                    '"narration":"Elara looks over the goods.",'
                    '"action":"Elara checks the available options.",'
                    '"npc":{"speaker":"Elara","line":"Still short on coin from last time, or ready to buy today?"},'
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
            "recalled_service_memories": [
                {
                    "memory_id": "memory:test",
                    "kind": "service_purchase_blocked",
                    "owner_id": "npc:Elara",
                    "owner_name": "Elara",
                    "subject_id": "player",
                    "service_kind": "shop_goods",
                    "offer_id": "elara_torch",
                    "summary": "The player tried to buy Torch from Elara without enough coin.",
                    "blocked_reason": "insufficient_funds",
                }
            ],
            "turn_contract": {
                "player_input": "I ask Elara what she sells",
                "service_result": service_result,
                "resolved_result": {"service_result": service_result},
            },
        },
        llm_gateway=StubGateway(),
        retry_on_invalid=False,
    )

    assert "still short on coin" in result["narration"].lower()
    assert result["narration_json"]["npc"]["line"] == (
        "Still short on coin from last time, or ready to buy today?"
    )

def test_service_purchase_blocked_narration_strips_meta_processed_language():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def generate_stream(self, *args, **kwargs):
            yield {
                "text": (
                    '{"format_version":"rpg_narration_v2",'
                    '"narration":"The request to purchase a torch is processed by Elara. The system confirms stock.",'
                    '"action":"Elara names the price, but you do not have enough coin.",'
                    '"npc":{"speaker":"Elara","line":"Torch for 1 silver is the price, but you do not have enough coin."},'
                    '"reward":"","followup_hooks":[]}'
                )
            }

    service_result = {
        "matched": True,
        "kind": "service_purchase",
        "service_kind": "shop_goods",
        "provider_id": "npc:Elara",
        "provider_name": "Elara",
        "status": "blocked",
        "offers": [{"offer_id": "elara_torch", "label": "Torch"}],
        "selected_offer_id": "elara_torch",
        "purchase": {
            "blocked": True,
            "blocked_reason": "insufficient_funds",
            "applied": False,
        },
    }

    result = narrate_scene(
        {"title": "Market Stall", "actors": [{"name": "Elara"}]},
        {
            "player_input": "I buy a torch from Elara",
            "service_result": service_result,
            "service_application": {"blocked": True, "blocked_reason": "insufficient_funds"},
            "turn_contract": {
                "player_input": "I buy a torch from Elara",
                "service_result": service_result,
                "resolved_result": {"service_result": service_result},
            },
        },
        llm_gateway=StubGateway(),
        retry_on_invalid=False,
    )

    text = result["narration"].lower()
    assert "the system confirms" not in text
    assert "processed by elara" not in text
    assert "current coin" in text

def test_service_purchase_blocked_result_keeps_specific_grounded_reason():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def generate_stream(self, *args, **kwargs):
            yield {
                "text": (
                    '{"format_version":"rpg_narration_v2",'
                    '"narration":"Elara checks the offer.",'
                    '"action":"The attempt fails.",'
                    '"npc":{"speaker":"Elara","line":"Torch for 1 silver is the price, but you do not have enough coin."},'
                    '"reward":"","followup_hooks":[]}'
                )
            }

    service_result = {
        "matched": True,
        "kind": "service_purchase",
        "service_kind": "shop_goods",
        "provider_id": "npc:Elara",
        "provider_name": "Elara",
        "status": "blocked",
        "selected_offer_id": "elara_torch",
        "purchase": {
            "blocked": True,
            "blocked_reason": "insufficient_funds",
            "applied": False,
        },
    }

    result = narrate_scene(
        {"title": "Market Stall", "actors": [{"name": "Elara"}]},
        {
            "player_input": "I buy a torch from Elara",
            "service_result": service_result,
            "service_application": {"blocked": True, "blocked_reason": "insufficient_funds"},
            "turn_contract": {
                "player_input": "I buy a torch from Elara",
                "service_result": service_result,
                "resolved_result": {"service_result": service_result},
            },
        },
        llm_gateway=StubGateway(),
        retry_on_invalid=False,
    )

    assert result["narration_json"]["action"] == "Elara names the price, but you do not have enough coin."
    assert "Result: Elara names the price, but you do not have enough coin." in result["narration"]

def test_non_service_narration_does_not_repeat_player_input():
    from app.rpg.ai.world_scene_narrator import narrate_scene

    class StubGateway:
        def generate_stream(self, *args, **kwargs):
            yield {
                "text": (
                    '{"format_version":"rpg_narration_v2",'
                    '"narration":"I ask Bran for directions to the market",'
                    '"action":"Bran responds.",'
                    '"npc":{"speaker":"Bran","line":"The market is east of the fountain."},'
                    '"reward":"","followup_hooks":[]}'
                )
            }

    result = narrate_scene(
        {"title": "Tavern", "actors": [{"name": "Bran"}]},
        {
            "player_input": "I ask Bran for directions to the market",
            "turn_contract": {
                "player_input": "I ask Bran for directions to the market",
                "action": {
                    "action_type": "investigate",
                    "target_name": "Bran",
                },
                "resolved_result": {
                    "outcome": "success",
                    "action_type": "investigate",
                    "target_name": "Bran",
                },
            },
            "resolved_result": {
                "outcome": "success",
                "action_type": "investigate",
                "target_name": "Bran",
            },
        },
        llm_gateway=StubGateway(),
        retry_on_invalid=False,
    )

    assert result["narration_json"]["narration"] != "I ask Bran for directions to the market"
    assert "gives the request their attention" in result["narration_json"]["narration"]

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
    assert runtime_state["session_id"] == "test_session"
    assert job1["narration_request"]["session_id"] == "test_session"
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

def test_turn_stream_uses_result_envelope_when_authoritative_envelope_missing(client):
    session_id = "test_session"

    authoritative_result = {
        "ok": True,
        "session": {
            "session_id": session_id,
            "runtime_state": {"tick": 9},
        },
        "turn_contract": {},
        "result": {
            "turn_id": "turn:9",
            "tick": 9,
            "resolved_result": {"ok": True},
            "combat_result": {},
            "xp_result": {},
            "skill_xp_result": {},
            "level_up": [],
            "skill_level_ups": [],
            "summary": "The turn resolves.",
            "presentation": {},
            "response_length": "short",
            "narration": "The turn resolves.",
            "narration_status": "queued",
        },
        "narration_request": {
            "turn_id": "turn:9",
            "tick": 9,
            "scene": {"title": "The Rusty Flagon Tavern"},
            "narration_context": {"player_input": "how do you do bran?"},
            "performance": {
                "enable_live_first_draft_stream": True,
                "enable_live_narration_llm": True,
            },
        },
    }

    artifact_result = {
        "ok": True,
        "artifact": {
            "turn_id": "turn:9",
            "tick": 9,
            "narration": "Bran nods from behind the bar.",
            "used_llm": True,
            "raw_llm_narrative": "{\"narration\":\"Bran nods.\"}",
            "narration_json": {"narration": "Bran nods."},
            "speaker_presentation": {},
            "format_warning": False,
            "artifact_type": "turn_narration",
        },
    }

    seen_request = {}

    def _fake_generate(session_id_arg, narration_request_arg, on_chunk=None):
        seen_request.update(narration_request_arg)
        return artifact_result

    with patch("app.rpg.api.rpg_session_routes._apply_turn_authoritative", return_value=authoritative_result), \
         patch("app.rpg.api.rpg_session_routes.load_runtime_session", return_value=authoritative_result["session"]), \
         patch("app.rpg.api.rpg_session_routes._generate_turn_narration_artifact", side_effect=_fake_generate):
        response = client.post("/api/rpg/session/turn/stream", json={
            "session_id": session_id,
            "input": "how do you do bran?",
        })

    assert response.status_code == 200
    body = response.text
    assert '"type": "authoritative_result"' in body
    assert '"turn_id": "turn:9"' in body
    assert '"tick": 9' in body
    assert seen_request["turn_id"] == "turn:9"
    assert seen_request["scene"]["title"] == "The Rusty Flagon Tavern"

def test_turn_stream_defaults_to_queued_narration_when_live_draft_not_explicit(client):
    session_id = "test_session"

    authoritative_result = {
        "ok": True,
        "authoritative": {
            "turn_id": "turn:6",
            "tick": 6,
            "resolved_result": {},
            "combat_result": {},
            "xp_result": {},
            "skill_xp_result": {},
            "level_up": [],
            "skill_level_ups": [],
            "summary": "Bran considers the room request.",
            "presentation": {},
            "response_length": "short",
            "deterministic_fallback_narration": "Bran names the going room rate.",
        },
        "narration_request": {
            "turn_id": "turn:6",
            "tick": 6,
            "scene": {"title": "The Rusty Flagon Tavern"},
            "narration_context": {"player_input": "how much for a room bran?"},
            "performance": {
                "enable_live_narration_llm": True,
            },
        },
    }

    mock_session = {
        "session_id": session_id,
        "runtime_state": {
            "tick": 6,
            "narration_jobs": [],
            "narration_jobs_by_turn": {},
            "narration_artifacts": [],
            "narration_artifacts_by_turn": {},
        },
    }

    with patch("app.rpg.api.rpg_session_routes._apply_turn_authoritative", return_value=authoritative_result), \
         patch("app.rpg.api.rpg_session_routes.load_runtime_session", return_value=mock_session), \
         patch("app.rpg.api.rpg_session_routes.save_runtime_session") as mock_save, \
         patch("app.rpg.api.rpg_session_routes._start_live_first_draft_thread") as mock_live_thread, \
         patch("app.rpg.api.rpg_session_routes.ensure_narration_worker_running") as mock_worker, \
         patch("app.rpg.api.rpg_session_routes.signal_narration_work") as mock_signal:
        response = client.post("/api/rpg/session/turn/stream", json={
            "session_id": session_id,
            "input": "how much for a room bran?",
        })

    assert response.status_code == 200
    body = response.text
    assert '"type": "authoritative_result"' in body
    assert '"type": "narration_job"' in body
    assert '"type": "done"' in body
    assert '"narration_status": "queued"' in body
    assert '"live_draft_streaming": false' in body
    assert '"type": "token"' not in body
    assert mock_live_thread.call_count == 0
    assert mock_save.call_count == 1
    assert mock_worker.call_count == 1
    assert mock_signal.call_count == 1
    saved_session = mock_save.call_args.args[0]
    saved_runtime_state = saved_session["runtime_state"]
    saved_job = saved_runtime_state["narration_jobs_by_turn"]["turn:6"]
    assert saved_runtime_state["session_id"] == session_id
    assert saved_job["narration_request"]["session_id"] == session_id

def test_turn_stream_times_out_live_first_draft_and_falls_back_to_queue(client):
    session_id = "test_session"

    authoritative_result = {
        "ok": True,
        "authoritative": {
            "turn_id": "turn:7",
            "tick": 7,
            "resolved_result": {},
            "combat_result": {},
            "xp_result": {},
            "skill_xp_result": {},
            "level_up": [],
            "skill_level_ups": [],
            "summary": "Bran starts to answer.",
            "presentation": {},
            "response_length": "short",
            "deterministic_fallback_narration": "Bran checks the room ledger.",
        },
        "narration_request": {
            "turn_id": "turn:7",
            "tick": 7,
            "scene": {"title": "The Rusty Flagon Tavern"},
            "narration_context": {"player_input": "how much for a room bran?"},
            "performance": {
                "enable_live_first_draft_stream": True,
                "enable_live_narration_llm": True,
                "live_first_draft_timeout_s": 0.001,
            },
        },
    }

    mock_session = {
        "session_id": session_id,
        "runtime_state": {
            "tick": 7,
            "narration_jobs": [],
            "narration_jobs_by_turn": {},
            "narration_artifacts": [],
            "narration_artifacts_by_turn": {},
        },
    }

    with patch("app.rpg.api.rpg_session_routes._apply_turn_authoritative", return_value=authoritative_result), \
         patch("app.rpg.api.rpg_session_routes.load_runtime_session", return_value=mock_session), \
         patch("app.rpg.api.rpg_session_routes.save_runtime_session") as mock_save, \
         patch("app.rpg.api.rpg_session_routes._start_live_first_draft_thread", return_value=queue.Queue()) as mock_live_thread, \
         patch("app.rpg.api.rpg_session_routes.ensure_narration_worker_running") as mock_worker, \
         patch("app.rpg.api.rpg_session_routes.signal_narration_work") as mock_signal:
        response = client.post("/api/rpg/session/turn/stream", json={
            "session_id": session_id,
            "input": "how much for a room bran?",
        })

    assert response.status_code == 200
    body = response.text
    assert '"type": "authoritative_result"' in body
    assert '"type": "live_first_draft_timeout"' in body
    assert '"type": "narration_job"' in body
    assert '"type": "done"' in body
    assert '"narration_status": "queued"' in body
    assert '"live_draft_streaming": false' in body
    assert mock_live_thread.call_count == 1
    assert mock_save.call_count == 1
    assert mock_worker.call_count == 1
    assert mock_signal.call_count == 1

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
