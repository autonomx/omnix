"""A campaign carried to another Omnix (RQ-8.6; PostgreSQL, scripted model).

An Aurelia campaign is played a little, exported, and taken out of the library; importing the file brings it back
under its own id, with its world, its bible, its local map and its narrations, and it plays on. A second import is
refused while it is in the library, and so is one whose world is not installed.
"""
from __future__ import annotations

import os

import pytest

from app.persistence.unit_of_work import unit_of_work
from app.runtime.tenant_context import current_tenant

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("OMNIX_TEST_DATABASE_URL"),
        reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
    ),
]


def _remove(session_id: str) -> None:
    """Take the campaign out of this library, as on another machine it never was."""
    with unit_of_work() as work:
        context = current_tenant()
        for table in ("omnix_rpg_narrative_retirement_records", "omnix_rpg_narrative_deliveries",
                      "omnix_rpg_narrative_responses"):
            work.connection.execute(f"DELETE FROM {table} WHERE workspace_id = %s AND response_id IN ("
                                    "SELECT response_id FROM omnix_rpg_narrative_responses "
                                    "WHERE workspace_id = %s AND campaign_id = %s)",
                                    (context.workspace_id, context.workspace_id, session_id))
        work.connection.execute("DELETE FROM omnix_rpg_campaigns WHERE workspace_id = %s AND id = %s",
                                (context.workspace_id, session_id))
        work.commit()


def test_a_campaign_exported_from_one_omnix_plays_on_in_another(tmp_path, monkeypatch) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.apps.rpg.edge.api.feature_routes.rpg_session_routes import register_rpg_session_routes
    from app.apps.rpg.narration.narrative_engine import service as narrative_service
    from app.apps.rpg.narration.narrative_engine.writer import StructuredNarrativeWriter
    from app.jobs import store as job_store
    from app.persistence.startup import bootstrap_postgresql_runtime
    from app.platform.chat.persistence.job_store import PostgresJobStoreAdapter
    from app.providers import service as provider_service
    from tests.characterization.test_rpg_production_turn import _scripted_narrative
    from tests.persistence.test_rpg_published_world_play_integration import _launch_aurelia, _ScriptedModel
    from tests.support.routers import include_router_registrar

    bootstrap_postgresql_runtime()
    jobs = PostgresJobStoreAdapter()
    job_store.install_default_job_store_factory(lambda: jobs)
    model = _ScriptedModel()
    monkeypatch.setattr(provider_service, "get_provider", lambda *args, **kwargs: model)
    monkeypatch.setattr(narrative_service, "_production_writer",
                        lambda: StructuredNarrativeWriter(_scripted_narrative, provider="scripted", model="scripted"))
    try:
        session_id = _launch_aurelia(tmp_path, monkeypatch)
        app = FastAPI()
        include_router_registrar(app, register_rpg_session_routes)
        client = TestClient(app, base_url="http://127.0.0.1", headers={"X-Omnix-Client": "test"})

        def turn(command: str) -> dict:
            response = client.post(f"/api/rpg/sessions/{session_id}/turn", json={"command": command})
            assert response.status_code == 200, response.text[:500]
            return response.json()

        turn("look around")
        turn("wait a while")
        before = client.get(f"/api/rpg/sessions/{session_id}").json()["session"]

        exported = client.get(f"/api/rpg/sessions/{session_id}/export")
        assert exported.status_code == 200
        assert exported.headers["content-disposition"].endswith('.omnix-campaign.json"')
        package = exported.json()
        transfer = package["transfer"]
        assert transfer["world_binding"]["world_id"].startswith("world:aurelia-play-")
        assert transfer["campaign_bible"] and transfer["map_instances"] and transfer["narrative_responses"]

        refused = client.post("/api/rpg/sessions/import", json=package)
        assert refused.status_code == 409 and refused.json()["detail"]["error"] == "rpg_campaign_already_in_library"

        _remove(session_id)
        assert client.get(f"/api/rpg/sessions/{session_id}").status_code == 404
        imported = client.post("/api/rpg/sessions/import", json=package)
        assert imported.status_code == 200, imported.text[:500]
        after = client.get(f"/api/rpg/sessions/{session_id}").json()["session"]
        for key in ("current_location_name", "title", "turn_count"):
            assert after["state"].get(key) == before["state"].get(key), key
        def told(session: dict) -> list:
            rows = (session.get("runtime_state") or {}).get("recent_interactions") or []
            return [(row.get("interaction_id"), (row.get("visible_response") or {}).get("plain_text")) for row in rows]

        assert told(after) == told(before) and any(text for _, text in told(after))  # the narrations came with it

        played = turn("look around")  # and it plays on, in its world, on its local map
        assert played.get("ok") is not False

        unbound = {**package, "transfer": {**transfer, "world_binding": {
            **transfer["world_binding"], "world_id": "world:not-here"}}}
        _remove(session_id)
        missing = client.post("/api/rpg/sessions/import", json=unbound)
        assert missing.status_code == 409
        assert missing.json()["detail"] == {"ok": False, "error": "rpg_campaign_world_not_installed",
                                            "subject": "world:not-here",
                                            "message": "Its world is not installed here: import the world first."}
        garbled = client.post("/api/rpg/sessions/import", json={"package_type": "something else"})
        assert garbled.status_code == 422
        assert client.get(f"/api/rpg/sessions/{session_id}").status_code == 404  # nothing was written
    finally:
        job_store.reset_default_job_store_factory_for_tests()
