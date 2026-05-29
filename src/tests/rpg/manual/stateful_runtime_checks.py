from __future__ import annotations

from typing import Any, Dict, List


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            return True
        if lowered in {"0", "false", "no", "n", "off"}:
            return False
    if value is None:
        return default
    return bool(value)


def _first_dict(*values: Any) -> Dict[str, Any]:
    for value in values:
        value = _safe_dict(value)
        if value:
            return value
    return {}


def _extract_contract(result: Dict[str, Any]) -> Dict[str, Any]:
    result = _safe_dict(result)
    nested = _safe_dict(result.get("result"))
    return _first_dict(
        result.get("stateful_runtime_narration_contract"),
        nested.get("stateful_runtime_narration_contract"),
        result.get("narration_contract"),
        nested.get("narration_contract"),
    )


def _extract_diagnostics(contract: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    result = _safe_dict(result)
    nested = _safe_dict(result.get("result"))
    return _first_dict(
        _safe_dict(contract).get("first_call_grounding_diagnostics"),
        result.get("first_call_grounding_diagnostics"),
        nested.get("first_call_grounding_diagnostics"),
        _safe_dict(result.get("grounding_validation")).get("first_call_grounding_diagnostics"),
        _safe_dict(nested.get("grounding_validation")).get("first_call_grounding_diagnostics"),
    )


def run_stateful_runtime_check(
    *,
    check: Dict[str, Any],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    del session
    check = _safe_dict(check)
    result = _safe_dict(result)
    failures: List[str] = []

    expected_turn = check.get("expected_turn")
    if expected_turn is not None and int(result.get("turn_index") or 0) != int(expected_turn):
        return {
            "check_type": _safe_str(check.get("type") or "stateful_runtime_narration_contract"),
            "ok": True,
            "skipped": True,
            "error": "",
        }

    contract = _extract_contract(result)
    diagnostics = _extract_diagnostics(contract, result)
    normalized = _safe_dict(diagnostics.get("normalized_result"))

    if not contract:
        failures.append("missing_stateful_runtime_narration_contract")

    expected_mode = _safe_str(check.get("expected_narration_mode")).strip()
    if expected_mode and _safe_str(contract.get("narration_mode")) != expected_mode:
        failures.append("unexpected_narration_mode")

    expected_status = _safe_str(check.get("expected_narration_status")).strip()
    if expected_status and _safe_str(contract.get("narration_status")) != expected_status:
        failures.append("unexpected_narration_status")

    if check.get("require_runtime_authoritative", True) and not _safe_bool(
        contract.get("stateful_runtime_authoritative")
    ):
        failures.append("runtime_not_marked_authoritative")

    if check.get("require_runtime_before_narration", True) and not _safe_bool(
        contract.get("runtime_resolved_before_narration")
    ):
        failures.append("runtime_not_marked_before_narration")

    if _safe_bool(contract.get("first_call_may_resolve_state"), True):
        failures.append("first_call_allowed_to_resolve_state")

    if _safe_bool(contract.get("narration_may_mutate_state"), True):
        failures.append("narration_allowed_to_mutate_state")

    if check.get("require_provider_stateful") and not _safe_bool(normalized.get("stateful")):
        failures.append("provider_not_stateful")

    if check.get("require_provider_needs_runtime") and not _safe_bool(
        normalized.get("needs_runtime_resolution")
    ):
        failures.append("provider_did_not_require_runtime")

    if check.get("require_diagnostics") and not diagnostics:
        failures.append("missing_first_call_grounding_diagnostics")

    text_blob = " ".join(
        [
            _safe_str(result.get("narration_preview")),
            _safe_str(result.get("narration")),
            _safe_str(_safe_dict(result.get("extracted")).get("narration")),
            _safe_str(_safe_dict(result.get("extracted")).get("npc_line")),
        ]
    ).lower()
    for term in _safe_list(check.get("forbidden_visible_terms")):
        term_text = _safe_str(term).strip().lower()
        if term_text and term_text in text_blob:
            failures.append(f"forbidden_visible_term:{term_text}")

    return {
        "check_type": _safe_str(check.get("type") or "stateful_runtime_narration_contract"),
        "ok": not failures,
        "skipped": False,
        "failures": failures,
        "error": ";".join(failures),
        "narration_mode": _safe_str(contract.get("narration_mode")),
        "narration_status": _safe_str(contract.get("narration_status")),
        "provider_stateful": _safe_bool(normalized.get("stateful")),
        "provider_needs_runtime_resolution": _safe_bool(normalized.get("needs_runtime_resolution")),
    }


def run_stateful_runtime_checks(
    *,
    checks: List[Dict[str, Any]],
    result: Dict[str, Any],
    session: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    return [
        run_stateful_runtime_check(check=check, result=result, session=session)
        for check in _safe_list(checks)
    ]
