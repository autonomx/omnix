from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Dict, List, Tuple


PLAYER_AGENT_CONTEXT_VERSION = "player_agent_context_v1"


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _short_text(value: Any, max_chars: int = 500) -> str:
    text = _safe_str(value).strip()
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "...[truncated]"
    return text


def compact_json(value: Any, max_chars: int = 6000) -> str:
    text = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    if len(text) > max_chars:
        return text[:max_chars] + "...[truncated]"
    return text


def prompt_section_metrics(sections: Dict[str, str]) -> Dict[str, Any]:
    by_section: Dict[str, Dict[str, Any]] = {}
    total_chars = 0
    for name, value in sections.items():
        text = value if isinstance(value, str) else str(value)
        chars = len(text)
        total_chars += chars
        by_section[name] = {
            "chars": chars,
            "estimated_tokens": round(chars / 4.0, 1),
        }
    return {
        "total_chars": total_chars,
        "estimated_tokens": round(total_chars / 4.0, 1),
        "by_section": by_section,
    }


def _compact_scene(session_or_state: Dict[str, Any]) -> Dict[str, Any]:
    state = _safe_dict(session_or_state.get("simulation_state") or session_or_state.get("state") or session_or_state)
    scene = _safe_dict(state.get("scene"))
    location = _safe_dict(state.get("location"))
    return {
        "location": (
            _safe_str(state.get("current_location"))
            or _safe_str(location.get("name"))
            or _safe_str(scene.get("location"))
            or _safe_str(scene.get("name"))
        ),
        "title": _safe_str(scene.get("title") or scene.get("name")),
        "summary": _short_text(
            scene.get("summary") or scene.get("description") or state.get("scene_summary"),
            700,
        ),
    }


def _compact_npcs(session_or_state: Dict[str, Any], limit: int = 6) -> List[Dict[str, Any]]:
    state = _safe_dict(session_or_state.get("simulation_state") or session_or_state.get("state") or session_or_state)
    present = (
        _safe_list(state.get("present_npcs"))
        or _safe_list(state.get("nearby_npcs"))
        or _safe_list(state.get("visible_npcs"))
    )
    npcs_by_id = _safe_dict(state.get("npcs"))
    compact: List[Dict[str, Any]] = []

    def npc_id_of(value: Any) -> str:
        if isinstance(value, str):
            return value
        item = _safe_dict(value)
        return _safe_str(item.get("id") or item.get("npc_id") or item.get("name"))

    for value in present[:limit]:
        npc_id = npc_id_of(value)
        record = _safe_dict(npcs_by_id.get(npc_id)) or _safe_dict(value)
        compact.append(
            {
                "id": npc_id,
                "name": _safe_str(record.get("name")) or npc_id,
                "role": _safe_str(record.get("role") or record.get("occupation")),
                "mood": _safe_str(record.get("mood") or record.get("emotional_state")),
            }
        )

    if not compact and npcs_by_id:
        for npc_id, record_any in list(npcs_by_id.items())[:limit]:
            record = _safe_dict(record_any)
            compact.append(
                {
                    "id": str(npc_id),
                    "name": _safe_str(record.get("name")) or str(npc_id),
                    "role": _safe_str(record.get("role") or record.get("occupation")),
                    "mood": _safe_str(record.get("mood") or record.get("emotional_state")),
                }
            )

    return [item for item in compact if item.get("id") or item.get("name")]


def _compact_recent_turns(transcript_tail: List[Dict[str, Any]], limit: int = 5) -> List[Dict[str, Any]]:
    rows = transcript_tail[-limit:] if isinstance(transcript_tail, list) else []
    compact: List[Dict[str, Any]] = []
    for row in rows:
        row_dict = _safe_dict(row)
        action = (
            _safe_str(row_dict.get("player_action"))
            or _safe_str(row_dict.get("player_input"))
            or _safe_str(_safe_dict(row_dict.get("selected_player_action")).get("action"))
        )
        result = (
            _safe_str(row_dict.get("resolved_narration"))
            or _safe_str(row_dict.get("narration"))
            or _safe_str(_safe_dict(row_dict.get("turn_contract")).get("resolved_result"))
        )
        compact.append(
            {
                "turn_index": row_dict.get("turn_index"),
                "action": _short_text(action, 220),
                "result": _short_text(result, 350),
            }
        )
    return compact


def _compact_objectives(latest_context: Dict[str, Any]) -> Dict[str, Any]:
    context = _safe_dict(latest_context)
    return {
        "active_objective": _short_text(context.get("active_objective") or context.get("objective"), 300),
        "known_goal": _short_text(context.get("known_goal") or context.get("goal"), 300),
        "strategy_hint": _short_text(context.get("strategy_hint"), 300),
        "active_objectives": _safe_list(context.get("active_objectives"))[:6],
        "quest_log_summary": _safe_dict(context.get("quest_log_summary")),
    }


def _compact_suggested_actions(latest_context: Dict[str, Any], limit: int = 8) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in _safe_list(_safe_dict(latest_context).get("suggested_actions"))[: max(1, int(limit or 8))]:
        row = _safe_dict(row)
        out.append(
            {
                "action_id": _safe_str(row.get("action_id")),
                "label": _short_text(row.get("label"), 120),
                "command": _short_text(row.get("command"), 260),
                "category": _safe_str(row.get("category")),
                "priority": row.get("priority"),
                "strategy_score": row.get("strategy_score"),
                "goal_pressure_score": row.get("goal_pressure_score"),
                "objective_id": _safe_str(row.get("objective_id")),
                "reason": _short_text(row.get("reason"), 160),
            }
        )
    return out


def build_player_agent_context_packet(
    *,
    session: Dict[str, Any],
    transcript_tail: List[Dict[str, Any]],
    latest_context: Dict[str, Any],
    strategy: str,
    action_diversity_window: int,
) -> Dict[str, Any]:
    """Compact context for the autoplay player-agent.

    The player-agent chooses a next action only. It should not receive full raw
    session/debug/report data or write narration.
    """
    session = _safe_dict(session)
    state = _safe_dict(session.get("simulation_state") or session.get("state") or session)
    return {
        "format_version": PLAYER_AGENT_CONTEXT_VERSION,
        "strategy": strategy,
        "scene": _compact_scene(state),
        "present_npcs": _compact_npcs(state, limit=6),
        "recent_turns": _compact_recent_turns(transcript_tail, limit=max(2, min(action_diversity_window, 6))),
        "objectives": _compact_objectives(latest_context),
        "suggested_actions": _compact_suggested_actions(latest_context, limit=8),
        "strategy_guidance": _safe_dict(latest_context.get("strategy_guidance")),
        "goal_pressure": _safe_dict(latest_context.get("goal_pressure")),
        "player_visible": {
            "status": _safe_str(_safe_dict(state.get("player")).get("status")),
            "location": _safe_str(state.get("current_location")),
        },
    }


def player_agent_output_schema_text() -> str:
    return (
        "{"
        '"action":"First-person action the player should take next.",'
        '"intent":"short intent label",'
        '"target":"optional target NPC/object/location",'
        '"reason":"brief tactical reason"'
        "}"
    )


def build_player_agent_messages(
    *,
    context_packet: Dict[str, Any],
    max_context_chars: int = 5000,
) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
    context_json = compact_json(context_packet, max_chars=max_context_chars)
    schema = player_agent_output_schema_text()
    system = (
        "You are an autoplay player for an RPG test harness. "
        "Choose one concrete next player action. Return JSON only. "
        "Do not narrate. Do not explain outside JSON. "
        "Do not repeat a recent action unless it clearly advances the objective. "
        "Prefer actions that create strict meaningful progress: objective completion, quest log changes, travel/location changes, story arc changes, service completion, combat lifecycle changes, or grounded clue discovery. "
        "Do not waste turns on vague listening, nodding, observing, maintaining eye contact, or asking for generic elaboration. "
        "When goal_pressure is active, choose one of the suggested concrete actions or a similarly direct action likely to complete/advance a quest within 1-3 turns."
    )
    user = (
        "Choose the next player action from this compact context.\n\n"
        "Decision policy:\n"
        "1. If active objectives exist, choose an action that directly advances or completes one.\n"
        "2. If no active objective exists, seek a new quest hook or travel to a lead.\n"
        "3. Prefer concrete verbs: report, accept, travel, inspect, search, confront, buy/rent, follow, ask specifically.\n"
        "4. Avoid passive micro-actions unless paired with a concrete progress verb.\n\n"
        "CONTEXT_JSON:\n"
        f"{context_json}\n\n"
        "Return exactly this JSON shape:\n"
        f"{schema}"
    )
    sections = {
        "system": system,
        "context_packet": context_json,
        "output_schema": schema,
    }
    return (
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        prompt_section_metrics(sections),
    )


def player_agent_cache_key(
    *,
    context_packet: Dict[str, Any],
    strategy: str,
) -> str:
    raw = json.dumps(
        {
            "strategy": strategy,
            "context": context_packet,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalize_player_agent_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = deepcopy(_safe_dict(payload))
    action = (
        _safe_str(payload.get("action"))
        or _safe_str(payload.get("player_action"))
        or _safe_str(payload.get("next_action"))
    )
    return {
        "ok": bool(action.strip()),
        "action": action.strip(),
        "intent": _safe_str(payload.get("intent")),
        "target": _safe_str(payload.get("target")),
        "reason": _short_text(payload.get("reason"), 300),
        "raw": payload,
    }