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
        from app.apps.rpg.rules.combat.campaign_mechanics import instantiate_campaign_creature

        wolf = instantiate_campaign_creature(load_session_from_postgres(session_id)["simulation_state"], "Echo Wolf")
        assert wolf and wolf["name"] == "Echo Wolf"  # its creatures fight as themselves
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
        # Every turn counts, the dialogue turn too; the hero keeps their name and their experience meter.
        assert arrived["turn_count"] == 3 and stored["manifest"]["turn_count"] == 3
        # The world's own people and places are authored: meeting them writes no new dossier. And the narrative
        # engine writes the prose, so no model draft of the turn's narration is made only to be replaced.
        assert "canon_dossier" not in model.calls, model.calls
        assert "narration_candidates" not in model.calls, model.calls
        assert stored["simulation_state"]["player_state"]["name"] == "Wren"
        assert arrived["player"]["xp"]["max"] == stored["simulation_state"]["player_state"]["xp_to_next"]

        text = json.dumps(load_session_from_postgres(session_id))
        for starter in ("Rusty Flagon", "loc_tavern", "Bran the Innkeeper", "Captain Aldric", "Elara the Merchant"):
            assert starter not in text, starter
    finally:
        job_store.reset_default_job_store_factory_for_tests()


def test_item_actions_and_story_turns_share_one_inventory(tmp_path, monkeypatch) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.jobs import store as job_store
    from app.persistence.startup import bootstrap_postgresql_runtime
    from app.platform.chat.persistence.job_store import PostgresJobStoreAdapter
    from app.providers import service as provider_service
    from app.apps.rpg.edge.api.feature_routes.rpg_session_routes import register_rpg_session_routes
    from app.apps.rpg.narration.narrative_engine import service as narrative_service
    from app.apps.rpg.narration.narrative_engine.writer import StructuredNarrativeWriter
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

        def sheet() -> tuple[dict, list]:
            player = client.get(f"/api/rpg/sessions/{session_id}").json()["session"]["state"]["player"]
            for item in player["inventory"]:
                assert "quantity" in item and "qty" not in item, item
            return {item["name"]: item["quantity"] for item in player["inventory"]}, player.get("equipment") or []

        def act(action: str, item: str) -> dict:
            response = client.post(f"/api/rpg/sessions/{session_id}/loadout-action", json={"action": action, "item_name": item})
            assert response.status_code == 200, response.text[:300]
            return response.json()

        def turn(command: str) -> None:
            assert client.post(f"/api/rpg/sessions/{session_id}/turn", json={"command": command}).status_code == 200

        assert sheet()[0]["Lantern Bread"] == 2
        act("drop", "Lantern Bread")
        assert sheet()[0]["Lantern Bread"] == 1
        turn("look around")
        # A story turn keeps what the item action did, in the player sheet's own shape.
        items, _ = sheet()
        assert items["Lantern Bread"] == 1 and items["Gateborn Compass"] == 1
        used = act("use", "Lantern Bread")
        assert used["consumed"] is True
        assert "Lantern Bread" not in sheet()[0]
        # "useful" is not "use": searching consumes nothing.
        turn("Search the area for useful supplies I can pick up")
        items, _ = sheet()
        assert "Lantern Bread" not in items and items["Gateborn Compass"] == 1
        act("equip", "Gateborn Compass")
        turn("look around")
        items, equipment = sheet()
        assert "Gateborn Compass" in {row["name"] for row in equipment}
        assert items["Gateborn Compass"] == 1
    finally:
        job_store.reset_default_job_store_factory_for_tests()


def test_world_mechanics_change_real_state(tmp_path, monkeypatch) -> None:
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
    told: list[str] = []
    beat_kinds: list[list[str]] = []

    def narrate(payload):
        beat_kinds.append([str(beat.get("kind") or "") for beat in payload.get("beats") or ()])
        # What the narrator is told for each turn: the evidence its beats may use.
        told.append(" ".join(str(record.get("content") or "") for beat in payload.get("beats") or ()
                             for record in beat.get("approved_evidence") or ()))
        return _scripted_narrative(payload)

    monkeypatch.setattr(
        narrative_service,
        "_production_writer",
        lambda: StructuredNarrativeWriter(narrate, provider="scripted", model="scripted"),
    )
    try:
        session_id = _launch_aurelia(tmp_path, monkeypatch)
        app = FastAPI()
        include_router_registrar(app, register_rpg_session_routes)
        client = TestClient(app, base_url="http://127.0.0.1", headers={"X-Omnix-Client": "test"})

        def turn(command: str) -> None:
            response = client.post(f"/api/rpg/sessions/{session_id}/turn", json={"command": command})
            assert response.status_code == 200, response.text[:500]

        def stored() -> dict:
            return load_session_from_postgres(session_id)

        def public() -> dict:
            return client.get(f"/api/rpg/sessions/{session_id}").json()["session"]["state"]

        def quests() -> dict:
            return {quest["title"]: quest for quest in public()["quests"]}

        def copper(purse: dict) -> int:
            return int(purse.get("gold") or 0) * 100 + int(purse.get("silver") or 0) * 10 + int(purse.get("copper") or 0)

        # Asking a companion to join changes the party.
        turn("I ask Liora Fen to join my party as a companion.")
        party = stored()["simulation_state"]["player_state"]["party_state"]["companions"]
        assert [companion["npc_id"] for companion in party] == ["npc:liora-fen"]
        assert public()["turn_count"] == 1  # the companion's turn ends early, and still counts
        assert stored()["simulation_state"]["survival"]["hunger"] == 1  # and time passes on it

        # Taking on a quest makes it active.
        assert quests()["Voices in the Phone"]["status"] == "available"
        turn("I accept the quest Voices in the Phone.")
        assert quests()["Voices in the Phone"]["status"] == "active"

        # Practising a skill earns its experience, on the sheet too.
        turn("Practice swordsmanship with a careful training drill.")
        assert stored()["simulation_state"]["player_state"]["skills"]["swordsmanship"]["xp"] == 10
        assert public()["player"]["skills"]["swordsmanship"]["xp"] == 10

        # Reaching a place the quest names advances it.
        assert quests()["First Night in Aurelia"]["visited_locations"] == ["location:aurelia:arrival-grove"]
        turn("go to Starfall Village")
        # Arriving, the narrator is told what the place is like, from the world's own description of it.
        village = stored()["simulation_state"]["world_model"]["locations"]["location:aurelia:starfall-village"]
        assert village["description"] and village["description"] in told[-1]
        first_night = quests()["First Night in Aurelia"]
        assert first_night["status"] == "active"
        assert "location:aurelia:starfall-village" in first_night["visited_locations"]

        # Time passes: needs rise.
        turn("wait")
        hungry = stored()["simulation_state"]["survival"]
        assert hungry["enabled"] is True and hungry["hunger"] > 0 and hungry["thirst"] > 0

        # Asking someone present a question is one short model call for their line, not the full narrative writer.
        calls, writes = len(model.calls), len(told)
        turn("I ask Orik Stonewake what he thinks of the newcomers.")
        assert model.calls[calls:] == ["turn_narration"] and len(told) == writes, model.calls[calls:]

        # A meal at the inn costs coin and eases hunger.
        purse = public()["player"]["currency"]
        turn("I buy a meal from Orik Stonewake.")
        assert copper(public()["player"]["currency"]) < copper(purse)
        assert stored()["simulation_state"]["survival"]["hunger"] < hungry["hunger"]
        assert public()["turn_count"] == 7
        # The narrator is told what the turns did, so it cannot invent otherwise.
        assert any("You take on the quest Voices in the Phone" in text for text in told)
        assert any("Your practice earns 10 experience in swordsmanship" in text for text in told)
        assert "for A hot meal" in told[-1] and "It eases your hunger." in told[-1]
        # A shop sells this world's goods: the item is in the pack and every copy of the purse agrees, on later
        # turns too. Asking for something general names what is on offer and sells nothing.
        turn("I buy a Healing Potion from Brindle Gearwing.")
        purse = public()["player"]["currency"]
        turn("I buy supplies from Brindle Gearwing.")
        assert "Brindle Gearwing offers:" in told[-1] and "Healing Potion" in told[-1], told[-1]
        state = stored()["simulation_state"]["player_state"]
        assert public()["player"]["currency"] == purse == state["currency"] == state["inventory_state"]["currency"]
        assert "Healing Potion" in [item["name"] for item in state["inventory_state"]["items"]]
        assert "Healing Potion" in [item["name"] for item in public()["player"]["inventory"]]

        # A shopkeeper buys what the player carries, and the narrator is told the price.
        before = copper(public()["player"]["currency"])
        turn("I sell my Iron Dagger to Brindle Gearwing.")
        assert "You sell the Iron Dagger to Brindle Gearwing for 5 copper." in told[-1], told[-1]
        assert copper(public()["player"]["currency"]) == before + 5
        assert "Iron Dagger" not in [item["name"] for item in public()["player"]["inventory"]]

        # What is put down lies where it was dropped, and picking it up returns it to its own stack.
        def bread() -> list:
            return [item["quantity"] for item in public()["player"]["inventory"] if item["name"] == "Lantern Bread"]

        carried = bread()
        turn("I drop one Lantern Bread on the ground.")
        assert bread() == [carried[0] - 1] or (carried == [1] and bread() == [])
        assert "You put down the Lantern Bread" in told[-1]
        turn("I pick up the Lantern Bread.")
        assert bread() == carried

        # Renting a room is a purchase; sleeping in it is resting, and it eases fatigue.
        before = copper(public()["player"]["currency"])
        turn("I rent a room for the night from Orik Stonewake.")
        assert copper(public()["player"]["currency"]) == before - 50
        tired = stored()["simulation_state"]["survival"]["fatigue"]
        assert tired > 0  # paying for the room rests no one
        turn("I go to my room and sleep for the night.")
        assert stored()["simulation_state"]["survival"]["fatigue"] < tired
        assert "rest" in told[-1] and "lodging" in told[-1], told[-1]

        # Every one of these commands is understood by the game itself: none asked the model what it meant.
        assert "semantic_intent" not in model.calls and "dialogue" not in model.calls, model.calls

        # A fight goes blow by blow: the creature takes its turns, the narrator is told every blow, the
        # sheet shows the wounds, and the rest of the turn (time passing) is kept.
        hunger, calls = stored()["simulation_state"]["survival"]["hunger"], len(model.calls)
        turn("I attack the Echo Wolf.")
        assert "The fight begins: you against the Echo Wolf." in told[-1], told[-1]
        combat = stored()["simulation_state"]["combat_state"]
        assert combat["active"] is True and combat["current_actor_id"] == "player"
        turn("I attack the Echo Wolf.")
        assert "You hit the Echo Wolf" in told[-1] or "You miss the Echo Wolf" in told[-1], told[-1]
        assert "dialogue" not in beat_kinds[-1], beat_kinds[-1]  # a fight is not a conversation
        hero = stored()["simulation_state"]["combat_state"]["participants"]["player"]
        assert public()["player"]["resources"]["hp"]["current"] == hero["hp"]
        assert stored()["simulation_state"]["survival"]["hunger"] > hunger
        # Fleeing is the combat rules' too: the turn is counted and the session's own combat stays out of it.
        count = public()["turn_count"]
        turn("I flee from the Echo Wolf.")
        assert "You break away from the Echo Wolf" in told[-1] or "cuts you off" in told[-1], told[-1]
        assert public()["turn_count"] == count + 1
        assert not (stored()["runtime_state"].get("combat_state") or {}).get("active")
        # The combat rules decide a blow at a creature and the narrator alone tells it: no other model call.
        assert model.calls[calls:] == [], model.calls[calls:]
    finally:
        job_store.reset_default_job_store_factory_for_tests()
