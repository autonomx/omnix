from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return str(value or "")


def seed_followup_arcs(
    *,
    existing_arcs: Mapping[str, Any],
    followup_hooks: Iterable[Mapping[str, Any]],
    turn_index: int,
    max_active_arcs: int = 3,
) -> Dict[str, Any]:
    arcs = {
        str(arc_id): dict(_safe_dict(arc))
        for arc_id, arc in _safe_dict(existing_arcs).items()
    }

    active_count = sum(
        1
        for arc in arcs.values()
        if _safe_dict(arc).get("status") not in {"completed", "failed", "abandoned"}
    )

    seeded_events: List[Dict[str, Any]] = []

    hooks = sorted(
        [_safe_dict(hook) for hook in _safe_list(list(followup_hooks))],
        key=lambda item: int(item.get("priority") or 0),
        reverse=True,
    )

    for hook in hooks:
        if active_count >= max_active_arcs:
            break

        arc_id = _safe_str(hook.get("arc_id"))
        if not arc_id or arc_id in arcs:
            continue

        arcs[arc_id] = {
            "arc_id": arc_id,
            "title": _safe_str(hook.get("title") or hook.get("summary") or arc_id),
            "status": "active",
            "current_stage": "seeded_followup",
            "started_turn": turn_index,
            "last_progress_turn": turn_index,
            "progress_count": 0,
            "source_hook_id": hook.get("id"),
            "history": [
                {
                    "turn": turn_index,
                    "type": "arc_seeded",
                    "summary": hook.get("summary", ""),
                }
            ],
        }
        active_count += 1

        seeded_events.append(
            {
                "type": "story_arc",
                "subtype": "arc_seeded",
                "arc_id": arc_id,
                "source_hook_id": hook.get("id"),
                "summary": hook.get("summary", ""),
                "meaningful_progress": True,
                "progress_category": "story_arc_seeded",
            }
        )

    return {
        "ok": True,
        "story_arcs": arcs,
        "seeded_events": seeded_events,
        "seeded_count": len(seeded_events),
    }