from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.rpg.spatial.audibility import audible_entities_from, can_hear_entity
from app.rpg.spatial.graph import get_entity_area
from app.rpg.spatial.movement import can_move_between
from app.rpg.spatial.serialization import normalize_spatial_graph
from app.rpg.spatial.visibility import can_see_entity, visible_entities_from


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _graph_has_content(graph: Dict[str, Any]) -> bool:
    return bool(
        graph.get("areas")
        or graph.get("connections")
        or graph.get("entity_locations")
    )


def _candidate_simulation_states(
    *,
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> Iterable[Dict[str, Any]]:
    result = _safe_dict(result)
    nested_result = _safe_dict(result.get("result"))
    session_dict = _safe_dict(session)

    candidates = [
        result.get("simulation_state"),
        _safe_dict(result.get("session")).get("simulation_state"),
        nested_result.get("simulation_state"),
        _safe_dict(nested_result.get("session")).get("simulation_state"),
        _safe_dict(result.get("turn_contract")).get("simulation_state"),
        session_dict.get("simulation_state"),
        _safe_dict(session_dict.get("setup_payload"))
        .get("metadata", {})
        .get("simulation_state"),
    ]

    for candidate in candidates:
        candidate = _safe_dict(candidate)
        if candidate:
            yield candidate


def _extract_spatial_graph(
    *,
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    for simulation_state in _candidate_simulation_states(result=result, session=session):
        graph = normalize_spatial_graph(simulation_state.get("spatial_graph"))
        if _graph_has_content(graph):
            return graph

    # Also tolerate result/turn_contract carrying graph directly.
    for direct_graph in [
        _safe_dict(result).get("spatial_graph"),
        _safe_dict(_safe_dict(result).get("turn_contract")).get("spatial_graph"),
        _safe_dict(_safe_dict(result).get("spatial_context")).get("spatial_graph"),
    ]:
        graph = normalize_spatial_graph(_safe_dict(direct_graph))
        if _graph_has_content(graph):
            return graph

    return {}


def _missing_graph_result(check_type: str) -> Dict[str, Any]:
    return {
        "check_type": check_type,
        "ok": False,
        "error": "spatial_graph_missing",
        "expected_ok": None,
        "actual_ok": None,
        "actual_reason": "spatial_graph_missing",
    }


def _check_bool(
    *,
    check_type: str,
    expected_ok: bool,
    actual: Dict[str, Any],
    expected_reason: str = "",
) -> Dict[str, Any]:
    actual_ok = bool(actual.get("ok"))
    reason = str(actual.get("reason") or "")
    ok = actual_ok is bool(expected_ok)
    if expected_reason:
        ok = ok and reason == expected_reason
    return {
        "check_type": check_type,
        "ok": ok,
        "expected_ok": expected_ok,
        "actual_ok": actual_ok,
        "expected_reason": expected_reason,
        "actual_reason": reason,
        "actual": actual,
    }


def run_spatial_check(
    *,
    check: Dict[str, Any],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    check_type = str(check.get("type") or "")
    graph = _extract_spatial_graph(result=result, session=session)
    if not graph:
        return _missing_graph_result(check_type)

    if check_type == "spatial_current_area":
        entity_id = str(check.get("entity") or "player")
        expected_area_id = str(check.get("expected_area_id") or "")
        actual_area_id = get_entity_area(graph, entity_id)
        return {
            "check_type": check_type,
            "ok": actual_area_id == expected_area_id,
            "entity": entity_id,
            "expected_area_id": expected_area_id,
            "actual_area_id": actual_area_id,
        }

    if check_type == "spatial_can_move":
        actual = can_move_between(
            graph,
            str(check.get("from_area_id") or ""),
            str(check.get("to_area_id") or ""),
        )
        return _check_bool(
            check_type=check_type,
            expected_ok=bool(check.get("expected_ok")),
            expected_reason=str(check.get("expected_reason") or ""),
            actual=actual,
        )

    if check_type == "spatial_visibility":
        actual = can_see_entity(
            graph,
            str(check.get("viewer") or "player"),
            str(check.get("target") or ""),
        )
        return _check_bool(
            check_type=check_type,
            expected_ok=bool(check.get("expected_ok")),
            expected_reason=str(check.get("expected_reason") or ""),
            actual=actual,
        )

    if check_type == "spatial_audibility":
        actual = can_hear_entity(
            graph,
            str(check.get("listener") or "player"),
            str(check.get("source") or ""),
            sound_level=str(check.get("sound_level") or "normal"),
        )
        return _check_bool(
            check_type=check_type,
            expected_ok=bool(check.get("expected_ok")),
            expected_reason=str(check.get("expected_reason") or ""),
            actual=actual,
        )

    if check_type == "spatial_visible_entities":
        expected_ids = set(check.get("expected_entity_ids") or [])
        actual_ids = {
            row["entity_id"]
            for row in visible_entities_from(graph, str(check.get("viewer") or "player"))
        }
        mode = str(check.get("mode") or "contains")
        ok = expected_ids <= actual_ids if mode == "contains" else expected_ids == actual_ids
        return {
            "check_type": check_type,
            "ok": ok,
            "mode": mode,
            "expected_entity_ids": sorted(expected_ids),
            "actual_entity_ids": sorted(actual_ids),
        }

    if check_type == "spatial_audible_entities":
        expected_ids = set(check.get("expected_entity_ids") or [])
        actual_ids = {
            row["entity_id"]
            for row in audible_entities_from(
                graph,
                str(check.get("listener") or "player"),
            )
        }
        mode = str(check.get("mode") or "contains")
        ok = expected_ids <= actual_ids if mode == "contains" else expected_ids == actual_ids
        return {
            "check_type": check_type,
            "ok": ok,
            "mode": mode,
            "expected_entity_ids": sorted(expected_ids),
            "actual_entity_ids": sorted(actual_ids),
        }

    return {
        "check_type": check_type,
        "ok": False,
        "error": f"unknown_spatial_check_type:{check_type}",
    }


def run_spatial_checks(
    *,
    checks: List[Dict[str, Any]],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    return [
        run_spatial_check(check=check, result=result, session=session)
        for check in checks
    ]