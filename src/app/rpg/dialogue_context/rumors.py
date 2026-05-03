from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List

from app.rpg.lore.state import get_lore_entry
from app.rpg.memory.observation import record_told_memory
from app.rpg.spatial.audibility import audible_entities_from

MAX_RUMOR_HEARERS = 12


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _stable_rumor_event_id(
    *,
    speaker_id: str,
    lore_id: str,
    summary: str,
    turn_index: int,
) -> str:
    payload = json.dumps(
        {
            "speaker_id": speaker_id,
            "lore_id": lore_id,
            "summary": summary,
            "turn_index": int(turn_index or 0),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
    return f"rumor:{digest}"


def _resolve_hearers(
    simulation_state: Dict[str, Any],
    speaker_id: str,
    explicit_hearers: List[str] | None = None,
) -> List[str]:
    if explicit_hearers is not None:
        return [
            str(item)
            for item in explicit_hearers
            if str(item) and str(item) != speaker_id
        ][:MAX_RUMOR_HEARERS]

    graph = _safe_dict(simulation_state.get("spatial_graph"))
    try:
        rows = audible_entities_from(graph, speaker_id)
    except Exception:
        rows = []

    hearers: List[str] = []
    for row in rows:
        if isinstance(row, dict):
            entity_id = str(row.get("entity_id") or row.get("id") or "")
        else:
            entity_id = str(row or "")
        if entity_id and entity_id != speaker_id and entity_id not in hearers:
            hearers.append(entity_id)
        if len(hearers) >= MAX_RUMOR_HEARERS:
            break
    return hearers


def propagate_rumor(
    simulation_state: Dict[str, Any],
    *,
    speaker_id: str,
    lore_id: str,
    summary: str,
    turn_index: int = 0,
    explicit_hearers: List[str] | None = None,
) -> Dict[str, Any]:
    speaker_id = str(speaker_id or "")
    lore_id = str(lore_id or "")
    summary = str(summary or "")
    if not speaker_id:
        return {"ok": False, "reason": "missing_speaker_id"}
    if not lore_id:
        return {"ok": False, "reason": "missing_lore_id"}
    if not summary:
        return {"ok": False, "reason": "missing_summary"}

    lore = get_lore_entry(simulation_state, lore_id)
    if not lore:
        return {"ok": False, "reason": "lore_missing", "lore_id": lore_id}

    truth_status_before = lore.get("truth_status")
    event_id = _stable_rumor_event_id(
        speaker_id=speaker_id,
        lore_id=lore_id,
        summary=summary,
        turn_index=turn_index,
    )
    hearers = _resolve_hearers(
        simulation_state,
        speaker_id,
        explicit_hearers=explicit_hearers,
    )

    memory_results = []
    for hearer_id in hearers:
        result = record_told_memory(
            simulation_state,
            hearer_id,
            speaker_id=speaker_id,
            event_id=event_id,
            summary=summary,
            facts={
                "lore_id": lore_id,
                "truth_status": truth_status_before,
                "rumor": True,
            },
            tags=["rumor", "lore", "story"],
            verified=False,
            turn_index=turn_index,
        )
        # Ensure lore_id is stored in the memory row for retrieval
        causal_memory_state = simulation_state.setdefault("causal_memory_state", {})
        memories = causal_memory_state.setdefault(hearer_id, [])
        if memories:
            memories[-1]["lore_id"] = lore_id
        memory_results.append(result)

    truth_status_after = (get_lore_entry(simulation_state, lore_id) or {}).get("truth_status")
    return {
        "ok": True,
        "reason": "rumor_propagated",
        "event_id": event_id,
        "speaker_id": speaker_id,
        "lore_id": lore_id,
        "summary": summary,
        "hearers": hearers,
        "memory_results": memory_results,
        "truth_status_before": truth_status_before,
        "truth_status_after": truth_status_after,
        "truth_promoted": truth_status_before != truth_status_after,
        "bounded": {"max_hearers": MAX_RUMOR_HEARERS},
    }