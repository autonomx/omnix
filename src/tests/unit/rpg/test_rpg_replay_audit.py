"""The replay audit finds gaps, unpatched turns and chain breaks, and replays across them (RQ-0.9)."""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

from app.apps.rpg.foundation.persistence.rpg_repository import state_hash
from app.apps.rpg.foundation.persistence.state_delta import state_delta

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "rpg_replay_audit.py"
spec = importlib.util.spec_from_file_location("omnix_rpg_replay_audit", SCRIPT)
assert spec and spec.loader
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def _states(count: int) -> list[dict]:
    states, state = [], {"simulation_state": {"npc_presence": {}, "tick": 0}, "runtime_state": {"log": []}}
    states.append(copy.deepcopy(state))
    for index in range(1, count + 1):
        state = copy.deepcopy(state)
        state["simulation_state"]["tick"] = index
        state["runtime_state"]["log"].append(index)
        states.append(state)
    return states


def _turn(revision: int, before: dict, after: dict, *, patch: bool = True, hash_before: str | None = None) -> dict:
    return {
        "resulting_revision": revision,
        "state_delta": state_delta(before, after) if patch else None,
        "state_hash_before": hash_before or state_hash(before),
        "state_hash_after": state_hash(after),
    }


def _campaign(states: list[dict]) -> dict:
    return {
        "id": "campaign:audit",
        "revision": len(states) - 1,
        "state": states[-1],
        "state_hash": state_hash(states[-1]),
        "schema_version": "rpg-session-v1",
    }


def test_an_unbroken_chain_replays_from_its_snapshot_to_the_current_state() -> None:
    states = _states(5)
    turns = [_turn(r, states[r - 1], states[r]) for r in range(1, 6)]
    snapshots = [{"revision": 0, "state": states[0], "state_hash": state_hash(states[0])}]

    result = audit.audit_campaign(_campaign(states), turns, snapshots)

    assert result["verified_turns"] == 5
    assert result["revisions_without_turn_row"] == 0
    assert result["hash_chain_breaks"] == 0
    assert result["replay_matches_current"] is True
    assert result["size"]["npc_related_bytes"] > 0


def test_a_save_outside_a_turn_breaks_the_chain_and_replay_restarts_at_the_next_snapshot() -> None:
    states = _states(6)
    # Revision 3 was written outside a turn (no turn row); turn 4 starts from it.
    turns = [_turn(r, states[r - 1], states[r]) for r in (1, 2, 4, 5, 6)]
    snapshots = [
        {"revision": 0, "state": states[0], "state_hash": state_hash(states[0])},
        {"revision": 4, "state": states[4], "state_hash": state_hash(states[4])},
    ]

    result = audit.audit_campaign(_campaign(states), turns, snapshots)

    assert result["revisions_without_turn_row"] == 1
    assert result["first_missing_turn_rows"] == [3]
    assert result["hash_chain_breaks"] == 1
    assert result["verified_turns"] == 4  # 1, 2 from snapshot 0; 5, 6 from snapshot 4
    assert result["replay_matches_current"] is True


def test_unpatched_turns_and_bad_snapshots_are_reported_and_not_replayed() -> None:
    states = _states(3)
    turns = [_turn(1, states[0], states[1], patch=False), _turn(2, states[1], states[2]), _turn(3, states[2], states[3])]
    snapshots = [
        {"revision": 0, "state": states[0], "state_hash": "0" * 64},
        {"revision": 1, "state": states[1], "state_hash": state_hash(states[1])},
    ]

    result = audit.audit_campaign(_campaign(states), turns, snapshots)

    assert result["turns_without_patch"] == 1
    assert result["snapshots_failing_hash"] == [0]
    assert result["verified_turns"] == 2
    assert result["replay_matches_current"] is True
    assert audit.summarize([result])["campaigns_replaying_to_current"] == 1
