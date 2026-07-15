from __future__ import annotations

from copy import deepcopy

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.rpg_session_routes import register_rpg_session_routes
from app.rpg.dialogue_quality_benchmark import (
    build_deterministic_benchmark_response,
    default_dialogue_benchmark_cases,
)
from app.rpg.local_dialogue_quality_fixtures import (
    LOCAL_DIALOGUE_FIXTURE_VERSION,
    apply_local_dialogue_fixture,
    dialogue_benchmark_case,
)
from app.rpg.local_dialogue_quality_smoke import run_local_dialogue_quality_smoke


def _template_session() -> dict:
    return {
        "manifest": {"id": "fixture", "session_id": "fixture", "title": "Template"},
        "state": {"player": {"name": "Before"}},
        "simulation_state": {
            "player_state": {"location_id": "location:tavern"},
            "scene": {"nearby_npcs": [{"npc_id": "npc:old", "name": "Old"}]},
        },
        "runtime_state": {
            "turn_history": [{"turn": 9}],
            "state_revision": 4,
            "current_scene": {
                "location_id": "location:tavern",
                "present_npc_ids": ["npc:bran"],
            },
        },
    }


def test_fixture_applies_known_case_without_mutating_template() -> None:
    case = dialogue_benchmark_case("high_trust")
    template = _template_session()
    original = deepcopy(template)

    fixture = apply_local_dialogue_fixture(template, case=case, run_id="run-1")

    assert template == original
    assert fixture["state"]["player"]["name"] == "Elara"
    assert fixture["state"]["relationship_index"]["npc:bran"] == {
        "trust": "high",
        "score": 75,
    }
    assert fixture["simulation_state"]["scene"]["present_npc_ids"] == ["npc:bran"]
    assert fixture["simulation_state"]["present_npc_state"]["location:tavern"] == ["npc:bran"]
    assert "turn_history" not in fixture["runtime_state"]
    assert fixture["runtime_state"]["local_dialogue_quality_fixture"] == {
        "fixture_version": LOCAL_DIALOGUE_FIXTURE_VERSION,
        "run_id": "run-1",
        "case_id": "high_trust",
        "category": "relationship_high_trust",
        "trust": "high",
        "present_npc_ids": ["npc:bran"],
        "recent_line_count": 0,
    }


def test_fixture_models_absent_group_and_continuity_state() -> None:
    absent = apply_local_dialogue_fixture(
        _template_session(),
        case=dialogue_benchmark_case("absent_npc"),
        run_id="run-2",
    )
    group = apply_local_dialogue_fixture(
        _template_session(),
        case=dialogue_benchmark_case("group_conversation"),
        run_id="run-2",
    )
    continuity = apply_local_dialogue_fixture(
        _template_session(),
        case=dialogue_benchmark_case("follow_up_continuity"),
        run_id="run-2",
    )

    assert absent["simulation_state"]["scene"]["present_npc_ids"] == ["npc:mira"]
    assert absent["simulation_state"]["npc_index"]["npc:bran"]["location_id"] == "location:offstage"
    assert absent["runtime_state"]["current_scene"]["present_npc_ids"] == ["npc:mira"]
    assert group["simulation_state"]["scene"]["present_npc_ids"] == ["npc:bran", "npc:mira"]
    assert len(continuity["runtime_state"]["recent_interactions"]) == 1


def test_local_smoke_resets_fixture_before_every_case_and_archives(monkeypatch) -> None:
    cases = default_dialogue_benchmark_cases()[:2]
    provisioned: list[tuple[str, str | None]] = []
    posted: list[tuple[str, str]] = []
    archived: list[str] = []

    def fake_provision(*, session_id, case, **_kwargs):
        provisioned.append((case.case_id, session_id))
        return {
            "ok": True,
            "fixture_version": LOCAL_DIALOGUE_FIXTURE_VERSION,
            "case_id": case.case_id,
            "session_id": "fixture-session",
            "created": session_id is None,
        }

    def fake_post(*, session_id, case, **_kwargs):
        posted.append((case.case_id, session_id))
        return build_deterministic_benchmark_response(case), 0.25, 512

    def fake_archive(*, session_id, **_kwargs):
        archived.append(session_id)
        return True

    monkeypatch.setattr("app.rpg.local_dialogue_quality_smoke._provision_case", fake_provision)
    monkeypatch.setattr("app.rpg.local_dialogue_quality_smoke._post_case", fake_post)
    monkeypatch.setattr("app.rpg.local_dialogue_quality_smoke._archive_fixture", fake_archive)

    report = run_local_dialogue_quality_smoke(
        base_url="http://127.0.0.1:8000",
        cases=cases,
        env={"OMNIX_RPG_LIVE_SMOKE": "1"},
    )

    assert report["ok"] is True
    assert provisioned == [(cases[0].case_id, None), (cases[1].case_id, None)]
    assert posted == [(cases[0].case_id, "fixture-session"), (cases[1].case_id, "fixture-session")]
    assert archived == ["fixture-session"]
    assert report["fixture_archived"] is True
    assert report["fixture_mode"] == "known_case_isolated_sessions"
    assert report["fixture_session_ids"] == ["fixture-session"]
    assert [row["fixture"]["case_id"] for row in report["results"]] == [
        cases[0].case_id,
        cases[1].case_id,
    ]


def test_fixture_route_requires_loopback_opt_in(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.rpg.local_dialogue_quality_fixtures.provision_local_dialogue_fixture",
        lambda **kwargs: {
            "ok": True,
            "case_id": kwargs["case"].case_id,
            "run_id": kwargs["run_id"],
            "session_id": "fixture-session",
        },
    )
    app = FastAPI()
    register_rpg_session_routes(app)
    client = TestClient(app)
    payload = {"case_id": "business", "run_id": "run-3"}

    denied = client.post("/api/rpg/local-qualification/dialogue-fixture", json=payload)
    allowed = client.post(
        "/api/rpg/local-qualification/dialogue-fixture",
        json=payload,
        headers={"X-Omnix-Rpg-Live-Smoke": "1"},
    )

    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json()["session_id"] == "fixture-session"
