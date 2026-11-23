"""An approved Hermes command is checked, submitted and recorded in one call; nothing reaches the game unless the
flow is switched on and the step is ready."""
from __future__ import annotations

from typing import Any

import pytest

from app.apps.rpg.edge.hermes.approved_command import run_approved_command
from app.apps.rpg.edge.hermes.execution_ledger import (
    hermes_rpg_execution_ledger_recent,
    hermes_rpg_execution_ledger_reset,
)

_ON = {"HERMES_RPG_APPROVED_FLOW_ENABLED": "1"}


@pytest.fixture(autouse=True)
def _empty_ledger() -> None:
    hermes_rpg_execution_ledger_reset()


def _payload(*, enabled: bool = True, ready: bool = True, replay_ok: bool = True) -> dict[str, Any]:
    return {
        "enabled": enabled,
        "user_step": {"ready": ready, "command_text": "look around"},
        "replay_entry": {"ok": replay_ok, "command_text": "look around"},
        "context": {"session_id": "session:a", "context_hash": "hash:1"},
    }


class _Submitter:
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def __call__(self, request: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(request)
        return self.result


@pytest.mark.parametrize(("payload_enabled", "environ"), [(False, _ON), (True, {})])
def test_a_command_is_not_submitted_unless_the_flow_and_the_payload_are_both_on(
        payload_enabled: bool, environ: dict[str, str]) -> None:
    submitter = _Submitter({"ok": True})

    out = run_approved_command(_payload(enabled=payload_enabled), submitter=submitter, environ=environ)

    assert (out["ok"], out["error"], out["state_changed"]) == (False, "hermes_rpg_approved_flow_disabled", False)
    assert submitter.calls == []
    assert hermes_rpg_execution_ledger_recent()["items"] == []


@pytest.mark.parametrize("change", [{"ready": False}, {"replay_ok": False}])
def test_a_step_that_is_not_ready_is_recorded_as_blocked_and_never_submitted(change: dict[str, bool]) -> None:
    submitter = _Submitter({"ok": True})

    out = run_approved_command(_payload(**change), submitter=submitter, environ=_ON)

    assert submitter.calls == []
    assert (out["ok"], out["state_changed"]) == (False, False)
    assert out["flow"]["ready_for_rpg_pipeline"] is False
    assert (out["readout"]["status"], out["readout"]["error"]) == ("blocked", "packet_not_ready")
    assert len(hermes_rpg_execution_ledger_recent()["items"]) == 1


def test_a_ready_step_is_submitted_once_on_the_turn_path_and_recorded() -> None:
    submitter = _Submitter({"ok": True, "state_revision": 4})

    out = run_approved_command(_payload(), submitter=submitter, environ=_ON)

    assert submitter.calls == [{"session_id": "session:a", "command_text": "look around", "input": "look around",
                                "context_hash": "hash:1", "canonical_path": "rpg_turn_execute"}]
    assert (out["ok"], out["state_changed"], out["readout"]["status"]) == (True, True, "accepted")
    assert out["flow"]["result"]["rpg_result"]["state_revision"] == 4
    assert len(hermes_rpg_execution_ledger_recent()["items"]) == 1


def test_a_turn_the_game_refuses_reads_out_the_games_error() -> None:
    submitter = _Submitter({"ok": False, "error": "rpg_state_revision_conflict", "status_code": 409})

    out = run_approved_command(_payload(), submitter=submitter, environ=_ON)

    assert len(submitter.calls) == 1
    assert (out["ok"], out["state_changed"]) == (False, False)
    assert (out["readout"]["status"], out["readout"]["error"]) == ("blocked", "rpg_state_revision_conflict")
