from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Tuple

from app.rpg.advisory.candidates import advisory_candidate_summary

try:
    from app.rpg.npc_evolution.target_grounding import ground_projection_target
except Exception:
    ground_projection_target = None


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _id_variants(value: Any) -> set[str]:
    raw = _safe_str(value).strip().lower()
    variants = {raw} if raw else set()
    if raw.startswith("npc:"):
        variants.add(raw.split("npc:", 1)[1])
    elif raw:
        variants.add(f"npc:{raw}")
    return {item for item in variants if item}


def _known_npcs(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    direct = _safe_dict(simulation_state.get("npcs"))
    if direct:
        return direct
    npc_progression = _safe_dict(simulation_state.get("npc_progression_state"))
    nested = _safe_dict(npc_progression.get("npcs"))
    if nested:
        return nested
    npc_profile = _safe_dict(simulation_state.get("npc_profile_state"))
    profile_npcs = _safe_dict(npc_profile.get("npcs"))
    if profile_npcs:
        return profile_npcs
    return {}


def _present_npc_items(simulation_state: Dict[str, Any]) -> List[Any]:
    simulation_state = _safe_dict(simulation_state)
    direct = (
        _safe_list(simulation_state.get("present_npcs"))
        or _safe_list(simulation_state.get("nearby_npcs"))
        or _safe_list(simulation_state.get("visible_npcs"))
    )
    if direct:
        return direct

    scene = _safe_dict(simulation_state.get("scene"))
    scene_items = (
        _safe_list(scene.get("present_npcs"))
        or _safe_list(scene.get("nearby_npcs"))
        or _safe_list(scene.get("visible_npcs"))
    )
    if scene_items:
        return scene_items

    contract = _safe_dict(simulation_state.get("turn_contract"))
    for section_key in ("resolved_action", "resolved_result"):
        section = _safe_dict(contract.get(section_key))
        current_location = _safe_dict(
            _safe_dict(section.get("location_state")).get("current_location")
        )
        present = _safe_list(current_location.get("present_npcs"))
        if present:
            return present

    return []


def _npc_id_from_present_item(item: Any) -> str:
    if isinstance(item, str):
        return item
    item_dict = _safe_dict(item)
    return (
        _safe_str(item_dict.get("id"))
        or _safe_str(item_dict.get("npc_id"))
        or _safe_str(item_dict.get("name"))
    )


def _canonical_npc_id(simulation_state: Dict[str, Any], candidate: str) -> str:
    candidate_variants = _id_variants(candidate)
    if not candidate_variants:
        return ""

    npcs = _known_npcs(simulation_state)
    for npc_id, record_any in npcs.items():
        record = _safe_dict(record_any)
        known = set()
        known.update(_id_variants(npc_id))
        known.update(_id_variants(record.get("id")))
        known.update(_id_variants(record.get("npc_id")))
        known.update(_id_variants(record.get("name")))
        known.update(_id_variants(record.get("display_name")))
        if candidate_variants & known:
            return str(npc_id)

    for item in _present_npc_items(simulation_state):
        present_id = _npc_id_from_present_item(item)
        if candidate_variants & _id_variants(present_id):
            canonical = _canonical_npc_id_from_known(simulation_state, present_id)
            return canonical or present_id

    return ""


def _canonical_npc_id_from_known(simulation_state: Dict[str, Any], candidate: str) -> str:
    candidate_variants = _id_variants(candidate)
    npcs = _known_npcs(simulation_state)
    for npc_id, record_any in npcs.items():
        record = _safe_dict(record_any)
        known = set()
        known.update(_id_variants(npc_id))
        known.update(_id_variants(record.get("id")))
        known.update(_id_variants(record.get("npc_id")))
        known.update(_id_variants(record.get("name")))
        if candidate_variants & known:
            return str(npc_id)
    return ""


def _npc_exists_or_is_present(simulation_state: Dict[str, Any], target: str) -> bool:
    return bool(_canonical_npc_id(simulation_state, target))


def _is_backed_by_turn(candidate: Dict[str, Any]) -> bool:
    backing = _safe_dict(candidate.get("backing"))
    action = _safe_str(backing.get("turn_contract_action"))
    return bool(action.strip())


def _ground_relationship_candidate_target(
    candidate: Dict[str, Any],
    simulation_state: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Ground relationship target before promotion validation.

    This uses the same deterministic target grounding rules as NPC evolution:
    known explicit target, role alias, name match, or single present NPC.
    """
    candidate = deepcopy(_safe_dict(candidate))
    payload = candidate.setdefault("payload", {})

    if ground_projection_target is not None:
        projection = {
            "candidate_id": candidate.get("candidate_id"),
            "kind": candidate.get("kind"),
            "payload": deepcopy(payload),
        }
        grounded_projection, grounding_result = ground_projection_target(
            projection=projection,
            simulation_state=simulation_state,
        )
        grounded_payload = _safe_dict(grounded_projection.get("payload"))
        grounded_target = _safe_str(
            grounded_payload.get("target")
            or grounded_payload.get("grounded_target")
            or grounding_result.get("npc_id")
        )
        if grounded_target:
            canonical = _canonical_npc_id(simulation_state, grounded_target) or grounded_target
            payload["target"] = canonical
            payload.setdefault("grounded_target", canonical)
            candidate["payload"] = payload
            candidate["target_grounding"] = {
                **grounding_result,
                "npc_id": canonical,
            }
            return candidate, candidate["target_grounding"]

        candidate["target_grounding"] = grounding_result
        return candidate, grounding_result

    # Fallback grounding if target_grounding module is unavailable.
    target = _safe_str(payload.get("target") or payload.get("npc") or payload.get("npc_id") or payload.get("owner"))
    canonical = _canonical_npc_id(simulation_state, target)
    if canonical:
        payload["target"] = canonical
        payload.setdefault("grounded_target", canonical)
        candidate["payload"] = payload
        candidate["target_grounding"] = {
            "grounded": True,
            "npc_id": canonical,
            "reason": "canonicalized_explicit_target",
            "original_target": target,
        }
        return candidate, candidate["target_grounding"]

    present = [_npc_id_from_present_item(item) for item in _present_npc_items(simulation_state)]
    present = [item for item in present if item]
    if len(set(item.lower() for item in present)) == 1:
        canonical = _canonical_npc_id(simulation_state, present[0]) or present[0]
        payload["target"] = canonical
        payload.setdefault("grounded_target", canonical)
        candidate["payload"] = payload
        candidate["target_grounding"] = {
            "grounded": True,
            "npc_id": canonical,
            "reason": "single_present_npc",
        }
        return candidate, candidate["target_grounding"]

    candidate["target_grounding"] = {
        "grounded": False,
        "npc_id": "",
        "reason": "no_deterministic_target",
    }
    return candidate, candidate["target_grounding"]


def _candidate_rejection_reason(
    candidate: Dict[str, Any],
    simulation_state: Dict[str, Any],
    current_turn: int,
) -> str:
    promotion = _safe_dict(candidate.get("promotion"))
    eligible_from = int(promotion.get("eligible_from_turn") or 0)
    if current_turn < eligible_from:
        return "__pending_not_eligible_until_future_turn__"
    if _safe_dict(candidate.get("safety")).get("contains_forbidden_authoritative_claim"):
        return "contains_forbidden_authoritative_claim"
    if not _is_backed_by_turn(candidate):
        return "not_backed_by_turn_contract"

    kind = _safe_str(candidate.get("kind"))
    payload = _safe_dict(candidate.get("payload"))

    if kind == "relationship_delta":
        target = _safe_str(
            payload.get("target")
            or payload.get("grounded_target")
            or payload.get("npc")
            or payload.get("npc_id")
            or payload.get("owner")
        )
        if not _npc_exists_or_is_present(simulation_state, target):
            return "relationship_target_not_present_or_unknown"
        try:
            delta = int(payload.get("delta") or 0)
        except Exception:
            return "relationship_delta_not_integer"
        if delta < -2 or delta > 2:
            return "relationship_delta_out_of_bounds"

    if kind == "memory":
        owner = _safe_str(payload.get("owner") or payload.get("npc") or payload.get("npc_id"))
        summary = _safe_str(payload.get("summary"))
        if not owner:
            return "memory_owner_missing"
        if not summary:
            return "memory_summary_missing"

    if kind == "world_signal":
        summary = _safe_str(payload.get("summary"))
        if not summary:
            return "world_signal_summary_missing"

    if kind == "future_hook":
        summary = _safe_str(payload.get("summary"))
        if not summary:
            return "future_hook_summary_missing"

    return ""


def _accepted_projection(candidate: Dict[str, Any]) -> Dict[str, Any]:
    kind = _safe_str(candidate.get("kind"))
    payload = deepcopy(_safe_dict(candidate.get("payload")))
    projection = {
        "candidate_id": candidate.get("candidate_id"),
        "kind": kind,
        "payload": payload,
        "source": "deferred_advisory_promotion",
    }
    if candidate.get("target_grounding"):
        projection["target_grounding"] = candidate.get("target_grounding")
    return projection


def promote_advisory_candidates(
    *,
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    current_turn: int,
    max_promotions_per_turn: int = 5,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Promote advisory candidates deterministically.

    Advisory candidates do not mutate authoritative RPG facts directly.
    This gate only creates bounded accepted projections that later deterministic
    systems can inspect.
    """
    runtime_state = deepcopy(runtime_state if isinstance(runtime_state, dict) else {})
    advisory_state = runtime_state.setdefault("deferred_advisory", {})
    candidates = _safe_list(advisory_state.get("candidates"))
    accepted = _safe_list(advisory_state.get("accepted"))
    rejected = _safe_list(advisory_state.get("rejected"))

    accepted_ids = {str(item.get("candidate_id")) for item in accepted if isinstance(item, dict)}
    rejected_ids = {str(item.get("candidate_id")) for item in rejected if isinstance(item, dict)}

    promoted_this_turn = 0
    decisions: List[Dict[str, Any]] = []
    updated_candidates: List[Dict[str, Any]] = []

    for candidate_raw in candidates:
        if not isinstance(candidate_raw, dict):
            continue
        candidate = deepcopy(candidate_raw)
        cid = str(candidate.get("candidate_id") or "")
        if not cid:
            updated_candidates.append(candidate)
            continue
        if cid in accepted_ids or cid in rejected_ids:
            updated_candidates.append(candidate)
            continue
        if promoted_this_turn >= max_promotions_per_turn:
            updated_candidates.append(candidate)
            continue

        if _safe_str(candidate.get("kind")) == "relationship_delta":
            candidate, grounding_result = _ground_relationship_candidate_target(
                candidate,
                simulation_state,
            )
            candidate.setdefault("promotion", {})["target_grounding"] = grounding_result

        reason = _candidate_rejection_reason(candidate, simulation_state, current_turn)
        if reason == "__pending_not_eligible_until_future_turn__":
            candidate["status"] = "pending"
            candidate.setdefault("promotion", {})["reason"] = "not_eligible_until_future_turn"
            decisions.append(
                {
                    "candidate_id": cid,
                    "status": "pending",
                    "reason": "not_eligible_until_future_turn",
                }
            )
            updated_candidates.append(candidate)
            continue

        if reason:
            candidate["status"] = "rejected"
            candidate.setdefault("promotion", {})["rejected"] = True
            candidate.setdefault("promotion", {})["reason"] = reason
            # Only add to permanent rejected list if not a timing issue
            if reason != "__pending_not_eligible_until_future_turn__":
                rejected.append(
                    {
                        "candidate_id": cid,
                        "turn_index": candidate.get("turn_index"),
                        "kind": candidate.get("kind"),
                        "reason": reason,
                        "rejected_at_turn": current_turn,
                        "target_grounding": candidate.get("target_grounding") or _safe_dict(candidate.get("promotion")).get("target_grounding") or {},
                    }
                )
            decisions.append(
                {
                    "candidate_id": cid,
                    "status": "rejected",
                    "reason": reason,
                    "target_grounding": candidate.get("target_grounding") or _safe_dict(candidate.get("promotion")).get("target_grounding") or {},
                }
            )
        else:
            candidate["status"] = "accepted"
            candidate.setdefault("promotion", {})["accepted"] = True
            candidate.setdefault("promotion", {})["reason"] = "accepted_by_deterministic_gate"
            candidate.setdefault("promotion", {})["promoted_at_turn"] = current_turn
            projection = _accepted_projection(candidate)
            accepted.append(
                {
                    "candidate_id": cid,
                    "turn_index": candidate.get("turn_index"),
                    "kind": candidate.get("kind"),
                    "projection": projection,
                    "accepted_at_turn": current_turn,
                    "reason": "accepted_by_deterministic_gate",
                    "target_grounding": candidate.get("target_grounding") or _safe_dict(candidate.get("promotion")).get("target_grounding") or {},
                }
            )
            decisions.append(
                {
                    "candidate_id": cid,
                    "status": "accepted",
                    "reason": "accepted_by_deterministic_gate",
                    "target_grounding": candidate.get("target_grounding") or _safe_dict(candidate.get("promotion")).get("target_grounding") or {},
                }
            )
            promoted_this_turn += 1
        updated_candidates.append(candidate)

    advisory_state["candidates"] = updated_candidates
    advisory_state["accepted"] = accepted
    advisory_state["rejected"] = rejected
    advisory_state["summary"] = {
        "candidates": advisory_candidate_summary(updated_candidates),
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
    }

    result = {
        "ok": True,
        "current_turn": current_turn,
        "promoted_this_turn": promoted_this_turn,
        "decisions": decisions,
        "summary": advisory_state["summary"],
    }
    return runtime_state, result