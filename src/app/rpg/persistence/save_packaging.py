"""Phase 20 — Save / migration / packaging.

Save schema, versioned snapshots, validation, migration pipeline,
replay checks, packaging, corruption recovery, inspector, determinism.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

def _sf(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d

def _si(v: Any, d: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return d

def _ss(v: Any, d: str = "") -> str:
    return str(v) if v is not None else d

# Constants
CURRENT_SAVE_VERSION = 8
MAX_SNAPSHOTS = 100
MAX_MIGRATION_STEPS = 10

# ---------------------------------------------------------------------------
# 20.0 — Save schema foundations
# ---------------------------------------------------------------------------

@dataclass
class SaveHeader:
    version: int = CURRENT_SAVE_VERSION
    created_tick: int = 0
    save_id: str = ""
    checksum: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version, "created_tick": self.created_tick,
            "save_id": self.save_id, "checksum": self.checksum,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SaveHeader":
        return cls(
            version=_si(d.get("version"), CURRENT_SAVE_VERSION),
            created_tick=_si(d.get("created_tick")),
            save_id=_ss(d.get("save_id")),
            checksum=_ss(d.get("checksum")),
            metadata=dict(d.get("metadata") or {}),
        )


@dataclass
class SaveSnapshot:
    header: SaveHeader = field(default_factory=SaveHeader)
    game_state: Dict[str, Any] = field(default_factory=dict)
    subsystem_states: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "header": self.header.to_dict(),
            "game_state": dict(self.game_state),
            "subsystem_states": {k: dict(v) for k, v in self.subsystem_states.items()},
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SaveSnapshot":
        return cls(
            header=SaveHeader.from_dict(d.get("header") or {}),
            game_state=dict(d.get("game_state") or {}),
            subsystem_states={
                k: dict(v) for k, v in (d.get("subsystem_states") or {}).items()
            },
        )


# ---------------------------------------------------------------------------
# 20.1 — Versioned snapshot format
# ---------------------------------------------------------------------------

class SnapshotManager:
    @staticmethod
    def create_snapshot(game_state: Dict[str, Any],
                        subsystems: Dict[str, Dict[str, Any]],
                        tick: int, save_id: str = "") -> SaveSnapshot:
        snapshot = SaveSnapshot(
            header=SaveHeader(
                version=CURRENT_SAVE_VERSION,
                created_tick=tick,
                save_id=save_id or f"save_{tick}",
            ),
            game_state=dict(game_state),
            subsystem_states={k: dict(v) for k, v in subsystems.items()},
        )
        # Compute checksum
        content = json.dumps(snapshot.to_dict(), sort_keys=True)
        snapshot.header.checksum = hashlib.sha256(content.encode()).hexdigest()[:16]
        return snapshot


# ---------------------------------------------------------------------------
# 20.2 — Save/load validation
# ---------------------------------------------------------------------------

class SaveValidator:
    @staticmethod
    def validate_snapshot(snapshot: SaveSnapshot) -> List[str]:
        errors: List[str] = []
        if not snapshot.header.save_id:
            errors.append("missing save_id")
        if snapshot.header.version < 1:
            errors.append("invalid version")
        if not snapshot.game_state:
            errors.append("empty game_state")
        return errors

    @staticmethod
    def verify_checksum(snapshot: SaveSnapshot) -> bool:
        stored = snapshot.header.checksum
        snapshot.header.checksum = ""
        content = json.dumps(snapshot.to_dict(), sort_keys=True)
        computed = hashlib.sha256(content.encode()).hexdigest()[:16]
        snapshot.header.checksum = stored
        return stored == computed


# ---------------------------------------------------------------------------
# 20.3 — Migration pipeline
# ---------------------------------------------------------------------------

@dataclass
class MigrationStep:
    from_version: int = 0
    to_version: int = 0
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_version": self.from_version,
            "to_version": self.to_version,
            "description": self.description,
        }


class MigrationPipeline:
    """Chain of migration steps from old to current version."""

    MIGRATIONS: List[MigrationStep] = [
        MigrationStep(7, 8, "Add travel and quest deepening state"),
    ]

    @classmethod
    def get_migration_path(cls, from_version: int) -> List[MigrationStep]:
        path: List[MigrationStep] = []
        current = from_version
        for step in cls.MIGRATIONS:
            if step.from_version == current:
                path.append(step)
                current = step.to_version
        return path

    @classmethod
    def migrate(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        version = _si(data.get("header", {}).get("version"), 1)
        result = dict(data)
        for step in cls.get_migration_path(version):
            if step.from_version == 7 and step.to_version == 8:
                subs = result.setdefault("subsystem_states", {})
                subs.setdefault("travel", {"tick": 0, "current_node": "", "regions": [], "nodes": [], "routes": [], "travel_log": []})
                subs.setdefault("quest_v2", {"tick": 0, "active_quests": [], "completed_quests": [], "quest_history": []})
                if "header" in result:
                    result["header"]["version"] = 8
        return result

    @classmethod
    def is_current(cls, data: Dict[str, Any]) -> bool:
        version = _si(data.get("header", {}).get("version"), 1)
        return version >= CURRENT_SAVE_VERSION


# ---------------------------------------------------------------------------
# 20.4 — Replay consistency checks
# ---------------------------------------------------------------------------

class ReplayConsistencyChecker:
    @staticmethod
    def check_consistency(snapshot1: SaveSnapshot,
                          snapshot2: SaveSnapshot) -> Dict[str, Any]:
        diffs: List[str] = []
        for key in set(list(snapshot1.game_state.keys()) + list(snapshot2.game_state.keys())):
            v1 = snapshot1.game_state.get(key)
            v2 = snapshot2.game_state.get(key)
            if v1 != v2:
                diffs.append(f"game_state.{key} differs")
        for key in set(list(snapshot1.subsystem_states.keys()) + list(snapshot2.subsystem_states.keys())):
            v1 = snapshot1.subsystem_states.get(key)
            v2 = snapshot2.subsystem_states.get(key)
            if v1 != v2:
                diffs.append(f"subsystem_states.{key} differs")
        return {
            "consistent": len(diffs) == 0,
            "diff_count": len(diffs),
            "diffs": diffs,
        }


# ---------------------------------------------------------------------------
# 20.5 — Packaging / scenario portability
# ---------------------------------------------------------------------------

class ScenarioPackager:
    @staticmethod
    def package_scenario(snapshot: SaveSnapshot,
                         scenario_name: str = "") -> Dict[str, Any]:
        return {
            "scenario_name": scenario_name or snapshot.header.save_id,
            "format_version": CURRENT_SAVE_VERSION,
            "snapshot": snapshot.to_dict(),
        }

    @staticmethod
    def unpackage_scenario(package: Dict[str, Any]) -> Optional[SaveSnapshot]:
        snap_data = package.get("snapshot")
        if not snap_data:
            return None
        return SaveSnapshot.from_dict(snap_data)


# ---------------------------------------------------------------------------
# 20.6 — Corruption recovery / diagnostics
# ---------------------------------------------------------------------------

class CorruptionRecovery:
    @staticmethod
    def diagnose(snapshot: SaveSnapshot) -> Dict[str, Any]:
        issues: List[str] = []
        if not snapshot.header.save_id:
            issues.append("missing save_id")
        if not snapshot.game_state:
            issues.append("empty game_state")
        if snapshot.header.version < 1:
            issues.append("invalid version")
        for key, sub in snapshot.subsystem_states.items():
            if not isinstance(sub, dict):
                issues.append(f"subsystem {key} is not a dict")
        return {"healthy": len(issues) == 0, "issues": issues}

    @staticmethod
    def attempt_repair(snapshot: SaveSnapshot) -> SaveSnapshot:
        if not snapshot.header.save_id:
            snapshot.header.save_id = f"repaired_{snapshot.header.created_tick}"
        if snapshot.header.version < 1:
            snapshot.header.version = CURRENT_SAVE_VERSION
        if not snapshot.game_state:
            snapshot.game_state = {"tick": snapshot.header.created_tick}
        cleaned: Dict[str, Dict[str, Any]] = {}
        for key, sub in snapshot.subsystem_states.items():
            if isinstance(sub, dict):
                cleaned[key] = sub
        snapshot.subsystem_states = cleaned
        return snapshot


# ---------------------------------------------------------------------------
# 20.7 — Save inspector / verification tools
# ---------------------------------------------------------------------------

class SaveInspector:
    @staticmethod
    def inspect_snapshot(snapshot: SaveSnapshot) -> Dict[str, Any]:
        return {
            "save_id": snapshot.header.save_id,
            "version": snapshot.header.version,
            "tick": snapshot.header.created_tick,
            "checksum": snapshot.header.checksum,
            "game_state_keys": sorted(snapshot.game_state.keys()),
            "subsystem_count": len(snapshot.subsystem_states),
            "subsystems": sorted(snapshot.subsystem_states.keys()),
        }

    @staticmethod
    def compare_snapshots(s1: SaveSnapshot, s2: SaveSnapshot) -> Dict[str, Any]:
        return ReplayConsistencyChecker.check_consistency(s1, s2)


# ---------------------------------------------------------------------------
# 20.8 — Save compatibility / determinism fix pass
# ---------------------------------------------------------------------------

class SaveDeterminismValidator:
    @staticmethod
    def validate_determinism(s1: SaveSnapshot, s2: SaveSnapshot) -> bool:
        return s1.to_dict() == s2.to_dict()

    @staticmethod
    def validate_bounds(snapshot: SaveSnapshot) -> List[str]:
        violations: List[str] = []
        if snapshot.header.version > CURRENT_SAVE_VERSION:
            violations.append(f"version too high: {snapshot.header.version}")
        return violations

    @staticmethod
    def normalize_snapshot(snapshot: SaveSnapshot) -> SaveSnapshot:
        if snapshot.header.version > CURRENT_SAVE_VERSION:
            snapshot.header.version = CURRENT_SAVE_VERSION
        return snapshot
