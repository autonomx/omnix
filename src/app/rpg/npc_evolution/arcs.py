from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple


NPC_EVOLUTION_VERSION = "npc_evolution_arcs_v1"

ALLOWED_SIGNAL_KINDS = {
    "memory",
    "relationship_delta",
    "world_signal",
    "future_hook",
    "semantic_intent",
}

FORBIDDEN_EVOLUTION_MUTATION_KEYS = {
    "inventory",
    "items",
    "currency",
    "gold",
    "xp",
    "experience",
    "quest_status",
    "quest_completion",
    "combat_damage",
    "damage",
    "hit",
    "miss",
    "location",
    "travel",
    "service_purchase",
    "reward",
}


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _norm_id(value: Any) -> str:
    return _safe_str(value).strip().lower()


def _id_variants(value: Any) -> set[str]:
    normed = _norm_id(value)
    variants = {normed} if normed else set()
    if normed.startswith("npc:"):
        variants.add(normed.split("npc:", 1)[1])
    elif normed:
        variants.add(f"npc:{normed}")
    return {item for item in variants if item}


def canonical_npc_id(
    *,
    simulation_state: Dict[str, Any],
    npc_id: str,
) -> str:
    """Collapse npc:bran / bran / Bran to the canonical known NPC key."""
    variants = _id_variants(npc_id)
    if not variants:
        return ""

    npcs = _known_npcs(simulation_state)
    for known_id, record_any in npcs.items():
        record = _safe_dict(record_any)
        known_variants = set()
        known_variants.update(_id_variants(known_id))
        known_variants.update(_id_variants(record.get("id")))
        known_variants.update(_id_variants(record.get("npc_id")))
        known_variants.update(_id_variants(record.get("name")))
        known_variants.update(_id_variants(record.get("display_name")))
        if variants & known_variants:
            return str(known_id)

    for item in _present_npc_items(simulation_state):
        present_id = _npc_id_from_present_item(item)
        if variants & _id_variants(present_id):
            return present_id

    return npc_id


def _known_npcs(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """Return known NPC map across supported state shapes."""
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
    """Return present/nearby NPC list across supported state/contract shapes."""
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

    for contract_key in ("turn_contract", "contract"):
        contract = _safe_dict(simulation_state.get(contract_key))
        for section_key in ("resolved_action", "resolved_result"):
            section = _safe_dict(contract.get(section_key))
            current_location = _safe_dict(
                _safe_dict(section.get("location_state")).get("current_location")
            )
            present = _safe_list(current_location.get("present_npcs"))
            if present:
                return present

    return []


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _contains_forbidden_claim(value: Any) -> bool:
    text = _stable_json(value).lower()
    return any(key in text for key in FORBIDDEN_EVOLUTION_MUTATION_KEYS)


def evolution_signal_id(
    *,
    npc_id: str,
    turn_index: int,
    kind: str,
    payload: Dict[str, Any],
    projection_id: str = "",
) -> str:
    # Idempotency rule:
    # If a signal comes from an accepted advisory projection, the signal id must
    # be stable across later turns. Otherwise the same projection can be
    # re-consumed every turn and duplicate memories/hooks.
    if projection_id:
        raw = _stable_json(
            {
                "npc_id": npc_id,
                "kind": kind,
                "projection_id": projection_id,
            }
        )
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        return f"npc_evo:{npc_id}:{kind}:projection:{digest}"

    raw = _stable_json(
        {
            "npc_id": npc_id,
            "turn_index": turn_index,
            "kind": kind,
            "payload": payload,
        }
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"npc_evo:{npc_id}:{turn_index}:{kind}:{digest}"


def _extract_target_npc_id(projection: Dict[str, Any]) -> str:
    payload = _safe_dict(projection.get("payload"))
    kind = _safe_str(projection.get("kind"))

    if kind == "memory":
        return (
            _safe_str(payload.get("owner"))
            or _safe_str(payload.get("npc"))
            or _safe_str(payload.get("npc_id"))
            or _safe_str(payload.get("target"))
        )

    if kind == "relationship_delta":
        return (
            _safe_str(payload.get("target"))
            or _safe_str(payload.get("npc"))
            or _safe_str(payload.get("npc_id"))
            or _safe_str(payload.get("owner"))
        )

    return (
        _safe_str(payload.get("target"))
        or _safe_str(payload.get("npc"))
        or _safe_str(payload.get("npc_id"))
        or _safe_str(payload.get("owner"))
    )


def _npc_exists(simulation_state: Dict[str, Any], npc_id: str) -> bool:
    if not npc_id:
        return False
    npc_variants = _id_variants(npc_id)
    npcs = _known_npcs(simulation_state)
    known_variants = set()
    for key, record_any in npcs.items():
        record = _safe_dict(record_any)
        known_variants.update(_id_variants(key))
        known_variants.update(_id_variants(record.get("name")))
        known_variants.update(_id_variants(record.get("id")))
        known_variants.update(_id_variants(record.get("npc_id")))
    if npc_variants & known_variants:
        return True
    present = _present_npc_items(simulation_state)
    present_variants = set()
    for item in present:
        present_variants.update(_id_variants(_npc_id_from_present_item(item)))
    return bool(npc_variants & present_variants)


def _npc_id_from_present_item(item: Any) -> str:
    if isinstance(item, str):
        return item
    item_dict = _safe_dict(item)
    return (
        _safe_str(item_dict.get("id"))
        or _safe_str(item_dict.get("npc_id"))
        or _safe_str(item_dict.get("name"))
    )


def infer_npc_target_for_projection(
    *,
    projection: Dict[str, Any],
    simulation_state: Dict[str, Any],
) -> Tuple[str, str]:
    """Infer an NPC target from deterministic context.

    This is intentionally conservative:
    1. Use explicit projection payload target/owner/npc.
    2. Match known NPC names mentioned in the projection summary.
    3. If exactly one NPC is present, use that NPC.

    Returns (npc_id, reason).
    """
    projection = _safe_dict(projection)
    simulation_state = _safe_dict(simulation_state)
    payload = _safe_dict(projection.get("payload"))

    explicit = _extract_target_npc_id(projection)
    if explicit and _npc_exists(simulation_state, explicit):
        return explicit, "explicit_projection_target"

    summary = _projection_summary(projection).lower()
    npcs = _known_npcs(simulation_state)
    for npc_id, npc_record_any in npcs.items():
        npc_record = _safe_dict(npc_record_any)
        names = {
            str(npc_id).lower(),
            _safe_str(npc_record.get("name")).lower(),
        }
        names = {name for name in names if name}
        if any(name and name in summary for name in names):
            return str(npc_id), "matched_npc_name_in_summary"

    present = _present_npc_items(simulation_state)
    present_ids = [_npc_id_from_present_item(item) for item in present]
    present_ids = [npc_id for npc_id in present_ids if npc_id]
    unique_present = []
    seen = set()
    for npc_id in present_ids:
        marker = npc_id.lower()
        if marker in seen:
            continue
        seen.add(marker)
        unique_present.append(npc_id)

    if len(unique_present) == 1:
        return unique_present[0], "single_present_npc"

    return "", "npc_target_missing"


def _projection_summary(projection: Dict[str, Any]) -> str:
    payload = _safe_dict(projection.get("payload"))
    return (
        _safe_str(payload.get("summary"))
        or _safe_str(payload.get("description"))
        or _safe_str(payload.get("reason"))
        or _safe_str(payload.get("intent"))
    )


def normalize_projection_to_evolution_signal(
    *,
    projection: Dict[str, Any],
    simulation_state: Dict[str, Any],
    turn_index: int,
) -> Tuple[Dict[str, Any] | None, str]:
    """Convert an accepted advisory projection into a bounded evolution signal.

    Returns (signal, rejection_reason). Signal is None when rejected.
    """
    projection = deepcopy(_safe_dict(projection))
    simulation_state = _safe_dict(simulation_state)
    kind = _safe_str(projection.get("kind"))
    payload = deepcopy(_safe_dict(projection.get("payload")))

    if kind not in ALLOWED_SIGNAL_KINDS:
        return None, "unsupported_projection_kind"
    if _contains_forbidden_claim(payload):
        return None, "contains_forbidden_authoritative_claim"

    npc_id, target_reason = infer_npc_target_for_projection(
        projection=projection,
        simulation_state=simulation_state,
    )
    if not npc_id:
        return None, target_reason or "npc_target_missing"
    if not _npc_exists(simulation_state, npc_id):
        return None, "npc_target_not_found"
    npc_id = canonical_npc_id(simulation_state=simulation_state, npc_id=npc_id) or npc_id
    payload["target"] = npc_id
    payload["grounded_target"] = npc_id

    summary = _projection_summary(projection)
    if not summary:
        return None, "summary_missing"

    if kind == "relationship_delta":
        try:
            delta = int(payload.get("delta") or payload.get("magnitude") or 0)
        except Exception:
            return None, "relationship_delta_not_integer"
        delta = max(-2, min(2, delta))
        payload["delta"] = delta

    if kind == "memory":
        try:
            importance = float(payload.get("importance") or 0.5)
        except Exception:
            importance = 0.5
        payload["importance"] = max(0.0, min(1.0, importance))

    signal = {
        "format_version": NPC_EVOLUTION_VERSION,
        "signal_id": evolution_signal_id(
            npc_id=npc_id,
            turn_index=turn_index,
            kind=kind,
            payload=payload,
            projection_id=_safe_str(projection.get("candidate_id")),
        ),
        "npc_id": npc_id,
        "turn_index": int(turn_index),
        "kind": kind,
        "summary": summary[:500],
        "payload": payload,
        "source": "deferred_advisory_promotion",
        "target_inference": target_reason,
        "projection_id": projection.get("candidate_id"),
        "created_at": _now_iso(),
        "consumed": False,
    }
    return signal, ""


def npc_evolution_state(runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    runtime_state = runtime_state if isinstance(runtime_state, dict) else {}
    state = runtime_state.setdefault("npc_evolution", {})
    state.setdefault("signals", [])
    state.setdefault("arcs", {})
    state.setdefault("consumption_log", [])
    state.setdefault("summary", {})
    return state


def ingest_evolution_signals(
    *,
    runtime_state: Dict[str, Any],
    signals: List[Dict[str, Any]],
    max_signals: int = 300,
) -> Dict[str, Any]:
    runtime_state = runtime_state if isinstance(runtime_state, dict) else {}
    state = npc_evolution_state(runtime_state)
    existing = _safe_list(state.get("signals"))
    existing_ids = {_safe_str(item.get("signal_id")) for item in existing if isinstance(item, dict)}

    added = 0
    duplicates = 0
    for signal in signals if isinstance(signals, list) else []:
        if not isinstance(signal, dict):
            continue
        signal_id = _safe_str(signal.get("signal_id"))
        if not signal_id:
            continue
        if signal_id in existing_ids:
            duplicates += 1
            continue
        existing_ids.add(signal_id)
        existing.append(deepcopy(signal))
        added += 1

    if len(existing) > max_signals:
        existing = existing[-max_signals:]

    state["signals"] = existing
    state["summary"] = summarize_npc_evolution_state(runtime_state)
    return {
        "ok": True,
        "added": added,
        "duplicates": duplicates,
        "signal_total": len(existing),
        "summary": state["summary"],
    }


def summarize_npc_evolution_state(runtime_state: Dict[str, Any]) -> Dict[str, Any]:
    state = _safe_dict(_safe_dict(runtime_state).get("npc_evolution"))
    signals = _safe_list(state.get("signals"))
    arcs = _safe_dict(state.get("arcs"))
    consumed_projection_ids = _safe_list(state.get("consumed_projection_ids"))
    by_kind: Dict[str, int] = {}
    by_npc: Dict[str, int] = {}
    consumed = 0
    for signal in signals:
        signal_dict = _safe_dict(signal)
        kind = _safe_str(signal_dict.get("kind")) or "unknown"
        npc_id = _safe_str(signal_dict.get("npc_id")) or "unknown"
        by_kind[kind] = int(by_kind.get(kind) or 0) + 1
        by_npc[npc_id] = int(by_npc.get(npc_id) or 0) + 1
        if signal_dict.get("consumed"):
            consumed += 1
    milestone_total = 0
    duplicate_milestone_ids: List[str] = []
    out_of_bounds_axes: List[Dict[str, Any]] = []
    seen_milestones = set()
    arc_stages: Dict[str, str] = {}
    axes_by_npc: Dict[str, Dict[str, Any]] = {}
    milestones_by_npc: Dict[str, int] = {}
    for npc_id, arc_any in arcs.items():
        arc = _safe_dict(arc_any)
        arc_stages[str(npc_id)] = _safe_str(arc.get("arc_stage")) or "stable"
        axes = _safe_dict(arc.get("axes"))
        axes_by_npc[str(npc_id)] = axes
        for axis, value in axes.items():
            try:
                int_value = int(value or 0)
                if int_value < -10 or int_value > 10:
                    out_of_bounds_axes.append(
                        {"npc_id": str(npc_id), "axis": str(axis), "value": int_value}
                    )
            except Exception:
                out_of_bounds_axes.append(
                    {"npc_id": str(npc_id), "axis": str(axis), "value": value}
                )
        milestones = _safe_list(arc.get("milestones"))
        milestones_by_npc[str(npc_id)] = len(milestones)
        milestone_total += len(milestones)
        for milestone in milestones:
            milestone_id = _safe_str(_safe_dict(milestone).get("milestone_id"))
            if not milestone_id:
                continue
            if milestone_id in seen_milestones:
                duplicate_milestone_ids.append(milestone_id)
            seen_milestones.add(milestone_id)
    return {
        "signal_total": len(signals),
        "signal_consumed": consumed,
        "signal_pending": len(signals) - consumed,
        "signals_by_kind": by_kind,
        "signals_by_npc": by_npc,
        "arc_count": len(arcs),
        "arcs_by_npc": sorted(list(arcs.keys())),
        "consumed_projection_count": len(consumed_projection_ids),
        "arc_stages": arc_stages,
        "axes_by_npc": axes_by_npc,
        "milestone_total": milestone_total,
        "milestones_by_npc": milestones_by_npc,
        "duplicate_milestone_ids": duplicate_milestone_ids,
        "out_of_bounds_axes": out_of_bounds_axes,
    }