from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.rehearsal.characters.stage4_contracts import Stage4Checkpoint, Stage4Metrics, Stage4PrepareConfig
from tests.rehearsal.characters.stage4_runner import _cleanup, prepare_stage4


class _Gateway:
    def __init__(self, *characters: dict[str, Any]) -> None:
        self.characters = {item["id"]: item for item in characters}
        self.deleted_sessions: list[str] = []

    def health(self) -> dict[str, Any]:
        return {"ok": True, "status": "ready"}

    def list_characters(self) -> list[dict[str, Any]]:
        return list(self.characters.values())

    def create_character(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.characters[payload["id"]] = {**payload, "status": "active", "active_version": 1}
        return self.characters[payload["id"]]

    def create_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("the test stops at the sessions")

    def archive_character(self, character_id: str) -> dict[str, Any]:
        self.characters[character_id]["status"] = "archived"
        return {"character": self.characters[character_id]}

    def list_memory(self, session_id: str) -> dict[str, Any]:
        return {"records": []}

    def set_interaction(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {"id": session_id}

    def delete_session(self, session_id: str) -> dict[str, Any]:
        self.deleted_sessions.append(session_id)
        return {"ok": True}


def _checkpoint(character_id: str) -> Stage4Checkpoint:
    return Stage4Checkpoint(
        created_at="2026-11-03T00:00:00Z",
        base_url="http://test",
        run_id="run",
        character_id=character_id,
        shared_session_id="chat:shared",
        control_session_id="chat:control",
        system_setup_session_id="chat:setup",
        shared_segment_id="segment",
        shared_identity_hash="a" * 64,
        fixture_memory_ids={},
        prepare_checks=[],
        prepare_metrics=Stage4Metrics(),
    )


def test_cleanup_archives_the_fixture_after_its_sessions() -> None:
    gateway = _Gateway({"id": "stage4-maya", "status": "active"})

    _, _, observed = _cleanup(gateway, _checkpoint("stage4-maya"))

    assert observed["characters_archived"] == ["stage4-maya"]
    assert gateway.characters["stage4-maya"]["status"] == "archived"
    assert len(gateway.deleted_sessions) == 3


def test_cleanup_leaves_a_character_it_was_given() -> None:
    gateway = _Gateway({"id": "maya", "status": "active"})

    _, _, observed = _cleanup(gateway, _checkpoint("maya"))

    assert observed["characters_archived"] == []
    assert gateway.characters["maya"]["status"] == "active"


def test_a_later_run_uses_a_new_character(tmp_path: Path) -> None:
    gateway = _Gateway({"id": "stage4-maya", "status": "archived"})

    report = prepare_stage4(
        gateway,
        Stage4PrepareConfig(base_url="http://test"),
        checkpoint_path=tmp_path / "checkpoint.json",
    )

    assert report.character_id == "stage4-maya-2"
    assert gateway.characters["stage4-maya-2"]["status"] == "active"
    assert gateway.characters["stage4-maya"]["status"] == "archived"


def test_a_character_it_was_given_stays_refused_once_archived(tmp_path: Path) -> None:
    gateway = _Gateway({"id": "maya", "status": "archived"})

    report = prepare_stage4(
        gateway,
        Stage4PrepareConfig(base_url="http://test", character_id="maya"),
        checkpoint_path=tmp_path / "checkpoint.json",
    )

    assert report.decision == "blocked"
    assert next(item for item in report.checks if item.id == "fixtures.character_policy").status == "fail"
    assert list(gateway.characters) == ["maya"]
