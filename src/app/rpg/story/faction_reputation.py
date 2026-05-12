from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return str(value or "")


def _reputation_tier(value: int) -> str:
    if value >= 5:
        return "trusted"
    if value >= 2:
        return "friendly"
    if value <= -5:
        return "hostile"
    if value <= -2:
        return "suspicious"
    return "neutral"


def apply_faction_deltas(
    *,
    faction_state: Mapping[str, Any],
    faction_deltas: Iterable[Mapping[str, Any]],
    turn_index: int,
) -> Dict[str, Any]:
    factions = {
        str(fid): dict(_safe_dict(data))
        for fid, data in _safe_dict(faction_state).items()
    }

    events: List[Dict[str, Any]] = []

    seen_delta_keys: set[tuple[str, int, str, int]] = set()

    for raw_delta in faction_deltas:
        delta = _safe_dict(raw_delta)
        faction_id = _safe_str(delta.get("faction_id"))
        if not faction_id:
            continue

        amount = int(delta.get("delta") or 0)
        if amount == 0:
            continue

        reason = _safe_str(delta.get("reason"))
        delta_key = (faction_id, int(turn_index), reason, amount)
        if delta_key in seen_delta_keys:
            continue
        seen_delta_keys.add(delta_key)

        row = factions.setdefault(
            faction_id,
            {
                "faction_id": faction_id,
                "reputation": 0,
                "tier": "neutral",
                "history": [],
            },
        )

        previous = int(row.get("reputation") or 0)
        current = max(-10, min(10, previous + amount))
        previous_tier = _reputation_tier(previous)
        current_tier = _reputation_tier(current)

        row["reputation"] = current
        row["tier"] = current_tier
        row.setdefault("history", []).append(
            {
                "turn": turn_index,
                "delta": amount,
                "from": previous,
                "to": current,
                "reason": reason,
            }
        )

        events.append(
            {
                "type": "faction_reputation",
                "faction_id": faction_id,
                "delta": amount,
                "from": previous,
                "to": current,
                "previous_tier": previous_tier,
                "tier": current_tier,
                "reason": reason,
                "meaningful_progress": True,
                "progress_category": "faction_reputation",
            }
        )

    return {
        "ok": True,
        "factions": factions,
        "events": events,
    }


def build_faction_reputation_summary(faction_state: Mapping[str, Any]) -> Dict[str, Any]:
    factions = _safe_dict(faction_state)
    rows = []

    for faction_id, raw in sorted(factions.items()):
        data = _safe_dict(raw)
        rows.append(
            {
                "faction_id": faction_id,
                "reputation": int(data.get("reputation") or 0),
                "tier": data.get("tier") or _reputation_tier(int(data.get("reputation") or 0)),
                "history_count": len(_safe_list(data.get("history"))),
                "recent_history": _safe_list(data.get("history"))[-5:],
            }
        )

    return {
        "format_version": "faction_reputation_summary_v1",
        "ok": bool(rows),
        "faction_count": len(rows),
        "factions": rows,
    }