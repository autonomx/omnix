"""A campaign launched from a published world plays in that world (PostgreSQL, scripted model).

Aurelia is imported, adopted and launched from its "Gateborn: First Light" opening, then played through the
turn route with a scripted model: the campaign starts at the opening's place with its people, kit, purse and
quests, talks to the people who are there, and travels along the world's own routes.
"""
from __future__ import annotations

import importlib.util
import json
import os
import uuid
from pathlib import Path

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

_AURELIA = Path(__file__).resolve().parents[3] / "resources/examples/rpg/world-bundles/aurelia-echoes-beyond-the-gate"


def _aurelia_bundle() -> bytes:
    spec = importlib.util.spec_from_file_location("aurelia_materialize", _AURELIA / "materialize.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._build_bundle(_AURELIA)


class _ScriptedModel:
    """Answers each model call by its contract; the dialogue call names the first present NPC."""

    name = "scripted"
    provider_id = "scripted"

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.present: list[list[str]] = []

    def chat_completion(self, messages, model=None, stream=False, **kwargs):
        from app.providers.base import ChatResponse

        text = "\n".join(str(getattr(message, "content", "")) for message in messages)
        kind, answer = "unscripted", "{}"
        if "decide which one present NPC" in text:
            present = json.loads(text.rsplit("CONTEXT: ", 1)[1]).get("present_npcs") or []
            self.present.append([str(npc.get("name")) for npc in present])
            kind = "dialogue"
            answer = json.dumps({"speaker_id": present[0]["id"] if present else "", "line": "Welcome, traveler."})
        elif "rpg_narration_candidates_v1" in text:
            kind = "narration_candidates"
            narration = {"format_version": "rpg_narration_v2", "narration": "The moment passes.", "action": "You take it in.",
                         "npc": {"speaker": "", "line": ""}, "reward": None, "followup_hooks": []}
            answer = json.dumps({"format_version": "rpg_narration_candidates_v1", "primary": narration, "safe_fallback": narration})
        elif "materializes durable, player-safe RPG canon" in text:
            kind, answer = "canon_dossier", json.dumps({"entities": [], "documents": [], "facts": [], "relationships": []})
        elif "first-call semantic intent router" in text:
            kind = "semantic_intent"
        elif "CONTEXT:" in text:
            kind, answer = "turn_narration", "The moment passes."
        self.calls.append(kind)
        response = ChatResponse(content=answer, model="scripted")
        return iter([response]) if stream else response

    def supports_streaming(self) -> bool:
        return False

    def get_capabilities(self) -> list:
        return []


def _scripted_narrative(payload):
    blocks = []
    for beat in payload.get("beats") or []:
        text = next(
            (str(record.get("text") or record.get("summary") or "").strip()
             for record in beat.get("approved_evidence") or []
             if str(record.get("text") or record.get("summary") or "").strip()),
            "",
        )
        blocks.append({"beat_id": beat["beat_id"], "sequence": beat["sequence"], "kind": beat["kind"],
                       "purpose": beat["purpose"], "speaker_id": beat.get("speaker_id") or "",
                       "text": text or "You take in your surroundings."})
    return {"blocks": blocks}


def _launch_aurelia(tmp_path, monkeypatch) -> str:
    from app.apps.rpg.edge.api.feature_routes.rpg_world_library_routes import SESSION_CAMPAIGN_SESSIONS
    from app.apps.rpg.genesis.worlds.published_launch import launch_published_scenario
    from app.apps.rpg.genesis.worlds.world_adoption import adopt_shared_world
    from app.apps.rpg.genesis.worlds.world_bundle_import import import_world_bundle

    monkeypatch.setenv("OMNIX_RESOURCES_DIR", str(tmp_path))
    world_id = f"world:aurelia-play-{uuid.uuid4().hex[:10]}"
    imported = import_world_bundle(_aurelia_bundle(), target_world_id=world_id)
    adopt_shared_world(world_id, bundle_sha256=imported["bundle_sha256"])
    with unit_of_work() as work:
        context = current_tenant()
        scenario = next(
            row for row in work.world_library.iter_scenarios(context, world_id=world_id)
            if "gateborn" in str(row["id"])
        )
        document = dict(work.world_library.list_scenario_revisions(context, str(scenario["id"]))[0]["document"])
        work.rollback()
    launched = launch_published_scenario(
        sessions=SESSION_CAMPAIGN_SESSIONS,
        world_id=world_id,
        world_revision=int(document["world_revision"]),
        world_release=int(document["compatible_release"]),
        scenario_id=str(document["scenario_id"]),
        scenario_revision=int(document["revision"]),
        player={"name": "Wren", "pronouns": "they/them"},
        features={"llm_narration": True, "image_generation": False},
    )
    return str(launched["session_id"])


def test_published_world_campaign_plays_in_its_world(tmp_path, monkeypatch) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.jobs import store as job_store
    from app.persistence.startup import bootstrap_postgresql_runtime
    from app.platform.chat.persistence.job_store import PostgresJobStoreAdapter
    from app.providers import service as provider_service
    from app.apps.rpg.edge.api.feature_routes.rpg_session_routes import register_rpg_session_routes
    from app.apps.rpg.narration.narrative_engine import service as narrative_service
    from app.apps.rpg.narration.narrative_engine.writer import StructuredNarrativeWriter
    from app.apps.rpg.session.persistence.session_records import load_session_from_postgres
    from tests.support.routers import include_router_registrar

    bootstrap_postgresql_runtime()
    jobs = PostgresJobStoreAdapter()
    job_store.install_default_job_store_factory(lambda: jobs)
    model = _ScriptedModel()
    monkeypatch.setattr(provider_service, "get_provider", lambda *args, **kwargs: model)
    monkeypatch.setattr(
        narrative_service,
        "_production_writer",
        lambda: StructuredNarrativeWriter(_scripted_narrative, provider="scripted", model="scripted"),
    )
    try:
        session_id = _launch_aurelia(tmp_path, monkeypatch)
        app = FastAPI()
        include_router_registrar(app, register_rpg_session_routes)
        client = TestClient(app, base_url="http://127.0.0.1", headers={"X-Omnix-Client": "test"})

        def public() -> dict:
            return client.get(f"/api/rpg/sessions/{session_id}").json()["session"]["state"]

        def turn(command: str) -> dict:
            response = client.post(f"/api/rpg/sessions/{session_id}/turn", json={"command": command})
            assert response.status_code == 200, response.text[:500]
            return response.json()

        # The opening: Aurelia's place, region, weather, kit, purse and quests, not the starter town's.
        opening = public()
        assert opening["current_location_name"] == "Starfall Grove"
        assert opening["title"] == "Wren — Starfall Grove"
        display = opening["environment_snapshot"]["display"]
        assert display["region"] == "Starfall March"
        assert display["weather"] and display["weather"] != "Unknown"
        inventory = {item["name"]: item.get("quantity") or item.get("qty") for item in opening["player"]["inventory"]}
        assert inventory["Gateborn Compass"] == 1 and inventory["Lantern Bread"] == 2
        assert "Trail Rations" not in inventory
        assert opening["player"]["currency"] == {"gold": 0, "silver": 12, "copper": 40}
        quests = {quest["title"]: quest["status"] for quest in opening["quests"]}
        assert quests["First Night in Aurelia"] == "active"
        assert "Talk to Liora Fen" in opening["quick_actions"]

        # The people at the grove are Aurelia's, from the very first turn: Liora answers.
        talk = turn("I greet Liora Fen and ask her where I am")
        speakers = [block.get("speaker_id") for block in talk["canonical_narrative_response"]["blocks"]]
        assert "npc:liora-fen" in speakers

        turn("look around")

        # Travel follows the world's own route, and what the player sees follows the player.
        turn("go to Starfall Village")
        stored = load_session_from_postgres(session_id)
        assert stored["simulation_state"]["player_state"]["location_id"] == "location:aurelia:starfall-village"
        # The village's people are here now, and Liora stayed at the grove.
        present = stored["runtime_state"]["current_scene"]["present_npc_ids"]
        assert "npc:orik-stonewake" in present and "npc:liora-fen" not in present
        assert stored["simulation_state"]["present_npc_state"]["present_npc_ids"] == present
        arrived = public()
        assert arrived["current_location_name"] == "Starfall Village"
        assert arrived["title"] == "Wren — Starfall Village"
        assert arrived["environment_snapshot"]["display"]["region"] == "Starfall March"

        text = json.dumps(load_session_from_postgres(session_id))
        for starter in ("Rusty Flagon", "loc_tavern", "Bran the Innkeeper", "Captain Aldric", "Elara the Merchant"):
            assert starter not in text, starter
    finally:
        job_store.reset_default_job_store_factory_for_tests()
