"""Contract tests for replay/persistence platform wrappers."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient


SRC_DIR = Path(__file__).resolve().parents[3]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def test_rpg_replay_adapter_state_hash_is_deterministic() -> None:
    from app.replay import RpgReplayPersistenceAdapter

    adapter = RpgReplayPersistenceAdapter()

    left = adapter.state_hash({"b": [2, 1], "a": {"z": 1}})
    right = adapter.state_hash({"a": {"z": 1}, "b": [2, 1]})

    assert left.hash == right.hash
    assert left.format_version == "rpg_replay_persistence_adapter_v1"


def test_rpg_replay_adapter_checkpoint_roundtrip() -> None:
    from app.replay import RpgReplayPersistenceAdapter

    adapter = RpgReplayPersistenceAdapter()
    bundle = {"turn_index": 3, "state_versions": {"inventory": "v1"}, "values": ["a", "b"]}

    envelope = adapter.create_checkpoint(bundle, checkpoint_id="checkpoint:test")
    restored = adapter.restore_checkpoint(
        {
            "version": envelope.version,
            "source": envelope.source,
            "checkpoint_id": envelope.checkpoint_id,
            "bundle_checksum": envelope.checksum,
            "bundle": envelope.payload,
            "state_versions": envelope.metadata["state_versions"],
        }
    )

    assert envelope.checkpoint_id == "checkpoint:test"
    assert restored == bundle


def test_gateway_replay_endpoints_expose_rpg_wrappers() -> None:
    from app.gateway.main import create_gateway_app

    client = TestClient(create_gateway_app(), raise_server_exceptions=False)

    primitives = client.get("/api/replay/primitives")
    assert primitives.status_code == 200
    kinds = {item["kind"] for item in primitives.json()["primitives"]}
    assert {"provider_recording", "state_hash", "checkpoint", "session_persistence"} <= kinds

    state_hash = client.post("/api/replay/state-hash", json={"state": {"x": 1}})
    assert state_hash.status_code == 200
    assert len(state_hash.json()["hash"]) == 64

    checkpoint = client.post("/api/replay/checkpoints", json={"turn_index": 1, "state_versions": {}})
    assert checkpoint.status_code == 200
    assert checkpoint.json()["source"] == "interactive_cli_state_checkpoint"


def test_gateway_replay_inventory_can_be_injected() -> None:
    from app.gateway.main import create_gateway_app
    from app.replay import PersistenceInventory, RpgReplayPersistenceAdapter

    class FakeReplayAdapter(RpgReplayPersistenceAdapter):
        def list_sessions(self) -> PersistenceInventory:
            return PersistenceInventory(
                sessions=[{"session_id": "session-1", "title": "Saved", "archived": False}],
                diagnostics=[],
            )

    client = TestClient(
        create_gateway_app(replay_adapter_factory=lambda: FakeReplayAdapter()),
        raise_server_exceptions=False,
    )

    response = client.get("/api/replay/persistence/inventory")

    assert response.status_code == 200
    assert response.json()["sessions"] == [{"session_id": "session-1", "title": "Saved", "archived": False}]
