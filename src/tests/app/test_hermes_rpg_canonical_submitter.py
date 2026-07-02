from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.assist_core.hermes_rpg_canonical_submitter import hermes_rpg_canonical_submitter


@dataclass
class _Player:
    name: str = "Hero"

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name}


@dataclass
class _Event:
    event_type: str = "command"

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.event_type}


@dataclass
class _Session:
    session_id: str = "s1"
    turn_count: int = 3
    player: _Player = field(default_factory=_Player)


@dataclass
class _TurnResult:
    narration: str = "You check your pack."
    state_changes: dict[str, Any] = field(default_factory=lambda: {"inspected": True})
    events: list[_Event] = field(default_factory=lambda: [_Event()])
    choices: list[str] = field(default_factory=list)
    error: str | None = None
    dice_roll: Any = None
    fail_state: Any = None


def test_hermes_rpg_canonical_submitter_uses_loader_and_executor() -> None:
    seen: list[tuple[str, str]] = []

    def loader(session_id: str) -> _Session:
        seen.append(("load", session_id))
        return _Session(session_id=session_id)

    def executor(session: _Session, command_text: str) -> _TurnResult:
        seen.append((session.session_id, command_text))
        return _TurnResult()

    payload = hermes_rpg_canonical_submitter(
        {"session_id": "s1", "command_text": "check inventory"},
        loader=loader,
        executor=executor,
    )

    assert seen == [("load", "s1"), ("s1", "check inventory")]
    assert payload["ok"] is True
    assert payload["success"] is True
    assert payload["source"] == "hermes_rpg_canonical_submitter"
    assert payload["turn"] == 3
    assert payload["player"] == {"name": "Hero"}
    assert payload["events"] == [{"type": "command"}]
    assert payload["state_changed"] is True


def test_hermes_rpg_canonical_submitter_blocks_missing_command() -> None:
    payload = hermes_rpg_canonical_submitter({"session_id": "s1", "command_text": "   "})

    assert payload["ok"] is False
    assert payload["error"] == "missing_command"
    assert payload["state_changed"] is False


def test_hermes_rpg_canonical_submitter_reports_missing_game() -> None:
    payload = hermes_rpg_canonical_submitter(
        {"session_id": "missing", "command_text": "look"},
        loader=lambda session_id: None,
        executor=lambda session, command: _TurnResult(),
    )

    assert payload["ok"] is False
    assert payload["error"] == "game_not_found"
    assert payload["state_changed"] is False
