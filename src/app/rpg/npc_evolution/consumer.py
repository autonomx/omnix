from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Tuple

from app.rpg.npc_evolution.arcs import (
    canonical_npc_id,
    ingest_evolution_signals,
    normalize_projection_to_evolution_signal,
    npc_evolution_state,
    summarize_npc_evolution_state,
)
from app.rpg.npc_evolution.target_grounding import ground_projection_target


AXES = {
    "trust",
    "fear",
    "respect",
    "curiosity",
    "resentment",
    "loyalty",
}


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _projection_id_from_accepted_row(accepted_row: Dict[str, Any]) -> str:
    accepted_row = _safe_dict(accepted_row)
    projection = _safe_dict(accepted_row.get("projection"))
    return (
        _safe_str(projection.get("candidate_id"))
        or _safe_str(accepted_row.get("candidate_id"))
    )


def _evolution_consumed_projection_ids(runtime_state: Dict[str, Any]) -> set[str]:
    evo_state = _safe_dict(_safe_dict(runtime_state).get("npc_evolution"))
    consumed = _safe_list(evo_state.get("consumed_projection_ids"))
    return {str(item) for item in consumed if item}


def _mark_projection_evolution_consumed(runtime_state: Dict[str, Any], projection_id: str) -> None:
    if not projection_id:
        return
    evo_state = runtime_state.setdefault("npc_evolution", {})
    consumed = evo_state.setdefault("consumed_projection_ids", [])
    if projection_id not in consumed:
        consumed.append(projection_id)
    if len(consumed) > 500:
        evo_state["consumed_projection_ids"] = consumed[-500:]


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _arc_for_npc(runtime_state: Dict[str, Any], npc_id: str) -> Dict[str, Any]:
    evo_state = npc_evolution_state(runtime_state)
    arcs = evo_state.setdefault("arcs", {})
    arc = arcs.setdefault(
        npc_id,
        {
            "npc_id": npc_id,
            "arc_stage": "stable",
            "axes": {
                "trust": 0,
                "fear": 0,
                "respect": 0,
                "curiosity": 0,
                "resentment": 0,
                "loyalty": 0,
            },
            "memories": [],
            "world_signals": [],
            "future_hooks": [],
            "semantic_intents": [],
            "milestones": [],
            "updated_at_turn": 0,
        },
    )
    return arc


def _merge_duplicate_arc_ids(
    *,
    runtime_state: Dict[str, Any],
    canonical_id: str,
    aliases: List[str],
) -> None:
    evo_state = npc_evolution_state(runtime_state)
    arcs = evo_state.setdefault("arcs", {})
    if canonical_id not in arcs:
        return
    canonical_arc = arcs[canonical_id]

    for alias in aliases:
        if not alias or alias == canonical_id or alias not in arcs:
            continue
        alias_arc = arcs.pop(alias)

        for axis, value in _safe_dict(alias_arc.get("axes")).items():
            try:
                canonical_arc.setdefault("axes", {})[axis] = max(
                    int(canonical_arc.setdefault("axes", {}).get(axis) or 0),
                    int(value or 0),
                )
            except Exception:
                canonical_arc.setdefault("axes", {})[axis] = value

        for key, limit in (
            ("memories", 30),
            ("world_signals", 20),
            ("future_hooks", 20),
            ("semantic_intents", 20),
            ("milestones", 20),
        ):
            existing = _safe_list(canonical_arc.get(key))
            seen = {
                _safe_str(_safe_dict(item).get("signal_id")) or str(item)
                for item in existing
            }
            for item in _safe_list(alias_arc.get(key)):
                marker = _safe_str(_safe_dict(item).get("signal_id")) or str(item)
                if marker in seen:
                    continue
                seen.add(marker)
                existing.append(item)
            canonical_arc[key] = existing[-limit:]


def _derive_arc_stage(axes: Dict[str, Any]) -> str:
    trust = int(axes.get("trust") or 0)
    fear = int(axes.get("fear") or 0)
    resentment = int(axes.get("resentment") or 0)
    loyalty = int(axes.get("loyalty") or 0)
    curiosity = int(axes.get("curiosity") or 0)

    if loyalty >= 5 and trust >= 4:
        return "ally_leaning"
    if resentment >= 5:
        return "resentful"
    if fear >= 5:
        return "fearful"
    if trust >= 4:
        return "trusting"
    if curiosity >= 4:
        return "curious"
    if trust <= -3:
        return "guarded"
    return "stable"


def _append_bounded(items: List[Dict[str, Any]], item: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
    existing_ids = {_safe_str(existing.get("signal_id")) for existing in items if isinstance(existing, dict)}
    signal_id = _safe_str(item.get("signal_id"))
    if signal_id and signal_id in existing_ids:
        return items
    items.append(deepcopy(item))
    if len(items) > limit:
        return items[-limit:]
    return items


def _consume_relationship_delta(arc: Dict[str, Any], signal: Dict[str, Any]) -> Dict[str, Any]:
    payload = _safe_dict(signal.get("payload"))
    axis = _safe_str(payload.get("axis") or payload.get("relationship_axis") or "trust").lower()
    if axis not in AXES:
        axis = "trust"
    try:
        delta = int(payload.get("delta") or 0)
    except Exception:
        delta = 0
    delta = _clamp(delta, -2, 2)
    axes = arc.setdefault("axes", {})
    axes[axis] = _clamp(int(axes.get(axis) or 0) + delta, -10, 10)
    return {
        "kind": "relationship_delta",
        "axis": axis,
        "delta": delta,
        "new_value": axes[axis],
    }


def _consume_memory(arc: Dict[str, Any], signal: Dict[str, Any]) -> Dict[str, Any]:
    payload = _safe_dict(signal.get("payload"))
    memory = {
        "signal_id": signal.get("signal_id"),
        "turn_index": signal.get("turn_index"),
        "summary": _safe_str(payload.get("summary") or signal.get("summary"))[:500],
        "importance": payload.get("importance", 0.5),
        "source": signal.get("source"),
    }
    arc["memories"] = _append_bounded(_safe_list(arc.get("memories")), memory, 30)
    return {"kind": "memory", "memory_count": len(arc["memories"])}


def _consume_world_signal(arc: Dict[str, Any], signal: Dict[str, Any]) -> Dict[str, Any]:
    payload = _safe_dict(signal.get("payload"))
    row = {
        "signal_id": signal.get("signal_id"),
        "turn_index": signal.get("turn_index"),
        "kind": _safe_str(payload.get("kind") or "world_signal"),
        "summary": _safe_str(payload.get("summary") or signal.get("summary"))[:500],
    }
    arc["world_signals"] = _append_bounded(_safe_list(arc.get("world_signals")), row, 20)
    return {"kind": "world_signal", "world_signal_count": len(arc["world_signals"])}


def _consume_future_hook(arc: Dict[str, Any], signal: Dict[str, Any]) -> Dict[str, Any]:
    payload = _safe_dict(signal.get("payload"))
    row = {
        "signal_id": signal.get("signal_id"),
        "turn_index": signal.get("turn_index"),
        "kind": _safe_str(payload.get("kind") or "future_hook"),
        "summary": _safe_str(payload.get("summary") or signal.get("summary"))[:500],
    }
    arc["future_hooks"] = _append_bounded(_safe_list(arc.get("future_hooks")), row, 20)
    return {"kind": "future_hook", "future_hook_count": len(arc["future_hooks"])}


def _consume_semantic_intent(arc: Dict[str, Any], signal: Dict[str, Any]) -> Dict[str, Any]:
    payload = _safe_dict(signal.get("payload"))
    row = {
        "signal_id": signal.get("signal_id"),
        "turn_index": signal.get("turn_index"),
        "intent": _safe_str(payload.get("intent") or payload.get("type") or signal.get("summary"))[:120],
        "summary": _safe_str(payload.get("summary") or signal.get("summary"))[:500],
    }
    arc["semantic_intents"] = _append_bounded(_safe_list(arc.get("semantic_intents")), row, 20)
    return {"kind": "semantic_intent", "semantic_intent_count": len(arc["semantic_intents"])}


def consume_evolution_signal(
    *,
    runtime_state: Dict[str, Any],
    signal: Dict[str, Any],
    turn_index: int,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    runtime_state = runtime_state if isinstance(runtime_state, dict) else {}
    signal = deepcopy(_safe_dict(signal))
    npc_id = _safe_str(signal.get("npc_id"))
    if not npc_id:
        return runtime_state, {"ok": False, "reason": "npc_id_missing"}
    if signal.get("consumed"):
        return runtime_state, {"ok": False, "reason": "already_consumed", "signal_id": signal.get("signal_id")}

    arc = _arc_for_npc(runtime_state, npc_id)
    alias_base = npc_id.lower()
    _merge_duplicate_arc_ids(
        runtime_state=runtime_state,
        canonical_id=npc_id,
        aliases=[
            f"npc:{alias_base}",
            f"npc:{npc_id}",
            alias_base,
        ],
    )
    before_stage = _safe_str(arc.get("arc_stage") or "stable")
    kind = _safe_str(signal.get("kind"))

    if kind == "relationship_delta":
        effect = _consume_relationship_delta(arc, signal)
    elif kind == "memory":
        effect = _consume_memory(arc, signal)
    elif kind == "world_signal":
        effect = _consume_world_signal(arc, signal)
    elif kind == "future_hook":
        effect = _consume_future_hook(arc, signal)
    elif kind == "semantic_intent":
        effect = _consume_semantic_intent(arc, signal)
    else:
        return runtime_state, {"ok": False, "reason": "unsupported_signal_kind", "kind": kind}

    arc["updated_at_turn"] = int(turn_index)
    arc["arc_stage"] = _derive_arc_stage(_safe_dict(arc.get("axes")))
    after_stage = arc["arc_stage"]
    milestone = None
    if before_stage != after_stage:
        milestone = {
            "turn_index": turn_index,
            "from": before_stage,
            "to": after_stage,
            "reason": f"evolution_signal:{kind}",
            "signal_id": signal.get("signal_id"),
        }
        arc["milestones"] = _append_bounded(_safe_list(arc.get("milestones")), milestone, 20)

    signal["consumed"] = True
    signal["consumed_at_turn"] = int(turn_index)

    evo_state = npc_evolution_state(runtime_state)
    for index, existing in enumerate(_safe_list(evo_state.get("signals"))):
        if _safe_str(_safe_dict(existing).get("signal_id")) == _safe_str(signal.get("signal_id")):
            evo_state["signals"][index] = signal
            break

    decision = {
        "ok": True,
        "npc_id": npc_id,
        "signal_id": signal.get("signal_id"),
        "kind": kind,
        "effect": effect,
        "arc_stage_before": before_stage,
        "arc_stage_after": after_stage,
        "milestone": milestone,
    }
    return runtime_state, decision


def consume_accepted_advisory_projections(
    *,
    runtime_state: Dict[str, Any],
    simulation_state: Dict[str, Any],
    turn_index: int,
    max_signals_per_turn: int = 8,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Convert accepted advisory projections into persistent NPC evolution arcs."""
    runtime_state = runtime_state if isinstance(runtime_state, dict) else {}
    simulation_state = _safe_dict(simulation_state)
    advisory = _safe_dict(runtime_state.get("deferred_advisory"))
    accepted = _safe_list(advisory.get("accepted"))

    signals: List[Dict[str, Any]] = []
    projection_decisions: List[Dict[str, Any]] = []
    consumed_projection_ids = _evolution_consumed_projection_ids(runtime_state)
    for accepted_row in accepted[-max_signals_per_turn:]:
        accepted_row = _safe_dict(accepted_row)
        projection = _safe_dict(accepted_row.get("projection"))
        if not projection:
            continue
        projection_id = _projection_id_from_accepted_row(accepted_row)
        if projection_id and projection_id in consumed_projection_ids:
            projection_decisions.append(
                {
                    "projection_id": projection_id,
                    "status": "skipped",
                    "reason": "already_evolution_consumed",
                    "kind": projection.get("kind"),
                }
            )
            continue
        grounded_projection, grounding_result = ground_projection_target(
            projection=projection,
            simulation_state=simulation_state,
        )
        signal, rejection = normalize_projection_to_evolution_signal(
            projection=grounded_projection,
            simulation_state=simulation_state,
            turn_index=int(turn_index),
        )
        if signal:
            canonical = canonical_npc_id(
                simulation_state=simulation_state,
                npc_id=_safe_str(signal.get("npc_id")),
            )
            if canonical:
                signal["npc_id"] = canonical
                signal["canonical_npc_id"] = canonical
                signal.setdefault("payload", {})["target"] = canonical
                signal.setdefault("payload", {})["grounded_target"] = canonical
            signal["target_grounding"] = grounding_result
            signals.append(signal)
            projection_decisions.append(
                {
                    "projection_id": projection_id or projection.get("candidate_id"),
                    "status": "signal_created",
                    "signal_id": signal.get("signal_id"),
                    "kind": signal.get("kind"),
                    "npc_id": signal.get("npc_id"),
                    "target_grounding": grounding_result,
                }
            )
        else:
            projection_decisions.append(
                {
                    "projection_id": projection_id or projection.get("candidate_id"),
                    "status": "rejected",
                    "reason": rejection,
                    "kind": projection.get("kind"),
                    "target_grounding": grounding_result,
                }
            )

    ingest_result = ingest_evolution_signals(runtime_state=runtime_state, signals=signals)
    consumed = 0
    consume_decisions: List[Dict[str, Any]] = []
    evo_state = npc_evolution_state(runtime_state)
    for signal in _safe_list(evo_state.get("signals")):
        signal_dict = _safe_dict(signal)
        if signal_dict.get("consumed"):
            continue
        runtime_state, decision = consume_evolution_signal(
            runtime_state=runtime_state,
            signal=signal_dict,
            turn_index=turn_index,
        )
        consume_decisions.append(decision)
        if decision.get("ok"):
            consumed += 1
            projection_id = _safe_str(signal_dict.get("projection_id"))
            if projection_id:
                _mark_projection_evolution_consumed(runtime_state, projection_id)

    evo_state = npc_evolution_state(runtime_state)
    summary = summarize_npc_evolution_state(runtime_state)
    evo_state["summary"] = summary
    evo_state.setdefault("consumption_log", []).append(
        {
            "turn_index": turn_index,
            "signals_created": len(signals),
            "signals_consumed": consumed,
            "projection_decisions": projection_decisions,
            "consume_decisions": consume_decisions,
        }
    )

    return runtime_state, {
        "ok": True,
        "turn_index": turn_index,
        "signals_created": len(signals),
        "signals_consumed": consumed,
        "already_consumed_projection_skips": sum(
            1
            for decision in projection_decisions
            if _safe_dict(decision).get("reason") == "already_evolution_consumed"
        ),
        "projection_decisions": projection_decisions,
        "consume_decisions": consume_decisions,
        "ingest_result": ingest_result,
        "summary": summary,
    }