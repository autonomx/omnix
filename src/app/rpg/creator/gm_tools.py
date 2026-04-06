"""Phase 19 — Creator / GM tools.

GM state, permissions, world/actor/quest edit tools, runtime overrides,
scenario templates, console, export/import, safety/determinism.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))

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


def _normalize_override(override: Dict[str, Any], tick: int = 0) -> Dict[str, Any]:
    override = _safe_dict(override)
    return {
        "type": _ss(override.get("type")),
        "target_id": _ss(override.get("target_id")),
        "payload": _safe_dict(override.get("payload")),
        "tick": _si(override.get("tick"), tick),
    }


def _override_key(override: Dict[str, Any]) -> str:
    override = _safe_dict(override)
    return f"{_ss(override.get('type'))}:{_ss(override.get('target_id'))}"


def _is_valid_package(package: Dict[str, Any]) -> bool:
    package = _safe_dict(package)
    if _si(package.get("_format_version")) != SUPPORTED_PACKAGE_FORMAT_VERSION:
        return False
    if "gm_state" not in package or "world_data" not in package:
        return False
    if not isinstance(package.get("gm_state"), dict):
        return False
    if not isinstance(package.get("world_data"), dict):
        return False
    return True


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


def _validate_world_data(world_data: Dict[str, Any]) -> bool:
    world_data = _safe_dict(world_data)
    if not world_data:
        return True
    return _is_json_like(world_data)

# Constants
MAX_OVERRIDES = 50
MAX_TEMPLATES = 20
MAX_EDIT_HISTORY = 100
VALID_OVERRIDE_TYPES = {
    "set_flag",
    "force_scene_bias",
    "pause_actor",
    "force_goal",
    "inject_dialogue_directive",
}
SUPPORTED_PACKAGE_FORMAT_VERSION = 1

# ---------------------------------------------------------------------------
# 19.0 — GM state / permissions foundations
# ---------------------------------------------------------------------------

@dataclass
class GMPermissions:
    can_edit_world: bool = True
    can_edit_npcs: bool = True
    can_edit_quests: bool = True
    can_override_runtime: bool = True
    can_export: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "can_edit_world": self.can_edit_world,
            "can_edit_npcs": self.can_edit_npcs,
            "can_edit_quests": self.can_edit_quests,
            "can_override_runtime": self.can_override_runtime,
            "can_export": self.can_export,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "GMPermissions":
        return cls(**{k: bool(d.get(k, True)) for k in cls.__dataclass_fields__})


@dataclass
class GMState:
    gm_id: str = "default_gm"
    permissions: GMPermissions = field(default_factory=GMPermissions)
    active_overrides: List[Dict[str, Any]] = field(default_factory=list)
    edit_history: List[Dict[str, Any]] = field(default_factory=list)
    tick: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gm_id": self.gm_id,
            "permissions": self.permissions.to_dict(),
            "active_overrides": list(self.active_overrides),
            "edit_history": list(self.edit_history),
            "tick": self.tick,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "GMState":
        return cls(
            gm_id=_ss(d.get("gm_id"), "default_gm"),
            permissions=GMPermissions.from_dict(d.get("permissions") or {}),
            active_overrides=list(d.get("active_overrides") or []),
            edit_history=list(d.get("edit_history") or []),
            tick=_si(d.get("tick")),
        )


# ---------------------------------------------------------------------------
# 19.1 — World edit tools
# ---------------------------------------------------------------------------

class WorldEditTools:
    @staticmethod
    def edit_location(gm_state: GMState, location_id: str,
                      changes: Dict[str, Any], tick: int) -> Dict[str, Any]:
        if not gm_state.permissions.can_edit_world:
            return {"success": False, "reason": "no permission"}
        entry = {"type": "edit_location", "location_id": location_id,
                 "changes": dict(changes), "tick": tick}
        gm_state.edit_history.append(entry)
        if len(gm_state.edit_history) > MAX_EDIT_HISTORY:
            gm_state.edit_history = gm_state.edit_history[-MAX_EDIT_HISTORY:]
        return {"success": True, "edit": entry}

    @staticmethod
    def edit_faction(gm_state: GMState, faction_id: str,
                     changes: Dict[str, Any], tick: int) -> Dict[str, Any]:
        if not gm_state.permissions.can_edit_world:
            return {"success": False, "reason": "no permission"}
        entry = {"type": "edit_faction", "faction_id": faction_id,
                 "changes": dict(changes), "tick": tick}
        gm_state.edit_history.append(entry)
        if len(gm_state.edit_history) > MAX_EDIT_HISTORY:
            gm_state.edit_history = gm_state.edit_history[-MAX_EDIT_HISTORY:]
        return {"success": True, "edit": entry}


# ---------------------------------------------------------------------------
# 19.2 — Actor / NPC edit tools
# ---------------------------------------------------------------------------

class ActorEditTools:
    @staticmethod
    def edit_npc(gm_state: GMState, npc_id: str,
                 changes: Dict[str, Any], tick: int) -> Dict[str, Any]:
        if not gm_state.permissions.can_edit_npcs:
            return {"success": False, "reason": "no permission"}
        entry = {"type": "edit_npc", "npc_id": npc_id,
                 "changes": dict(changes), "tick": tick}
        gm_state.edit_history.append(entry)
        if len(gm_state.edit_history) > MAX_EDIT_HISTORY:
            gm_state.edit_history = gm_state.edit_history[-MAX_EDIT_HISTORY:]
        return {"success": True, "edit": entry}

    @staticmethod
    def spawn_npc(gm_state: GMState, npc_data: Dict[str, Any],
                  tick: int) -> Dict[str, Any]:
        if not gm_state.permissions.can_edit_npcs:
            return {"success": False, "reason": "no permission"}
        entry = {"type": "spawn_npc", "npc_data": dict(npc_data), "tick": tick}
        gm_state.edit_history.append(entry)
        if len(gm_state.edit_history) > MAX_EDIT_HISTORY:
            gm_state.edit_history = gm_state.edit_history[-MAX_EDIT_HISTORY:]
        return {"success": True, "edit": entry}


# ---------------------------------------------------------------------------
# 19.3 — Quest / event authoring tools
# ---------------------------------------------------------------------------

class QuestAuthoringTools:
    @staticmethod
    def create_quest(gm_state: GMState, quest_data: Dict[str, Any],
                     tick: int) -> Dict[str, Any]:
        if not gm_state.permissions.can_edit_quests:
            return {"success": False, "reason": "no permission"}
        entry = {"type": "create_quest", "quest_data": dict(quest_data), "tick": tick}
        gm_state.edit_history.append(entry)
        if len(gm_state.edit_history) > MAX_EDIT_HISTORY:
            gm_state.edit_history = gm_state.edit_history[-MAX_EDIT_HISTORY:]
        return {"success": True, "edit": entry}

    @staticmethod
    def inject_event(gm_state: GMState, event_data: Dict[str, Any],
                     tick: int) -> Dict[str, Any]:
        if not gm_state.permissions.can_edit_quests:
            return {"success": False, "reason": "no permission"}
        entry = {"type": "inject_event", "event_data": dict(event_data), "tick": tick}
        gm_state.edit_history.append(entry)
        if len(gm_state.edit_history) > MAX_EDIT_HISTORY:
            gm_state.edit_history = gm_state.edit_history[-MAX_EDIT_HISTORY:]
        return {"success": True, "edit": entry}


# ---------------------------------------------------------------------------
# 19.4 — Runtime override / intervention tools
# ---------------------------------------------------------------------------

class RuntimeOverrideTools:
    @staticmethod
    def add_override(gm_state: GMState, override: Dict[str, Any],
                     tick: int) -> Dict[str, Any]:
        if not gm_state.permissions.can_override_runtime:
            return {"success": False, "reason": "no permission"}
        normalized = _normalize_override(override, tick=tick)
        if normalized["type"] not in VALID_OVERRIDE_TYPES:
            return {"success": False, "reason": f"invalid override type: {normalized['type']}"}
        if not normalized["target_id"]:
            return {"success": False, "reason": "missing target_id"}

        existing = {_override_key(v): _normalize_override(v) for v in gm_state.active_overrides}
        existing[_override_key(normalized)] = normalized
        gm_state.active_overrides = [
            existing[k] for k in sorted(existing.keys())
        ]
        if len(gm_state.active_overrides) > MAX_OVERRIDES:
            gm_state.active_overrides = gm_state.active_overrides[-MAX_OVERRIDES:]
        return {"success": True, "override": normalized}

    @staticmethod
    def clear_overrides(gm_state: GMState) -> Dict[str, Any]:
        count = len(gm_state.active_overrides)
        gm_state.active_overrides = []
        return {"success": True, "cleared": count}

    @staticmethod
    def get_active_overrides(gm_state: GMState) -> List[Dict[str, Any]]:
        return list(gm_state.active_overrides)


# ---------------------------------------------------------------------------
# 19.5 — Scenario templates / sandbox presets
# ---------------------------------------------------------------------------

class ScenarioTemplateManager:
    TEMPLATES: Dict[str, Dict[str, Any]] = {
        "tutorial": {
            "name": "Tutorial",
            "description": "A guided introduction",
            "settings": {"difficulty": "easy", "npcs": 3, "quests": 1},
        },
        "sandbox": {
            "name": "Sandbox",
            "description": "Free exploration",
            "settings": {"difficulty": "medium", "npcs": 10, "quests": 0},
        },
        "campaign": {
            "name": "Campaign",
            "description": "Structured story campaign",
            "settings": {"difficulty": "hard", "npcs": 20, "quests": 5},
        },
    }

    @classmethod
    def list_templates(cls) -> List[Dict[str, Any]]:
        return [{"id": k, **v} for k, v in cls.TEMPLATES.items()]

    @classmethod
    def get_template(cls, template_id: str) -> Optional[Dict[str, Any]]:
        tmpl = cls.TEMPLATES.get(template_id)
        return {"id": template_id, **tmpl} if tmpl else None


# ---------------------------------------------------------------------------
# 19.6 — GM console / inspector polish
# ---------------------------------------------------------------------------

class GMConsole:
    @staticmethod
    def inspect_gm_state(gm_state: GMState) -> Dict[str, Any]:
        return {
            "gm_id": gm_state.gm_id,
            "tick": gm_state.tick,
            "permissions": gm_state.permissions.to_dict(),
            "active_override_count": len(gm_state.active_overrides),
            "edit_history_count": len(gm_state.edit_history),
        }

    @staticmethod
    def get_edit_history(gm_state: GMState, last_n: int = 10) -> List[Dict[str, Any]]:
        return list(gm_state.edit_history[-last_n:])


# ---------------------------------------------------------------------------
# 19.7 — Export / import / content packaging
# ---------------------------------------------------------------------------

class ContentPackager:
    @staticmethod
    def export_state(gm_state: GMState, world_data: Dict[str, Any]) -> Dict[str, Any]:
        if not gm_state.permissions.can_export:
            return {"success": False, "reason": "no permission"}
        normalized_gm_state = GMDeterminismValidator.normalize_state(gm_state).to_dict()
        normalized_world_data = _safe_dict(world_data)
        return {
            "success": True,
            "package": {
                "gm_state": normalized_gm_state,
                "world_data": normalized_world_data,
                "export_tick": gm_state.tick,
                "_format_version": SUPPORTED_PACKAGE_FORMAT_VERSION,
            },
        }

    @staticmethod
    def import_state(package: Dict[str, Any]) -> Dict[str, Any]:
        package = _safe_dict(package)
        if not _is_valid_package(package):
            return {"success": False, "reason": "invalid package format"}
        if not _validate_world_data(package.get("world_data") or {}):
            return {"success": False, "reason": "invalid world_data payload"}
        gm_state = GMState.from_dict(package.get("gm_state") or {})
        gm_state = GMDeterminismValidator.normalize_state(gm_state)
        return {
            "success": True,
            "gm_state": gm_state.to_dict(),
            "world_data": _safe_dict(package.get("world_data")),
        }


# ---------------------------------------------------------------------------
# 19.8 — GM tool safety / determinism fix pass
# ---------------------------------------------------------------------------

class GMDeterminismValidator:
    @staticmethod
    def validate_determinism(s1: GMState, s2: GMState) -> bool:
        return s1.to_dict() == s2.to_dict()

    @staticmethod
    def validate_bounds(gm_state: GMState) -> List[str]:
        violations: List[str] = []
        if len(gm_state.active_overrides) > MAX_OVERRIDES:
            violations.append(f"overrides exceed max ({len(gm_state.active_overrides)} > {MAX_OVERRIDES})")
        if len(gm_state.edit_history) > MAX_EDIT_HISTORY:
            violations.append(f"edit_history exceeds max ({len(gm_state.edit_history)} > {MAX_EDIT_HISTORY})")
        for override in gm_state.active_overrides:
            normalized = _normalize_override(override)
            if normalized["type"] not in VALID_OVERRIDE_TYPES:
                violations.append(f"invalid override type: {normalized['type']}")
            if not normalized["target_id"]:
                violations.append("override missing target_id")
        return violations

    @staticmethod
    def normalize_state(gm_state: GMState) -> GMState:
        overrides_map = {}
        for override in gm_state.active_overrides:
            normalized = _normalize_override(override)
            if normalized["type"] not in VALID_OVERRIDE_TYPES:
                continue
            if not normalized["target_id"]:
                continue
            overrides_map[_override_key(normalized)] = normalized
        overrides = [overrides_map[k] for k in sorted(overrides_map.keys())]
        if len(overrides) > MAX_OVERRIDES:
            overrides = overrides[-MAX_OVERRIDES:]
        history = [dict(v) for v in gm_state.edit_history if isinstance(v, dict)]
        if len(history) > MAX_EDIT_HISTORY:
            history = history[-MAX_EDIT_HISTORY:]
        return GMState(
            gm_id=gm_state.gm_id,
            permissions=GMPermissions.from_dict(gm_state.permissions.to_dict()),
            active_overrides=overrides,
            edit_history=history,
            tick=gm_state.tick,
        )