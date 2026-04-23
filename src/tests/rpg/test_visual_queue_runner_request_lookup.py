from __future__ import annotations


def test_load_pending_request_resolves_request(monkeypatch):
    from app.rpg.visual import queue_runner

    session = {
        "simulation_state": {
            "presentation_state": {
                "visual_state": {
                    "image_requests": [
                        {
                            "request_id": "scene:req1",
                            "kind": "scene_illustration",
                            "target_id": "scene",
                            "status": "pending",
                        }
                    ]
                }
            }
        }
    }

    monkeypatch.setattr(queue_runner, "load_runtime_session", lambda session_id: session)

    request = queue_runner._load_pending_request(
        session_id="preview_test",
        request_id="scene:req1",
    )

    assert request["request_id"] == "scene:req1"
    assert request["kind"] == "scene_illustration"


def test_load_pending_request_returns_empty_when_missing(monkeypatch):
    from app.rpg.visual import queue_runner
    monkeypatch.setattr(queue_runner, "load_runtime_session", lambda session_id: None)
    assert queue_runner._load_pending_request(session_id="preview_test", request_id="missing") == {}
