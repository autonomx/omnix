"""Save/load and replay contract helpers for deterministic RPG state."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Mapping, Sequence


@dataclass(frozen=True)
class ReplaySnapshot:
    snapshot_id: str
    turn: int
    seed: int
    counters: Mapping[str, int] = field(default_factory=dict)
    state: Mapping[str, object] = field(default_factory=dict)

    def canonical_payload(self) -> dict[str, object]:
        return {
            "snapshot_id": self.snapshot_id,
            "turn": self.turn,
            "seed": self.seed,
            "counters": dict(sorted(self.counters.items())),
            "state": _stable_value(self.state),
        }

    def stable_hash(self) -> str:
        encoded = json.dumps(self.canonical_payload(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ReplayAction:
    turn: int
    action: str
    expected_state_hash: str = ""

    def as_dict(self) -> dict[str, object]:
        return {"turn": self.turn, "action": self.action, "expected_state_hash": self.expected_state_hash}


@dataclass(frozen=True)
class ReplayScenario:
    scenario_id: str
    seed: int
    actions: tuple[ReplayAction, ...]

    def as_dict(self) -> dict[str, object]:
        return {"scenario_id": self.scenario_id, "seed": self.seed, "actions": [action.as_dict() for action in self.actions]}


def compare_snapshot_hashes(expected: ReplaySnapshot, actual: ReplaySnapshot) -> dict[str, object]:
    expected_hash = expected.stable_hash()
    actual_hash = actual.stable_hash()
    return {"matches": expected_hash == actual_hash, "expected_hash": expected_hash, "actual_hash": actual_hash}


def build_regression_scenario(scenario_id: str, seed: int, actions: Sequence[str]) -> ReplayScenario:
    return ReplayScenario(scenario_id, seed, tuple(ReplayAction(index + 1, action) for index, action in enumerate(actions)))


def validate_snapshot(snapshot: ReplaySnapshot) -> tuple[str, ...]:
    issues: list[str] = []
    if snapshot.turn < 0:
        issues.append("negative_turn")
    if not snapshot.snapshot_id:
        issues.append("missing_snapshot_id")
    required = ("world", "player", "quests", "map", "inventory")
    for key in required:
        if key not in snapshot.state:
            issues.append(f"missing_state:{key}")
    return tuple(issues)


def replay_report_payload(snapshot: ReplaySnapshot, scenario: ReplayScenario) -> dict[str, object]:
    return {
        "snapshot_id": snapshot.snapshot_id,
        "turn": snapshot.turn,
        "state_hash": snapshot.stable_hash(),
        "scenario": scenario.as_dict(),
        "validation_issues": list(validate_snapshot(snapshot)),
    }


def _stable_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _stable_value(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_stable_value(item) for item in value]
    return value
