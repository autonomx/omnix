from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from app.rpg.ai.action_intelligence import get_action_advisory
from app.rpg.ai.semantic_action_intelligence import get_semantic_action_advisory
from app.rpg.llm_app_gateway import build_app_llm_gateway
from app.rpg.session.first_call_dialogue import build_non_stateful_dialogue_result
from app.rpg.session import runtime as canonical_runtime


def _d(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _s(value: Any) -> str:
    return str(value) if value is not None else ""


def _load_manual_session_override(session_id: str) -> Dict[str, Any]:
    """Best-effort bridge for manual scenario sessions.

    Manual scenarios persist rich setup state through the manual harness helpers,
    while production runtime loaders may return a canonical session shell without
    those test-only setup fields.  Keep this import guarded so normal gameplay
    never depends on tests.
    """
    if not _s(session_id).startswith("manual_service_"):
        return {}
    try:
        from tests.rpg.manual.session_helpers import _ensure_manual_session

        return _d(_ensure_manual_session(session_id))
    except Exception:
        return {}


def _select_session(session_id: str, session_override: Dict[str, Any] | None = None) -> Dict[str, Any]:
    override = _d(session_override)
    if override:
        return deepcopy(override)

    manual = _load_manual_session_override(session_id)
    if manual:
        return manual

    loaded = canonical_runtime.load_runtime_session(session_id)
    return _d(loaded)


def _stateful_action_from_first_call(
    action_advisory: Dict[str, Any],
    semantic_advisory: Dict[str, Any],
) -> Dict[str, Any]:
    semantic_advisory = _d(semantic_advisory)
    action_advisory = _d(action_advisory)
    source = semantic_advisory or action_advisory
    if not source:
        return {}
    action = {
        "action_type": _s(source.get("action_type")),
        "target_id": _s(source.get("target_id")),
        "target_name": _s(source.get("target_name")),
        "difficulty": _s(source.get("difficulty")),
        "skill_id": _s(source.get("skill_id")),
        "metadata": {
            "first_call_advisory": True,
            "first_call_action_advisory": action_advisory,
            "first_call_semantic_advisory": semantic_advisory,
            "first_call_grounding_diagnostics": _d(
                semantic_advisory.get("first_call_grounding_diagnostics")
                or action_advisory.get("first_call_grounding_diagnostics")
            ),
        },
    }
    return {k: v for k, v in action.items() if v not in (None, "", {})}


def _disable_duplicate_runtime_first_call(performance_override: Dict[str, Any] | None) -> Dict[str, Any]:
    merged = dict(_d(performance_override))
    merged.setdefault("enable_action_advisory", False)
    merged.setdefault("enable_semantic_action_advisory", False)
    return merged


def apply_turn(
    session_id: str,
    player_input: str,
    action: Dict[str, Any] | None = None,
    *,
    performance_override: Dict[str, Any] | None = None,
    session_override: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Interactive CLI two-call entry point.

    CE.1.3 bridges manual scenario setup state into the first-call grounding
    layer.  Production/canonical runtime remains authoritative for stateful
    actions; only non-stateful interpretive NPC dialogue can return directly.
    """

    session = _select_session(session_id, session_override=session_override)
    if not session:
        return {"ok": False, "error": "session_not_found"}

    simulation_state = _d(session.get("simulation_state"))
    runtime_state = _d(session.get("runtime_state"))
    candidate_action = _d(action)

    # Deterministic service/commerce detection always wins over LLM visible text.
    try:
        service_match = canonical_runtime.resolve_service_turn(
            player_input=_s(player_input),
            action=candidate_action,
            resolved_action={},
            simulation_state=simulation_state,
            runtime_state=runtime_state,
        )
    except Exception:
        service_match = {}
    service_matched = bool(_d(service_match).get("matched"))

    action_advisory: Dict[str, Any] = {}
    semantic_advisory: Dict[str, Any] = {}
    try:
        gateway = build_app_llm_gateway()
        action_advisory = get_action_advisory(
            llm_gateway=gateway,
            player_input=_s(player_input),
            simulation_state=simulation_state,
            runtime_state=runtime_state,
            candidate_action=candidate_action,
        )
        semantic_advisory = get_semantic_action_advisory(
            llm_gateway=gateway,
            player_input=_s(player_input),
            simulation_state=simulation_state,
            runtime_state=runtime_state,
            candidate_action=candidate_action or action_advisory,
        )
    except Exception as exc:
        runtime_state["first_call_grounding_error"] = f"{type(exc).__name__}: {exc}"

    non_stateful_result = build_non_stateful_dialogue_result(
        session=session,
        simulation_state=simulation_state,
        runtime_state=runtime_state,
        player_input=_s(player_input),
        action_advisory=action_advisory,
        semantic_advisory=semantic_advisory,
        service_matched=service_matched,
    )
    if non_stateful_result.get("consumed"):
        non_stateful_result["turn_id"] = canonical_runtime._build_turn_id(runtime_state)
        non_stateful_result["tick"] = int(runtime_state.get("tick", 0) or 0)
        non_stateful_result["first_call_action_advisory"] = action_advisory
        non_stateful_result["first_call_semantic_advisory"] = semantic_advisory
        non_stateful_result["first_call_grounding_diagnostics"] = _d(
            semantic_advisory.get("first_call_grounding_diagnostics")
            or action_advisory.get("first_call_grounding_diagnostics")
            or non_stateful_result.get("first_call_grounding_diagnostics")
        )
        return non_stateful_result

    first_call_action = _stateful_action_from_first_call(action_advisory, semantic_advisory)
    if not first_call_action:
        first_call_action = candidate_action

    result = canonical_runtime.apply_turn(
        session_id=session_id,
        player_input=_s(player_input),
        action=first_call_action,
        performance_override=_disable_duplicate_runtime_first_call(performance_override),
    )
    if isinstance(result, dict):
        result["first_call_action_advisory"] = action_advisory
        result["first_call_semantic_advisory"] = semantic_advisory
        result["first_call_visible_response_selection"] = _d(
            non_stateful_result.get("selection")
        )
        result["first_call_grounding_diagnostics"] = _d(
            semantic_advisory.get("first_call_grounding_diagnostics")
            or action_advisory.get("first_call_grounding_diagnostics")
        )
    return result
