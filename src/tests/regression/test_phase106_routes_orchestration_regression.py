"""Phase 10.6 — Regression tests for route-level orchestration payload."""
from app import create_app


def test_phase106_scene_route_includes_orchestration_payload():
    app = create_app()
    client = app.test_client()

    response = client.post(
        "/api/rpg/presentation/scene",
        json={
            "setup_payload": {
                "simulation_state": {
                    "player_state": {
                        "actor_id": "player:hero",
                        "name": "Hero",
                    },
                    "orchestration_state": {
                        "llm": {
                            "provider_mode": "disabled",
                            "request_counter": 0,
                            "active_requests": [],
                            "completed_requests": [],
                            "last_error": {},
                        }
                    },
                }
            },
            "scene_state": {},
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert "orchestration" in payload["presentation"]
    assert payload["presentation"]["orchestration"]["llm_orchestration"]["provider_mode"] == "disabled"