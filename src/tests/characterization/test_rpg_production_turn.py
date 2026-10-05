"""The production RPG turn, end to end through the turn route (characterization).

A seeded new game plays look, talk, buy, travel and wait turns through
``POST /api/rpg/sessions/{id}/turn`` against PostgreSQL. Model calls are
answered by a scripted fake keyed on each call's contract, and the narrative
engine writes through a scripted structured writer, so the golden records what
the deterministic engine does with fixed model answers: the visible response,
the interaction and simulation counters, changed domains, the session summary,
the narrative blocks and their validation, and which model calls each turn made.
"""
from __future__ import annotations

import json
import os
import re

import pytest

from tests.characterization.harness import capture

# The catalog modules this scenario characterizes (scripts/test_module.py).
MODULES = ("rpg",)

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("OMNIX_TEST_DATABASE_URL"),
        reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
    ),
]

SEED = 7
COMMANDS = ("look around", "talk to the bartender", "buy a drink", "go outside", "wait")

NARRATION = {
    "format_version": "rpg_narration_candidates_v1",
    "primary": {"format_version": "rpg_narration_v2", "narration": "The moment passes quietly in the room.",
                "action": "You take it in.", "npc": {"speaker": "", "line": ""}, "reward": None, "followup_hooks": []},
    "safe_fallback": {"format_version": "rpg_narration_v2", "narration": "The moment passes quietly.",
                      "action": "You take it in.", "npc": {"speaker": "", "line": ""}, "reward": None, "followup_hooks": []},
}
# (marker in the prompt, call kind, scripted answer)
SCRIPT = (
    ("rpg_narration_candidates_v1", "narration_candidates", json.dumps(NARRATION)),
    ("materializes durable, player-safe RPG canon", "canon_dossier",
     json.dumps({"entities": [], "documents": [], "facts": [], "relationships": []})),
    ("first-call semantic intent router", "semantic_intent", "{}"),
    ("CONTEXT:", "turn_narration", "The moment passes quietly in the room."),
)


class _ScriptedModel:
    name = "scripted"
    provider_id = "scripted"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def chat_completion(self, messages, model=None, stream=False, **kwargs):
        from app.providers.base import ChatResponse

        text = "\n".join(str(getattr(message, "content", "")) for message in messages)
        for marker, kind, answer in SCRIPT:
            if marker in text:
                break
        else:
            kind, answer = "unscripted", "{}"
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
        blocks.append({
            "beat_id": beat["beat_id"], "sequence": beat["sequence"], "kind": beat["kind"],
            "purpose": beat["purpose"], "speaker_id": beat.get("speaker_id") or "",
            "text": text or "You take in your surroundings.",
        })
    return {"blocks": blocks}


def _turn_record(body: dict, model_calls: list[str]) -> dict:
    canonical = body.get("canonical_narrative_response") or {}
    result = body.get("result") or {}
    summary = body.get("session_summary") or {}
    return {
        "ok": body.get("ok"),
        "contract_version": body.get("contract_version"),
        "interaction_id": body.get("interaction_id"),
        "turn_id": body.get("turn_id"),
        "simulation_tick": body.get("simulation_tick"),
        "visible_response": body.get("visible_response"),
        "result": {key: result.get(key) for key in ("changed_domains", "narration_status", "llm_purpose", "source")},
        "state": body.get("state"),
        "session_summary": {key: summary.get(key) for key in ("title", "location", "interaction_seq", "state_revision", "player_level")},
        "narrative": {
            "blocks": [
                {key: block.get(key) for key in ("sequence", "kind", "purpose", "speaker_id", "text")}
                for block in canonical.get("blocks") or []
            ],
            "validation": {key: (canonical.get("validation") or {}).get(key) for key in ("passed", "status")},
        },
        "model_calls": model_calls,
    }


def test_rpg_production_turns_match_golden(monkeypatch) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.chat.persistence.job_store import PostgresJobStoreAdapter
    from app.jobs import store as job_store
    from app.persistence.startup import bootstrap_postgresql_runtime
    from app.providers import service as provider_service
    from app.rpg.api.feature_routes.rpg_session_routes import register_rpg_session_routes
    from app.rpg.narrative_engine import service as narrative_service
    from app.rpg.narrative_engine.writer import StructuredNarrativeWriter
    from app.rpg.session.new_game import RpgNewGameRequest, create_new_game_session
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
        def play() -> dict:
            created = create_new_game_session(RpgNewGameRequest(seed=SEED))
            session_id = str(created["session_id"])
            app = FastAPI()
            include_router_registrar(app, register_rpg_session_routes)
            client = TestClient(app, base_url="http://127.0.0.1", headers={"X-Omnix-Client": "test"})
            turns = []
            for command in COMMANDS:
                before = len(model.calls)
                response = client.post(f"/api/rpg/sessions/{session_id}/turn", json={"command": command})
                assert response.status_code == 200, response.text[:500]
                turns.append({"command": command, **_turn_record(response.json(), model.calls[before:])})
            text = json.dumps({"status": created.get("status"), "turns": turns}, sort_keys=True)
            text = text.replace(session_id, "SESSION")
            text = re.sub(r"\b(submit|job|pipeline)[:-][0-9a-f]{32}\b", r"\1:ID", text)
            return json.loads(text)

        capture("rpg-production-turn", play)
    finally:
        job_store.reset_default_job_store_factory_for_tests()
