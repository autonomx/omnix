from __future__ import annotations

from typing import Any, Dict, List, Set

from app.rpg.lore.state import get_lore_entry, is_lore_known_by
from app.rpg.memory.causal_retrieval import retrieve_causal_memories
from app.rpg.story_arcs.state import get_story_arc


MAX_DIALOGUE_LORE = 10
MAX_DIALOGUE_ARCS = 10
MAX_DIALOGUE_MEMORIES = 10


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _memory_lore_id(row):
    facts = _safe_dict(row.get("facts"))
    metadata = _safe_dict(row.get("metadata"))
    details = _safe_dict(row.get("details"))
    return (
        _safe_str(facts.get("lore_id"))
        or _safe_str(row.get("lore_id"))
        or _safe_str(metadata.get("lore_id"))
        or _safe_str(details.get("lore_id"))
    )


def _known_lore_ids_from_memory(
    simulation_state: Dict[str, Any],
    npc_id: str,
) -> Set[str]:
    rows = retrieve_causal_memories(
        simulation_state,
        npc_id,
        tags=["lore", "rumor", "story"],
        max_items=MAX_DIALOGUE_MEMORIES,
    )
    lore_ids: Set[str] = set()
    for row in rows:
        lore_id = _memory_lore_id(row)
        if lore_id:
            lore_ids.add(lore_id)
    return lore_ids


def _memory_event_ids(
    simulation_state: Dict[str, Any],
    npc_id: str,
    *,
    tags: List[str] | None = None,
) -> List[str]:
    rows = retrieve_causal_memories(
        simulation_state,
        npc_id,
        tags=tags or [],
        max_items=MAX_DIALOGUE_MEMORIES,
    )
    return [
        str(row.get("event_id"))
        for row in rows
        if row.get("event_id")
    ][:MAX_DIALOGUE_MEMORIES]


def _can_discuss_lore(
    simulation_state: Dict[str, Any],
    npc_id: str,
    lore_id: str,
) -> Dict[str, Any]:
    entry = get_lore_entry(simulation_state, lore_id)
    if not entry:
        return {
            "ok": False,
            "reason": "lore_missing",
            "lore_id": lore_id,
        }

    known_by = is_lore_known_by(simulation_state, lore_id, npc_id)
    remembered_lore = lore_id in _known_lore_ids_from_memory(simulation_state, npc_id)
    revealed = bool(entry.get("revealed_to_player"))
    truth_status = str(entry.get("truth_status") or "unknown")

    if truth_status == "secret" and not known_by and not remembered_lore:
        return {
            "ok": False,
            "reason": "secret_not_known",
            "lore_id": lore_id,
            "truth_status": truth_status,
        }

    if not known_by and not remembered_lore and not revealed:
        return {
            "ok": False,
            "reason": "not_known_or_revealed",
            "lore_id": lore_id,
            "truth_status": truth_status,
        }

    must_mark_as_rumor = truth_status in {"rumor", "myth", "unknown"} or remembered_lore
    return {
        "ok": True,
        "reason": "available",
        "lore_id": lore_id,
        "truth_status": truth_status,
        "known_by": known_by,
        "remembered_lore": remembered_lore,
        "revealed_to_player": revealed,
        "must_mark_as_rumor": must_mark_as_rumor,
    }


def build_arc_dialogue_context(
    simulation_state: Dict[str, Any],
    npc_id: str,
    *,
    arc_id: str = "",
    topic_lore_id: str = "",
) -> Dict[str, Any]:
    npc_id = str(npc_id or "")
    relationship = simulation_state.get("social_state", {}).get("relationships", {}).get(npc_id, {})
    social_stance = str(relationship.get("last_stance") or "")
    if not social_stance:
        if int(relationship.get("fear") or 0) >= 50:
            social_stance = "fearful"
        elif int(relationship.get("hostility") or 0) >= 50:
            social_stance = "hostile"
        elif int(relationship.get("trust") or 0) >= 40:
            social_stance = "trusting"
        else:
            social_stance = "neutral"

    lore_state = _safe_dict(simulation_state.get("lore_state"))
    entries = _safe_dict(lore_state.get("entries"))
    arc_state = _safe_dict(simulation_state.get("story_arc_state"))
    arcs = _safe_dict(arc_state.get("arcs"))

    candidate_lore_ids: List[str] = []
    if topic_lore_id:
        candidate_lore_ids.append(topic_lore_id)
    if arc_id:
        arc = get_story_arc(simulation_state, arc_id) or {}
        candidate_lore_ids.extend(_safe_list(arc.get("linked_lore")))
    candidate_lore_ids.extend(
        lore_id
        for lore_id, entry in entries.items()
        if npc_id in set(_safe_list(_safe_dict(entry).get("known_by")))
    )
    candidate_lore_ids.extend(sorted(_known_lore_ids_from_memory(simulation_state, npc_id)))

    seen_lore: Set[str] = set()
    known_lore = []
    rejected_lore = []
    for lore_id in candidate_lore_ids:
        lore_id = str(lore_id or "")
        if not lore_id or lore_id in seen_lore:
            continue
        seen_lore.add(lore_id)
        decision = _can_discuss_lore(simulation_state, npc_id, lore_id)
        entry = get_lore_entry(simulation_state, lore_id) or {}
        if decision.get("ok"):
            known_lore.append(
                {
                    "lore_id": lore_id,
                    "title": entry.get("title"),
                    "kind": entry.get("kind"),
                    "truth_status": entry.get("truth_status"),
                    "summary": entry.get("summary"),
                    "tags": list(entry.get("tags") or [])[:10],
                    "must_mark_as_rumor": bool(decision.get("must_mark_as_rumor")),
                    "source_reason": decision.get("reason"),
                }
            )
        else:
            rejected_lore.append(decision)
        if len(known_lore) >= MAX_DIALOGUE_LORE:
            break

    candidate_arc_ids: List[str] = []
    if arc_id:
        candidate_arc_ids.append(arc_id)
    for current_arc_id, arc in arcs.items():
        arc = _safe_dict(arc)
        if npc_id in set(_safe_list(arc.get("linked_entities"))):
            candidate_arc_ids.append(str(current_arc_id))
        if any(lore.get("lore_id") in set(_safe_list(arc.get("linked_lore"))) for lore in known_lore):
            candidate_arc_ids.append(str(current_arc_id))

    known_arcs = []
    seen_arcs: Set[str] = set()
    memory_event_ids = _memory_event_ids(simulation_state, npc_id, tags=["story", "rumor", "warning", "bandit"])
    for current_arc_id in candidate_arc_ids:
        current_arc_id = str(current_arc_id or "")
        if not current_arc_id or current_arc_id in seen_arcs:
            continue
        seen_arcs.add(current_arc_id)
        arc = get_story_arc(simulation_state, current_arc_id)
        if not arc:
            continue
        has_known_lore_link = any(lore.get("lore_id") in set(_safe_list(arc.get("linked_lore"))) for lore in known_lore)
        linked_entity = npc_id in set(_safe_list(arc.get("linked_entities")))
        if not has_known_lore_link and not linked_entity and current_arc_id != arc_id:
            continue
        known_arcs.append(
            {
                "arc_id": current_arc_id,
                "title": arc.get("title"),
                "status": arc.get("status"),
                "stage": arc.get("stage"),
                "pressure": arc.get("pressure"),
                "linked_lore": list(arc.get("linked_lore") or [])[:10],
                "linked_entities": list(arc.get("linked_entities") or [])[:10],
                "source": "linked_entity" if linked_entity else "known_lore",
            }
        )
        if len(known_arcs) >= MAX_DIALOGUE_ARCS:
            break

    can_discuss = bool(known_lore or known_arcs or memory_event_ids)
    if social_stance == "hostile" and int(relationship.get("trust") or 0) < 0:
        can_discuss = False

    return {
        "ok": True,
        "npc_id": npc_id,
        "arc_id": arc_id,
        "topic_lore_id": topic_lore_id,
        "can_discuss": can_discuss,
        "social_stance": social_stance,
        "known_lore": known_lore,
        "known_story_arcs": known_arcs,
        "relevant_memory_event_ids": memory_event_ids,
        "rejected_lore": rejected_lore[:10],
        "rumor_permissions": {
            "can_discuss": can_discuss,
            "must_mark_as_rumor": any(row.get("must_mark_as_rumor") for row in known_lore),
        },
        "bounded": {
            "max_lore": MAX_DIALOGUE_LORE,
            "max_arcs": MAX_DIALOGUE_ARCS,
            "max_memories": MAX_DIALOGUE_MEMORIES,
        },
    }