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

# Constants
MAX_OVERRIDES = 50
MAX_TEMPLATES = 20
MAX_EDIT_HISTORY = 100

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
        override["tick"] = tick
        gm_state.active_overrides.append(override)
        if len(gm_state.active_overrides) > MAX_OVERRIDES:
            gm_state.active_overrides = gm_state.active_overrides[-MAX_OVERRIDES:]
        return {"success": True, "override": override}

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
        return {
            "success": True,
            "package": {
                "gm_state": gm_state.to_dict(),
                "world_data": dict(world_data),
                "export_tick": gm_state.tick,
                "_format_version": 1,
            },
        }

    @staticmethod
    def import_state(package: Dict[str, Any]) -> Dict[str, Any]:
        if "_format_version" not in package:
            return {"success": False, "reason": "invalid package format"}
        return {
            "success": True,
            "gm_state": package.get("gm_state"),
            "world_data": package.get("world_data"),
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
        return violations

    @staticmethod
    def normalize_state(gm_state: GMState) -> GMState:
        overrides = list(gm_state.active_overrides)
        if len(overrides) > MAX_OVERRIDES:
            overrides = overrides[-MAX_OVERRIDES:]
        history = list(gm_state.edit_history)
        if len(history) > MAX_EDIT_HISTORY:
            history = history[-MAX_EDIT_HISTORY:]
        return GMState(
            gm_id=gm_state.gm_id,
            permissions=GMPermissions.from_dict(gm_state.permissions.to_dict()),
            active_overrides=overrides,
            edit_history=history,
            tick=gm_state.tick,
        )
