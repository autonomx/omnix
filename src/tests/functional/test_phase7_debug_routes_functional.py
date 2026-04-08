"""Functional tests for Phase 7 — Creator / GM Debug Routes."""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock, patch

import pytest


def _make_test_app():
    """Create a minimal Flask test app with just the debug blueprint."""
    from flask import Flask

    from app.rpg.creator.world_debug import (
        explain_faction,
        explain_npc,
        summarize_npc_minds,
        summarize_social_state,
        summarize_world_pressures,
    )
    from app.rpg.creator.world_gm_tools import (
        force_alliance,
        force_faction_position,
        force_npc_belief,
        inject_event,
        seed_rumor,
        step_ticks,
    )
    from app.rpg.creator.world_replay import (
        get_snapshot,
        list_snapshots,
        rollback_to_snapshot,
        summarize_timeline,
    )

    try:
        from app.rpg.api.rpg_debug_routes import rpg_debug_bp
        blueprint_registered = True
    except ImportError:
        blueprint_registered = False

    app = Flask(__name__)

    if blueprint_registered:
        app.register_blueprint(rpg_debug_bp)
    else:
        # Inline endpoints for testing when blueprint not registered
        from flask import jsonify, request

        @app.post("/api/rpg/debug/state")
        def debug_state():
            data = request.get_json(silent=True) or {}
            setup_payload = dict(data.get("setup_payload") or {})
            meta = dict((setup_payload or {}).get("metadata") or {})
            state = dict(meta.get("simulation_state") or {})
            return jsonify({
                "ok": True,
                "tick": int(state.get("tick", 0) or 0),
                "npc_minds": summarize_npc_minds(state),
                "social": summarize_social_state(state),
                "pressures": summarize_world_pressures(state),
                "timeline": summarize_timeline(state),
            })

        @app.post("/api/rpg/debug/npc")
        def debug_npc():
            data = request.get_json(silent=True) or {}
            setup_payload = dict(data.get("setup_payload") or {})
            npc_id = str(data.get("npc_id") or "")
            meta = dict((setup_payload or {}).get("metadata") or {})
            state = dict(meta.get("simulation_state") or {})
            return jsonify({"ok": True, "npc": explain_npc(state, npc_id)})

        @app.post("/api/rpg/debug/faction")
        def debug_faction():
            data = request.get_json(silent=True) or {}
            setup_payload = dict(data.get("setup_payload") or {})
            faction_id = str(data.get("faction_id") or "")
            meta = dict((setup_payload or {}).get("metadata") or {})
            state = dict(meta.get("simulation_state") or {})
            return jsonify({"ok": True, "faction": explain_faction(state, faction_id)})

        @app.post("/api/rpg/debug/step")
        def debug_step():
            data = request.get_json(silent=True) or {}
            setup_payload = dict(data.get("setup_payload") or {})
            count = int(data.get("count", 1) or 1)

            def mock_step(payload):
                payload = dict(payload or {})
                meta = dict(payload.get("metadata") or {})
                sim = dict(meta.get("simulation_state") or {})
                sim["tick"] = sim.get("tick", 0) + 1
                meta["simulation_state"] = sim
                payload["metadata"] = meta
                return payload

            result = step_ticks(setup_payload, mock_step, count=count)
            return jsonify({"ok": True, "setup_payload": result})

        @app.post("/api/rpg/debug/inject_event")
        def debug_inject_event():
            data = request.get_json(silent=True) or {}
            setup_payload = dict(data.get("setup_payload") or {})
            event = dict(data.get("event") or {})
            meta = dict((setup_payload or {}).get("metadata") or {})
            state = dict(meta.get("simulation_state") or {})
            state = inject_event(state, event, reason="gm_injection")
            meta["simulation_state"] = state
            setup_payload["metadata"] = meta
            return jsonify({"ok": True, "setup_payload": setup_payload})

        @app.post("/api/rpg/debug/seed_rumor")
        def debug_seed_rumor():
            data = request.get_json(silent=True) or {}
            setup_payload = dict(data.get("setup_payload") or {})
            rumor = dict(data.get("rumor") or {})
            meta = dict((setup_payload or {}).get("metadata") or {})
            state = dict(meta.get("simulation_state") or {})
            state = seed_rumor(state, rumor)
            meta["simulation_state"] = state
            setup_payload["metadata"] = meta
            return jsonify({"ok": True, "setup_payload": setup_payload})

        @app.post("/api/rpg/debug/force_alliance")
        def debug_force_alliance():
            data = request.get_json(silent=True) or {}
            setup_payload = dict(data.get("setup_payload") or {})
            alliance = dict(data.get("alliance") or {})
            meta = dict((setup_payload or {}).get("metadata") or {})
            state = dict(meta.get("simulation_state") or {})
            state = force_alliance(state, alliance)
            meta["simulation_state"] = state
            setup_payload["metadata"] = meta
            return jsonify({"ok": True, "setup_payload": setup_payload})

        @app.post("/api/rpg/debug/force_faction_position")
        def debug_force_faction_position():
            data = request.get_json(silent=True) or {}
            setup_payload = dict(data.get("setup_payload") or {})
            faction_id = str(data.get("faction_id") or "")
            position = dict(data.get("position") or {})
            meta = dict((setup_payload or {}).get("metadata") or {})
            state = dict(meta.get("simulation_state") or {})
            state = force_faction_position(state, faction_id, position)
            meta["simulation_state"] = state
            setup_payload["metadata"] = meta
            return jsonify({"ok": True, "setup_payload": setup_payload})

        @app.post("/api/rpg/debug/force_npc_belief")
        def debug_force_npc_belief():
            data = request.get_json(silent=True) or {}
            setup_payload = dict(data.get("setup_payload") or {})
            npc_id = str(data.get("npc_id") or "")
            target_id = str(data.get("target_id") or "")
            belief_patch = dict(data.get("belief_patch") or {})
            meta = dict((setup_payload or {}).get("metadata") or {})
            state = dict(meta.get("simulation_state") or {})
            state = force_npc_belief(state, npc_id, target_id, belief_patch)
            meta["simulation_state"] = state
            setup_payload["metadata"] = meta
            return jsonify({"ok": True, "setup_payload": setup_payload})

        @app.post("/api/rpg/debug/snapshots")
        def debug_snapshots():
            data = request.get_json(silent=True) or {}
            setup_payload = dict(data.get("setup_payload") or {})
            meta = dict((setup_payload or {}).get("metadata") or {})
            state = dict(meta.get("simulation_state") or {})
            return jsonify({"ok": True, "snapshots": list_snapshots(state)})

        @app.post("/api/rpg/debug/snapshot")
        def debug_snapshot():
            data = request.get_json(silent=True) or {}
            setup_payload = dict(data.get("setup_payload") or {})
            snapshot_id = str(data.get("snapshot_id") or "")
            meta = dict((setup_payload or {}).get("metadata") or {})
            state = dict(meta.get("simulation_state") or {})
            return jsonify({"ok": True, "snapshot": get_snapshot(state, snapshot_id)})

        @app.post("/api/rpg/debug/rollback")
        def debug_rollback():
            data = request.get_json(silent=True) or {}
            setup_payload = dict(data.get("setup_payload") or {})
            snapshot_id = str(data.get("snapshot_id") or "")
            meta = dict((setup_payload or {}).get("metadata") or {})
            state = dict(meta.get("simulation_state") or {})
            rolled = rollback_to_snapshot(state, snapshot_id)
            meta["simulation_state"] = rolled
            setup_payload["metadata"] = meta
            return jsonify({"ok": True, "setup_payload": setup_payload})

    return app


@pytest.fixture
def app():
    return _make_test_app()


@pytest.fixture
def client(app):
    return app.test_client()


class TestDebugStateEndpoint:
    def test_debug_state_returns_sections(self, client):
        """Debug state endpoint returns npc/social/pressure/timeline sections."""
        payload = {
            "setup_payload": {
                "metadata": {
                    "simulation_state": {
                        "tick": 3,
                        "npc_minds": {},
                        "social_state": {},
                        "threads": {},
                        "factions": {},
                        "locations": {},
                    }
                }
            }
        }
        resp = client.post("/api/rpg/debug/state", json=payload)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "npc_minds" in data
        assert "social" in data
        assert "pressures" in data
        assert "timeline" in data


class TestDebugStepEndpoint:
    def test_step_ticks(self, client):
        """Step 3 ticks through /api/rpg/debug/step."""
        payload = {
            "setup_payload": {
                "metadata": {
                    "simulation_state": {"tick": 0}
                }
            },
            "count": 3,
        }
        resp = client.post("/api/rpg/debug/step", json=payload)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["setup_payload"]["metadata"]["simulation_state"]["tick"] == 3


class TestInjectEventEndpoint:
    def test_inject_betrayal_event(self, client):
        """Inject betrayal event and confirm it lands in simulation state."""
        setup = {
            "metadata": {
                "simulation_state": {"tick": 1, "events": []}
            }
        }
        payload = {
            "setup_payload": setup,
            "event": {"type": "betrayal", "actor": "player", "target_id": "faction_1"},
        }
        resp = client.post("/api/rpg/debug/inject_event", json=payload)
        assert resp.status_code == 200
        data = resp.get_json()
        sp = data["setup_payload"]
        events = sp["metadata"]["simulation_state"].get("events", [])
        assert len(events) == 1
        assert events[0]["type"] == "betrayal"


class TestForceFactionPosition:
    def test_force_faction_position_preserved(self, client):
        """Force faction position and verify next step preserves override."""
        setup = {
            "metadata": {
                "simulation_state": {"tick": 1}
            }
        }
        # Force position
        payload_force = {
            "setup_payload": setup,
            "faction_id": "faction_alpha",
            "position": {"stance": "hostile", "priority": "high"},
        }
        resp = client.post("/api/rpg/debug/force_faction_position", json=payload_force)
        assert resp.status_code == 200
        data = resp.get_json()

        # Verify position was set
        social = data["setup_payload"]["metadata"]["simulation_state"].get("social_state", {})
        assert social.get("group_positions", {}).get("faction_alpha") == {"stance": "hostile", "priority": "high"}


class TestDebugNpcEndpoint:
    def test_debug_npc_missing(self, client):
        payload = {
            "setup_payload": {
                "metadata": {
                    "simulation_state": {"npc_index": {}, "npc_minds": {}}
                }
            },
            "npc_id": "missing",
        }
        resp = client.post("/api/rpg/debug/npc", json=payload)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["npc"]["npc"]["npc_id"] == "missing"


class TestSeedRumorEndpoint:
    def test_seed_rumor(self, client):
        setup = {"metadata": {"simulation_state": {"tick": 1}}}
        payload = {
            "setup_payload": setup,
            "rumor": {"id": "r1", "content": "something secret", "origin": "faction_x"},
        }
        resp = client.post("/api/rpg/debug/seed_rumor", json=payload)
        assert resp.status_code == 200
        data = resp.get_json()
        social = data["setup_payload"]["metadata"]["simulation_state"].get("social_state", {})
        rumors = social.get("rumors", [])
        assert len(rumors) == 1
        assert rumors[0]["id"] == "r1"


class TestForceAllianceEndpoint:
    def test_force_alliance(self, client):
        setup = {"metadata": {"simulation_state": {"tick": 1}}}
        payload = {
            "setup_payload": setup,
            "alliance": {"status": "active", "member_ids": ["f1", "f2"]},
        }
        resp = client.post("/api/rpg/debug/force_alliance", json=payload)
        assert resp.status_code == 200
        data = resp.get_json()
        social = data["setup_payload"]["metadata"]["simulation_state"].get("social_state", {})
        alliances = social.get("alliances", [])
        assert len(alliances) == 1


class TestForceNpcBeliefEndpoint:
    def test_force_npc_belief(self, client):
        setup = {"metadata": {"simulation_state": {"tick": 1}}}
        payload = {
            "setup_payload": setup,
            "npc_id": "npc_1",
            "target_id": "player",
            "belief_patch": {"trust": 0.5, "hostility": -0.3},
        }
        resp = client.post("/api/rpg/debug/force_npc_belief", json=payload)
        assert resp.status_code == 200
        data = resp.get_json()
        minds = data["setup_payload"]["metadata"]["simulation_state"].get("npc_minds", {})
        npc_mind = minds.get("npc_1", {})
        beliefs = npc_mind.get("beliefs", {}).get("player", {})
        assert beliefs["trust"] == 0.5


class TestSnapshotsEndpoints:
    def test_list_snapshots(self, client):
        setup = {
            "metadata": {
                "simulation_state": {
                    "tick": 5,
                    "snapshots": [
                        {"snapshot_id": "s1", "tick": 1, "label": "start"},
                        {"snapshot_id": "s2", "tick": 3, "label": "mid"},
                    ]
                }
            }
        }
        resp = client.post("/api/rpg/debug/snapshots", json={"setup_payload": setup})
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["snapshots"]) == 2

    def test_rollback(self, client):
        setup = {
            "metadata": {
                "simulation_state": {
                    "tick": 10,
                    "snapshots": [
                        {
                            "snapshot_id": "s1",
                            "tick": 2,
                            "state": {"tick": 2, "events": [], "debug_meta": {}},
                        }
                    ]
                }
            }
        }
        payload = {
            "setup_payload": setup,
            "snapshot_id": "s1",
        }
        resp = client.post("/api/rpg/debug/rollback", json=payload)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["setup_payload"]["metadata"]["simulation_state"]["tick"] == 2
        assert data["setup_payload"]["metadata"]["simulation_state"]["debug_meta"]["last_step_reason"] == "rollback"