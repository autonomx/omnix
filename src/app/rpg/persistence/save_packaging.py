"""Phase 20 — Save / migration / packaging.

Versioned save schema, validation, migration, replay consistency,
portability, corruption recovery, inspector, determinism.
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


def _safe_dict(v: Any) -> Dict[str, Any]:
    return dict(v) if isinstance(v, dict) else {}


def _safe_list(v: Any) -> List[Any]:
    return list(v) if isinstance(v, list) else []


def _is_json_like(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, list):
        return all(_is_json_like(v) for v in value)
    if isinstance(value, dict):
        return all(isinstance(k, str) and _is_json_like(v) for k, v in value.items())
    return False


def _stable_json_data(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_stable_json_data(v) for v in value]
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for key in sorted(value.keys()):
            if isinstance(key, str):
                out[key] = _stable_json_data(value[key])
        return out
    return _ss(value)


def _stable_json_dumps(value: Any) -> str:
    return json.dumps(
        _stable_json_data(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _stable_hash(value: Any) -> str:
    return hashlib.sha1(_stable_json_dumps(value).encode("utf-8")).hexdigest()


def _normalize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = _safe_dict(payload)
    normalized = _stable_json_data(payload)
    return normalized if isinstance(normalized, dict) else {}


# Constants
SAVE_FORMAT_VERSION = 1
MAX_MIGRATION_HISTORY = 20
MAX_VALIDATION_ERRORS = 100


# ---------------------------------------------------------------------------
# 20.0 — Save schema foundations
# ---------------------------------------------------------------------------

@dataclass
class SaveSnapshot:
    save_id: str = ""
    version: int = SAVE_FORMAT_VERSION
    tick: int = 0
    simulation_state: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    integrity_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "save_id": self.save_id,
            "version": self.version,
            "tick": self.tick,
            "simulation_state": _normalize_payload(self.simulation_state),
            "metadata": _normalize_payload(self.metadata),
            "integrity_hash": self.integrity_hash,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SaveSnapshot":
        d = _safe_dict(d)
        return cls(
            save_id=_ss(d.get("save_id")),
            version=_si(d.get("version"), SAVE_FORMAT_VERSION),
            tick=_si(d.get("tick")),
            simulation_state=_normalize_payload(d.get("simulation_state") or {}),
            metadata=_normalize_payload(d.get("metadata") or {}),
            integrity_hash=_ss(d.get("integrity_hash")),
        )


@dataclass
class MigrationRecord:
    from_version: int = 0
    to_version: int = 0
    applied: bool = False
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_version": self.from_version,
            "to_version": self.to_version,
            "applied": self.applied,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MigrationRecord":
        return cls(
            from_version=_si(d.get("from_version")),
            to_version=_si(d.get("to_version")),
            applied=bool(d.get("applied", False)),
            notes=_ss(d.get("notes")),
        )


@dataclass
class SavePackagingState:
    current_version: int = SAVE_FORMAT_VERSION
    migration_history: List[MigrationRecord] = field(default_factory=list)
    last_validation_errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_version": self.current_version,
            "migration_history": [m.to_dict() for m in self.migration_history],
            "last_validation_errors": list(self.last_validation_errors),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SavePackagingState":
        return cls(
            current_version=_si(d.get("current_version"), SAVE_FORMAT_VERSION),
            migration_history=[MigrationRecord.from_dict(m) for m in (d.get("migration_history") or [])],
            last_validation_errors=[str(v) for v in (d.get("last_validation_errors") or [])],
        )


# ---------------------------------------------------------------------------
# 20.1 — Save schema and validation
# ---------------------------------------------------------------------------

class SaveSchema:
    """Save schema and validation helpers."""

    REQUIRED_KEYS = {
        "save_id",
        "version",
        "tick",
        "simulation_state",
        "metadata",
    }

    @classmethod
    def validate_snapshot_dict(cls, snapshot: Dict[str, Any]) -> List[str]:
        errors: List[str] = []
        snapshot = _safe_dict(snapshot)

        for key in sorted(cls.REQUIRED_KEYS):
            if key not in snapshot:
                errors.append(f"missing required key: {key}")

        version = _si(snapshot.get("version"), -1)
        if version < 1:
            errors.append(f"invalid version: {version}")

        tick = _si(snapshot.get("tick"), -1)
        if tick < 0:
            errors.append(f"invalid tick: {tick}")

        if not isinstance(snapshot.get("simulation_state"), dict):
            errors.append("simulation_state must be a dict")
        if not isinstance(snapshot.get("metadata"), dict):
            errors.append("metadata must be a dict")
        if "integrity_hash" in snapshot and not isinstance(snapshot.get("integrity_hash"), str):
            errors.append("integrity_hash must be a string")

        if isinstance(snapshot.get("simulation_state"), dict) and not _is_json_like(snapshot.get("simulation_state")):
            errors.append("simulation_state must be JSON-like")
        if isinstance(snapshot.get("metadata"), dict) and not _is_json_like(snapshot.get("metadata")):
            errors.append("metadata must be JSON-like")

        return errors[:MAX_VALIDATION_ERRORS]


# ---------------------------------------------------------------------------
# 20.2 — Save builder
# ---------------------------------------------------------------------------

class SaveBuilder:
    """Create deterministic save snapshots."""

    @staticmethod
    def build_snapshot(
        *,
        save_id: str,
        tick: int,
        simulation_state: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SaveSnapshot:
        normalized_simulation_state = _normalize_payload(simulation_state)
        normalized_metadata = _normalize_payload(metadata or {})
        snapshot = SaveSnapshot(
            save_id=_ss(save_id),
            version=SAVE_FORMAT_VERSION,
            tick=max(0, _si(tick)),
            simulation_state=normalized_simulation_state,
            metadata=normalized_metadata,
        )
        snapshot.integrity_hash = SaveBuilder.compute_integrity_hash(snapshot)
        return snapshot

    @staticmethod
    def compute_integrity_hash(snapshot: SaveSnapshot) -> str:
        payload = {
            "save_id": _ss(snapshot.save_id),
            "version": _si(snapshot.version),
            "tick": _si(snapshot.tick),
            "simulation_state": _normalize_payload(snapshot.simulation_state),
            "metadata": _normalize_payload(snapshot.metadata),
        }
        return _stable_hash(payload)


# ---------------------------------------------------------------------------
# 20.3 — Save serialization
# ---------------------------------------------------------------------------

class SaveSerializer:
    """Serialize and deserialize save snapshots deterministically."""

    @staticmethod
    def dump_snapshot(snapshot: SaveSnapshot) -> str:
        snapshot = SavePackagingValidator.normalize_snapshot(snapshot)
        return _stable_json_dumps(snapshot.to_dict())

    @staticmethod
    def load_snapshot(text: str) -> SaveSnapshot:
        data = json.loads(text)
        snapshot = SaveSnapshot.from_dict(data)
        return SavePackagingValidator.normalize_snapshot(snapshot)


# ---------------------------------------------------------------------------
# 20.4 — Save migration
# ---------------------------------------------------------------------------

class SaveMigrator:
    """Migrate save snapshots across versions."""

    @staticmethod
    def _migrate_one(snapshot: SaveSnapshot, target_version: int) -> SaveSnapshot:
        snapshot.version = target_version
        return snapshot

    @staticmethod
    def migrate(snapshot: SaveSnapshot, state: Optional[SavePackagingState] = None) -> SaveSnapshot:
        state = state or SavePackagingState()
        current = SaveSnapshot.from_dict(snapshot.to_dict())
        while current.version < SAVE_FORMAT_VERSION:
            next_version = current.version + 1
            current = SaveMigrator._migrate_one(current, next_version)
            state.migration_history.append(MigrationRecord(
                from_version=next_version - 1,
                to_version=next_version,
                applied=True,
                notes=f"migrated save to version {next_version}",
            ))
            if len(state.migration_history) > MAX_MIGRATION_HISTORY:
                state.migration_history = state.migration_history[-MAX_MIGRATION_HISTORY:]
        current = SavePackagingValidator.normalize_snapshot(current)
        return current


# ---------------------------------------------------------------------------
# 20.5 — Replay consistency
# ---------------------------------------------------------------------------

class ReplayConsistencyChecker:
    """Check round-trip determinism for save/load."""

    @staticmethod
    def check_round_trip(snapshot: SaveSnapshot) -> Dict[str, Any]:
        normalized = SavePackagingValidator.normalize_snapshot(snapshot)
        dumped = SaveSerializer.dump_snapshot(normalized)
        loaded = SaveSerializer.load_snapshot(dumped)
        return {
            "matches": normalized.to_dict() == loaded.to_dict(),
            "before": normalized.to_dict(),
            "after": loaded.to_dict(),
        }


# ---------------------------------------------------------------------------
# 20.6 — Save packaging validator
# ---------------------------------------------------------------------------

class SavePackagingValidator:
    @staticmethod
    def validate_snapshot(snapshot: SaveSnapshot) -> List[str]:
        errors = SaveSchema.validate_snapshot_dict(snapshot.to_dict())
        expected_hash = SaveBuilder.compute_integrity_hash(snapshot)
        actual_hash = _ss(snapshot.integrity_hash)
        if actual_hash and actual_hash != expected_hash:
            errors.append("integrity_hash mismatch")
        return errors[:MAX_VALIDATION_ERRORS]

    @staticmethod
    def normalize_snapshot(snapshot: SaveSnapshot) -> SaveSnapshot:
        normalized = SaveSnapshot.from_dict(snapshot.to_dict())
        normalized.version = max(1, _si(normalized.version, SAVE_FORMAT_VERSION))
        normalized.tick = max(0, _si(normalized.tick))
        normalized.simulation_state = _normalize_payload(normalized.simulation_state)
        normalized.metadata = _normalize_payload(normalized.metadata)
        normalized.integrity_hash = SaveBuilder.compute_integrity_hash(normalized)
        return normalized

    @staticmethod
    def normalize_packaging_state(state: SavePackagingState) -> SavePackagingState:
        history = list(state.migration_history)
        errors = [str(v) for v in state.last_validation_errors]
        if len(history) > MAX_MIGRATION_HISTORY:
            history = history[-MAX_MIGRATION_HISTORY:]
        if len(errors) > MAX_VALIDATION_ERRORS:
            errors = errors[-MAX_VALIDATION_ERRORS:]
        return SavePackagingState(
            current_version=max(1, _si(state.current_version, SAVE_FORMAT_VERSION)),
            migration_history=history,
            last_validation_errors=errors,
        )