from tests.rpg.autoplay.turn_runtime import (
    _discover_fastapi_apps,
    _run_turn_via_fastapi_route,
    _run_turn_via_live_http_route,
    bootstrap_live_http_session,
    describe_turn_runtime_candidates,
    extract_narration,
    extract_turn_contract,
    normalize_turn_result,
    probe_live_http_health,
    run_real_rpg_turn,
)


def test_extract_turn_contract_from_result():
    result = {"turn_contract": {"action": "observe"}}

    assert extract_turn_contract(result)["action"] == "observe"


def test_extract_narration_from_result():
    result = {"narration": "You look around."}

    assert extract_narration(result) == "You look around."


def test_normalize_turn_result_keeps_state_contract_and_narration():
    state = {"x": 1}
    result = {
        "ok": True,
        "simulation_state": {"x": 2},
        "turn_contract": {"action": "observe"},
        "narration": "You look around.",
    }

    normalized = normalize_turn_result(result, fallback_state=state, runtime_name="test")

    assert normalized["ok"] is True
    assert normalized["runtime_name"] == "test"
    assert normalized["simulation_state"] == {"x": 2}
    assert normalized["turn_contract"]["action"] == "observe"
    assert normalized["narration"] == "You look around."


def test_describe_turn_runtime_candidates_returns_list():
    candidates = describe_turn_runtime_candidates()

    assert isinstance(candidates, list)


def test_run_turn_via_fastapi_route_with_fake_app(monkeypatch):
    from fastapi import FastAPI

    app = FastAPI()

    @app.post("/api/rpg/session/turn")
    def fake_turn(payload: dict):
        return {
            "ok": True,
            "simulation_state": {"advanced": True},
            "turn_contract": {"player_action": payload.get("input")},
            "narration": "The real route advanced.",
        }

    monkeypatch.setattr(
        "tests.rpg.autoplay.turn_runtime._discover_fastapi_apps",
        lambda: [("fake.app", app)],
    )
    monkeypatch.setattr(
        "tests.rpg.autoplay.turn_runtime._install_autoplay_session",
        lambda **kwargs: ["fake_session_seeded"],
    )

    result = _run_turn_via_fastapi_route(
        simulation_state={},
        session_id="s",
        player_input="I observe.",
        turn_index=1,
    )

    assert result["ok"] is True
    assert result["runtime_name"] == "fake.app POST /api/rpg/session/turn"
    assert result["simulation_state"] == {"advanced": True}
    assert result["turn_contract"]["player_action"] == "I observe."
    assert result["narration"] == "The real route advanced."


def test_discover_fastapi_apps_supports_factory_module(monkeypatch):
    import types

    from fastapi import FastAPI

    module = types.ModuleType("fake_factory_app")

    def create_app():
        app = FastAPI()

        @app.post("/api/rpg/session/turn")
        def fake_turn(payload: dict):
            return {"ok": True}

        return app

    module.create_app = create_app
    monkeypatch.setitem(__import__("sys").modules, "fake_factory_app", module)
    monkeypatch.setattr(
        "tests.rpg.autoplay.turn_runtime._iter_app_module_names",
        lambda: ["fake_factory_app"],
    )

    apps = _discover_fastapi_apps()

    assert apps
    assert apps[0][0] == "fake_factory_app.create_app()"


def test_run_turn_via_live_http_route_with_mocked_requests(monkeypatch):
    get_call_count = 0

    class GetResponse:
        status_code = 200
        text = '{"ok": true}'

    class PostResponse:
        status_code = 200
        text = '{"ok": true}'

        def json(self):
            return {
                "ok": True,
                "simulation_state": {"advanced": True},
                "turn_contract": {"player_action": "I observe."},
                "narration": "The live route advanced.",
            }

    class Requests:
        @staticmethod
        def get(url, timeout):
            return GetResponse()

        @staticmethod
        def post(url, json, timeout):
            return PostResponse()

    monkeypatch.setitem(__import__("sys").modules, "requests", Requests)

    result = _run_turn_via_live_http_route(
        simulation_state={},
        session_id="s",
        player_input="I observe.",
        turn_index=1,
        base_url="http://testserver",
    )

    assert result["ok"] is True
    assert result["runtime_name"] == "HTTP POST http://testserver/api/rpg/session/turn"


def test_probe_live_http_health_with_mocked_requests(monkeypatch):
    class Response:
        status_code = 200
        text = '{"ok": true}'

    class Requests:
        @staticmethod
        def get(url, timeout):
            return Response()

    monkeypatch.setitem(__import__("sys").modules, "requests", Requests)

    result = probe_live_http_health("http://testserver")

    assert result["ok"] is True
    assert result["url"] == "http://testserver/api/health"


def test_bootstrap_live_http_session_with_mocked_requests(monkeypatch):
    class Response:
        status_code = 200
        text = '{"ok": true}'

    class Requests:
        @staticmethod
        def post(url, json, timeout):
            return Response()

    monkeypatch.setitem(__import__("sys").modules, "requests", Requests)

    result = bootstrap_live_http_session(
        session_id="s",
        simulation_state={"x": 1},
        base_url="http://testserver",
    )

    assert result["ok"] is True
    assert result["url"] == "http://testserver/api/rpg/session/create"


def test_run_real_rpg_turn_accepts_base_url_for_http_fallback(monkeypatch):
    monkeypatch.setattr(
        "tests.rpg.autoplay.turn_runtime._candidate_callables",
        lambda: [],
    )
    monkeypatch.setattr(
        "tests.rpg.autoplay.turn_runtime._run_turn_via_fastapi_route",
        lambda **kwargs: {"ok": False, "reason": "no_app"},
    )
    monkeypatch.setattr(
        "tests.rpg.autoplay.turn_runtime._run_turn_via_live_http_route",
        lambda **kwargs: {
            "ok": True,
            "runtime_name": f"HTTP POST {kwargs['base_url'].rstrip('/')}/api/rpg/session/turn",
            "simulation_state": {"advanced": True},
            "turn_contract": {"player_action": kwargs["player_input"]},
            "narration": "Advanced through HTTP.",
        },
    )

    result = run_real_rpg_turn(
        simulation_state={},
        session_id="s",
        player_input="I observe.",
        turn_index=1,
        base_url="http://testserver",
    )

    assert result["ok"] is True
    assert result["runtime_name"] == "HTTP POST http://testserver/api/rpg/session/turn"
    assert result["simulation_state"] == {"advanced": True}