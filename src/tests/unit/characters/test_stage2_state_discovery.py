from __future__ import annotations

from typing import Any

from app.characters.stage2_contracts import Stage2PrepareConfig, marker_memory
from app.characters.stage2_discovery import discover_stage2_cleanup

from test_stage2_preflight import FakeStage2Gateway


class DiscoverableStage2Gateway(FakeStage2Gateway):
    def list_sessions(self) -> dict[str, Any]:
        return {"sessions": [dict(item) for item in self.sessions.values()]}


def _config() -> Stage2PrepareConfig:
    return Stage2PrepareConfig(
        base_url="http://test",
        provider_id="lmstudio",
        model_id="test-model",
        settle_seconds=0,
    )


def _seed(gateway: DiscoverableStage2Gateway) -> dict[str, Any]:
    config = _config()
    gateway.create_character({"id": "stage2-maya", "display_name": "Maya Stage 2"})
    gateway.create_character({"id": "stage2-alex", "display_name": "Alex Stage 2"})
    maya_setup = gateway.create_session(
        {
            "title": "Stage 2 Maya controlled memory setup",
            "interaction_mode": "character",
            "character_id": "stage2-maya",
            "read_memory": False,
            "write_memory": True,
            "shared_memory_access": "none",
        }
    )
    alex_setup = gateway.create_session(
        {
            "title": "Stage 2 Alex controlled memory setup",
            "interaction_mode": "character",
            "character_id": "stage2-alex",
            "read_memory": False,
            "write_memory": True,
            "shared_memory_access": "none",
        }
    )
    system_setup = gateway.create_session(
        {
            "title": "Stage 2 System Assistant memory fixture",
            "interaction_mode": "system",
            "read_memory": False,
            "write_memory": False,
            "shared_memory_access": "none",
        }
    )
    maya = gateway.create_memory(
        {
            "session_id": maya_setup["id"],
            "scope": "global",
            "category": "relationship",
            "content": marker_memory(config.run_id, "maya"),
            "pinned": True,
        }
    )
    alex = gateway.create_memory(
        {
            "session_id": alex_setup["id"],
            "scope": "global",
            "category": "relationship",
            "content": marker_memory(config.run_id, "alex"),
            "pinned": True,
        }
    )
    system = gateway.create_memory(
        {
            "session_id": system_setup["id"],
            "scope": "global",
            "category": "relationship",
            "content": marker_memory(config.run_id, "system"),
            "pinned": True,
        }
    )
    maya_pilot = gateway.create_session(
        {
            "title": "Stage 2 Maya read-only memory pilot",
            "interaction_mode": "character",
            "character_id": "stage2-maya",
            "read_memory": True,
            "write_memory": False,
            "shared_memory_access": "none",
        }
    )
    alex_control = gateway.create_session(
        {
            "title": "Stage 2 Alex read-only isolation control",
            "interaction_mode": "character",
            "character_id": "stage2-alex",
            "read_memory": True,
            "write_memory": False,
            "shared_memory_access": "none",
        }
    )
    return {
        "maya_setup": maya_setup,
        "alex_setup": alex_setup,
        "system_setup": system_setup,
        "maya_pilot": maya_pilot,
        "alex_control": alex_control,
        "maya": maya,
        "alex": alex,
        "system": system,
    }


def _purge_maya(gateway: DiscoverableStage2Gateway, seeded: dict[str, Any]) -> None:
    gateway.memories[seeded["maya"]["id"]]["status"] = "forgotten"
    for snapshot in gateway.snapshots.values():
        snapshot["items"] = [
            item
            for item in snapshot["items"]
            if item["memory_record_id"] != seeded["maya"]["id"]
        ]
        snapshot["active_count"] = len(snapshot["items"])
        snapshot["invalidated_count"] = 0


def test_discover_cleanup_dry_run_performs_no_mutation() -> None:
    gateway = DiscoverableStage2Gateway()
    seeded = _seed(gateway)

    report = discover_stage2_cleanup(gateway, _config())

    assert report.decision == "needs_review"
    assert gateway.memories[seeded["alex"]["id"]]["status"] == "active"
    assert gateway.deleted_sessions == []
    assert next(item for item in report.checks if item.id == "cleanup.plan").status == "review"


def test_discover_cleanup_apply_completes_pending_cleanup() -> None:
    gateway = DiscoverableStage2Gateway()
    seeded = _seed(gateway)

    report = discover_stage2_cleanup(gateway, _config(), apply=True)

    assert report.decision == "pass"
    assert gateway.memories[seeded["maya"]["id"]]["status"] == "forgotten"
    assert gateway.memories[seeded["alex"]["id"]]["status"] == "forgotten"
    assert gateway.memories[seeded["system"]["id"]]["status"] == "forgotten"
    assert seeded["maya_pilot"]["id"] in gateway.sessions
    assert len(gateway.deleted_sessions) == 4


def test_discover_cleanup_apply_completes_observed_partial_cleanup() -> None:
    gateway = DiscoverableStage2Gateway()
    seeded = _seed(gateway)
    _purge_maya(gateway, seeded)

    report = discover_stage2_cleanup(gateway, _config(), apply=True)

    assert report.decision == "pass"
    assert gateway.memories[seeded["alex"]["id"]]["status"] == "forgotten"
    assert gateway.memories[seeded["system"]["id"]]["status"] == "forgotten"
    assert len(gateway.deleted_sessions) == 4


def test_discover_cleanup_is_idempotent_after_sessions_removed() -> None:
    gateway = DiscoverableStage2Gateway()
    _seed(gateway)
    first = discover_stage2_cleanup(gateway, _config(), apply=True)

    second = discover_stage2_cleanup(gateway, _config(), apply=True)

    assert first.decision == "pass"
    assert second.decision == "pass"
    assert next(item for item in second.checks if item.id == "cleanup.idempotent").status == "pass"


def test_duplicate_session_title_blocks_discovery() -> None:
    gateway = DiscoverableStage2Gateway()
    _seed(gateway)
    gateway.create_session(
        {
            "title": "Stage 2 Maya read-only memory pilot",
            "interaction_mode": "character",
            "character_id": "stage2-maya",
            "read_memory": True,
            "write_memory": False,
            "shared_memory_access": "none",
        }
    )

    report = discover_stage2_cleanup(gateway, _config(), apply=True)

    assert report.decision == "blocked"
    assert "duplicate Stage 2 session title" in report.checks[0].summary


def test_duplicate_marker_record_blocks_discovery() -> None:
    gateway = DiscoverableStage2Gateway()
    seeded = _seed(gateway)
    gateway.create_memory(
        {
            "session_id": seeded["alex_setup"]["id"],
            "scope": "global",
            "category": "relationship",
            "content": marker_memory(_config().run_id, "alex"),
            "pinned": True,
        }
    )

    report = discover_stage2_cleanup(gateway, _config(), apply=True)

    assert report.decision == "blocked"
    assert "duplicate active Stage 2 fixture memories" in report.checks[0].summary


def test_wrong_owner_marker_blocks_discovery() -> None:
    gateway = DiscoverableStage2Gateway()
    seeded = _seed(gateway)
    gateway.memories[seeded["alex"]["id"]]["owner_id"] = "stage2-maya"

    report = discover_stage2_cleanup(gateway, _config(), apply=True)

    assert report.decision == "blocked"
    assert "missing active Stage 2 fixture memory for alex" in report.checks[0].summary


def test_unrelated_memory_is_preserved() -> None:
    gateway = DiscoverableStage2Gateway()
    seeded = _seed(gateway)
    unrelated = gateway.create_memory(
        {
            "session_id": seeded["alex_setup"]["id"],
            "scope": "global",
            "category": "fact",
            "content": "Unrelated active memory.",
            "pinned": False,
        }
    )

    report = discover_stage2_cleanup(gateway, _config(), apply=True)

    assert report.decision == "pass"
    assert gateway.memories[unrelated["id"]]["status"] == "active"


def test_report_contains_no_memory_content() -> None:
    gateway = DiscoverableStage2Gateway()
    _seed(gateway)

    report = discover_stage2_cleanup(gateway, _config())
    payload = report.model_dump_json()

    assert "Synthetic Stage 2 relationship marker" not in payload
    assert marker_memory(_config().run_id, "maya") not in payload
