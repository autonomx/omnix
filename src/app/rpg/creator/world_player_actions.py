"""Phase 4.5 — Player Action → Simulation Feedback.

Provides deterministic action → consequence mapping so that player input
feeds into the existing effects/incident pipeline instead of bypassing it.

Design principles:
- Player actions produce **consequences**, not direct pressure mutations.
  The effects system applies those consequences on the next tick.
- Faction escalation is scoped to *related* factions (those connected
  to the target thread), not all factions globally.
- Every action carries a stable action_id so duplicate submissions are
  silently ignored (idempotency protection).

The gameplay loop enabled by this module is:

    Scene → Player Action → Consequences → Effects → New World State → New Scenes

All mutations are fully deterministic given the same (state, action) pair.
"""

from __future__ import annotations

from typing import Any

# Phase 8: player-facing action summaries
from app.rpg.player import ensure_player_state


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safe_dict(value: Any) -> dict[str, Any]:
    """Return *value* if it is already a dict, otherwise ``{}``."""
    if isinstance(value, dict):
        return value
    return {}


def _safe_list(value: Any) -> list[Any]:
    """Return *value* if it is already a list, otherwise ``[]``."""
    if isinstance(value, list):
        return value
    return []


def _safe_str(value: Any) -> str:
    """Return *value* as a string."""
    if value is None:
        return ""
    return str(value)


def _cap(value: int, lo: int = 0, hi: int = 5) -> int:
    """Clamp *value* to [lo, hi]."""
    return max(lo, min(hi, value))


def _infer_affected_npc_ids(
    simulation_state: dict[str, Any],
    location_id: str = "",
    faction_id: str = "",
    target_id: str = "",
) -> list[str]:
    """Infer NPC IDs affected by an action based on npc_index."""
    simulation_state = simulation_state or {}
    npc_index = simulation_state.get("npc_index") or {}
    affected = []

    for npc_id, npc in sorted(npc_index.items()):
        npc_loc = _safe_str(npc.get("location_id"))
        npc_faction = _safe_str(npc.get("faction_id"))
        if location_id and npc_loc == location_id:
            affected.append(npc_id)
            continue
        if faction_id and npc_faction == faction_id:
            affected.append(npc_id)
            continue
        if target_id and npc_id == target_id:
            affected.append(npc_id)

    return sorted(set(affected))


# ---------------------------------------------------------------------------
# Action types
# ---------------------------------------------------------------------------

INTERVENE_THREAD = "intervene_thread"
SUPPORT_FACTION = "support_faction"
ESCALATE_CONFLICT = "escalate_conflict"
BETRAY_FACTION = "betray_faction"

VALID_ACTION_TYPES = {
    INTERVENE_THREAD,
    SUPPORT_FACTION,
    ESCALATE_CONFLICT,
    BETRAY_FACTION,
}


# ---------------------------------------------------------------------------
# Core: action → consequences (NOT direct mutations)
# ---------------------------------------------------------------------------


def apply_player_action(
    state: dict[str, Any],
    action: dict[str, Any],
) -> dict[str, Any]:
    """Process a player action and append consequences/events to state.

    **Important:** This function does *not* directly mutate pressure values.
    It appends structured consequences to state["consequences"] which are
    then consumed by the effects system (``world_effects.py``) on the next
    simulation tick.  This preserves the causality chain:

        action → consequence → effect → next-tick mutation → diff

    Parameters
    ----------
    state :
        The current ``simulation_state`` dict.
        Expected keys include: threads, factions, locations, events,
        consequences, active_effects, incidents, policy_reactions.
    action :
        Dict with keys:
        - ``type``: one of VALID_ACTION_TYPES
        - ``target_id`` (or ``target``): entity id to act upon
        - ``action_id`` (optional): dedup key for idempotency

    Returns
    -------
    dict
        A new simulation state (deep-copied) with appended consequences
        and events.  The action_diff key records the action metadata
        separately for causality tracking.
    """
    import copy

    state = copy.deepcopy(state)

    action_type = action.get("type", "")
    target_id = action.get("target_id") or action.get("target")
    action_id = action.get("action_id")

    # ── Idempotency guard ─────────────────────────────────────────────
    applied_ids: list[str] = _safe_list(state.get("applied_actions"))
    if action_id and action_id in applied_ids:
        return state  # already applied — idempotent no-op

    threads = _safe_dict(state.get("threads"))
    factions = _safe_dict(state.get("factions"))
    events = _safe_list(state.get("events"))
    consequences = _safe_list(state.get("consequences"))

    action_applied = False
    action_diff: dict[str, Any] = {
        "action_type": action_type,
        "target_id": target_id,
        "action_id": action_id,
        "consequences_added": [],
    }

    # ── Rule: intervene_thread → consequence to reduce thread pressure ─
    if action_type == INTERVENE_THREAD and target_id in threads:
        old_pressure = threads[target_id].get("pressure", 0)
        new_pressure = _cap(old_pressure - 2)
        magnitude = new_pressure - old_pressure  # negative

        consequences.append({
            "type": "player_intervention",
            "origin": "player_action",
            "action_type": action_type,
            "target_id": target_id,
            "magnitude": magnitude,
            "summary": f"Player intervened in thread '{target_id}' (pressure {old_pressure} → {new_pressure})",
        })
        action_diff["consequences_added"].append("player_intervention")

        events.append({
            "type": "player_intervention",
            "origin": "player_action",
            "action_type": action_type,
            "actor": "player",
            "target_id": target_id,
            "target_kind": "thread",
            "location_id": "",
            "faction_id": "",
            "affected_npc_ids": _infer_affected_npc_ids(
                simulation_state=state,
                target_id=target_id,
            ),
            "summary": f"Player intervened in thread '{target_id}' (pressure {old_pressure} → {new_pressure})",
            "severity": "positive",
            "salience": 0.8,
        })
        action_applied = True

    # ── Rule: support_faction → consequence to stabilize faction ─────
    if action_type == SUPPORT_FACTION and target_id in factions:
        old_pressure = factions[target_id].get("pressure", 0)
        new_pressure = _cap(old_pressure - 1)
        magnitude = new_pressure - old_pressure  # negative

        consequences.append({
            "type": "player_faction_support",
            "origin": "player_action",
            "action_type": action_type,
            "target_id": target_id,
            "magnitude": magnitude,
            "summary": f"Player supported faction '{target_id}' (pressure {old_pressure} → {new_pressure})",
        })
        action_diff["consequences_added"].append("player_faction_support")

        events.append({
            "type": "player_support",
            "origin": "player_action",
            "action_type": action_type,
            "actor": "player",
            "target_id": target_id,
            "target_kind": "faction",
            "location_id": "",
            "faction_id": target_id,
            "affected_npc_ids": _infer_affected_npc_ids(
                simulation_state=state,
                faction_id=target_id,
            ),
            "summary": f"Player supported faction '{target_id}' (pressure {old_pressure} → {new_pressure})",
            "severity": "positive",
            "salience": 0.8,
        })
        action_applied = True

    # ── Rule: escalate_conflict → consequence scoped to related factions
    if action_type == ESCALATE_CONFLICT and target_id in threads:
        old_pressure = threads[target_id].get("pressure", 0)
        new_pressure = _cap(old_pressure + 2)
        magnitude = new_pressure - old_pressure  # positive

        # Determine related factions from thread metadata
        thread_data = threads[target_id] if isinstance(thread_data := threads.get(target_id), dict) else {}
        # faction_ids may be stored in the simulation state under various keys
        related_factions = _safe_list(thread_data.get("faction_ids"))
        if not related_factions:
            # Fallback: factions whose pressure > 0 are considered "involved"
            related_factions = [
                fid for fid, fs in factions.items()
                if _safe_dict(fs).get("pressure", 0) > 0
            ]

        consequences.append({
            "type": "player_escalation",
            "origin": "player_action",
            "action_type": action_type,
            "target_id": target_id,
            "magnitude": magnitude,
            "related_factions": related_factions,
            "summary": f"Player escalated conflict in thread '{target_id}' (pressure {old_pressure} → {new_pressure})",
        })
        action_diff["consequences_added"].append("player_escalation")

        events.append({
            "type": "player_escalation",
            "origin": "player_action",
            "action_type": action_type,
            "actor": "player",
            "target_id": target_id,
            "target_kind": "thread",
            "location_id": "",
            "faction_id": "",
            "related_factions": related_factions,
            "affected_npc_ids": _infer_affected_npc_ids(
                simulation_state=state,
                target_id=target_id,
            ),
            "summary": f"Player escalated conflict in thread '{target_id}' (pressure {old_pressure} → {new_pressure})",
            "severity": "negative",
            "salience": 0.9,
        })
        action_applied = True

    # ── Rule: betray_faction → emit betrayal event
    if action_type == BETRAY_FACTION and target_id:
        event = {
            "type": "betrayal",
            "origin": "player_action",
            "action_type": action_type,
            "actor": "player",
            "source_id": "player",
            "target_id": target_id,
            "target_kind": "faction",
            "faction_id": target_id,
            "location_id": "",
            "affected_npc_ids": _infer_affected_npc_ids(
                simulation_state=state,
                faction_id=target_id,
            ),
            "summary": f"Player betrayed faction '{target_id}'.",
            "severity": "negative",
            "salience": 0.9,
        }
        events.append(event)
        action_diff["consequences_added"].append("betrayal")
        action_applied = True

    # ── Fallback: unknown action type ──────────────────────────────────
    if not action_applied and action_type:
        events.append({
            "type": "unknown_action",
            "origin": "player_action",
            "action_type": action_type,
            "target_id": target_id,
            "summary": f"Unhandled action type: {action_type}",
            "severity": "neutral",
        })

    # ── Record action_id for dedup ─────────────────────────────────────
    if action_id:
        state["applied_actions"] = applied_ids + [action_id]

    # Write back
    state["events"] = events
    state["consequences"] = consequences
    state["action_diff"] = action_diff  # new key for causality tracking

    # Phase 7: add debug reason to action_diff
    action_diff["debug_reason"] = {
        "action_type": action_type,
        "target_id": target_id,
        "events_added_count": len(events),
        "consequences_added_count": len(action_diff.get("consequences_added") or []),
    }

    # Phase 8: lightweight player-facing action summary
    state = ensure_player_state(state)
    player_state = state["player_state"]
    objectives = list(player_state.get("active_objectives") or [])
    objectives.append({
        "objective_id": f"obj:{action_type}:{target_id}",
        "type": action_type,
        "target_id": target_id,
        "status": "active",
        "tick": int(state.get("tick", 0) or 0),
    })
    player_state["active_objectives"] = objectives[-20:]

    return state


# ---------------------------------------------------------------------------
# Status helpers (mirror world_simulation for consistency)
# ---------------------------------------------------------------------------


def _thread_status(pressure: int) -> str:
    if pressure <= 1:
        return "low"
    if pressure <= 3:
        return "active"
    return "critical"


def _faction_status(pressure: int) -> str:
    if pressure == 0:
        return "stable"
    if pressure <= 2:
        return "watchful"
    return "strained"


def enrich_action_metadata(action: dict) -> dict:
    """Add difficulty_tier, skill_id, xp_category, target_difficulty to action."""
    action = dict(action or {})
    action_type = str(action.get("action_type") or action.get("type") or "")

    _SKILL_MAP = {
        "attack_melee": "swordsmanship", "attack_ranged": "archery",
        "persuade": "persuasion", "intimidate": "intimidation",
        "sneak": "stealth", "investigate": "investigation",
        "hack": "hacking", "cast_spell": "magic",
        "block": "defense", "dodge": "defense", "parry": "swordsmanship",
    }
    _XP_CATEGORY = {
        "attack_melee": "combat", "attack_ranged": "combat",
        "block": "combat", "dodge": "combat", "parry": "combat",
        "persuade": "diplomacy", "intimidate": "diplomacy", "deceive": "diplomacy",
        "sneak": "stealth", "investigate": "exploration",
        "hack": "exploration", "cast_spell": "magic",
    }

    action.setdefault("difficulty_tier", 1)
    action.setdefault("skill_id", _SKILL_MAP.get(action_type, "investigation"))
    action.setdefault("xp_category", _XP_CATEGORY.get(action_type, "general"))
    action.setdefault("target_difficulty", "normal")

    return action